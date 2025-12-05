#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
device.py

Main logic, Sensor start/stop, uploads and Smiley logic.

This safe version:
- Exposes the callbacks the UI expects at module level (get_counts, get_override_info, ...)
- Does NOT import or call ui.run() at import time (avoids circular imports / side effects)
- Starts sensors and calls ui.run(...) only when executed as __main__
"""
import time
import json
import requests
import threading
import os
import argparse
import logging
from datetime import datetime
from typing import Tuple

import sensor  # sensor is allowed to start/stop from main

# --- Configuration ---
SERVER_URL = "http://127.0.0.1:5000/upload"
UPLOAD_TIMES = [(9, 15), (12, 15), (15, 15), (18, 15)]
BASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(BASE_DIR, exist_ok=True)

# --- Device ID ---
DEVICE_ID = "01_Torben"
print(f"[INFO] Client-ID: {DEVICE_ID}")

# --- Logging ---
logging.basicConfig(level=logging.INFO)
_LOG = logging.getLogger("device")

# --- Command line args (parsed only in __main__) ---
parser = argparse.ArgumentParser(description="SIA Client (Smiley + Sensoranzeige)")
parser.add_argument("--interval", "-i", type=float, default=2.0, help="Sensor Poll-Intervall in Sekunden (default 2.0)")
parser.add_argument("--use-scd", action="store_true", help="SCD4x (SCD40/SCD41) verwenden, falls vorhanden")
parser.add_argument("--use-bme", action="store_true", help="BME280 als Temperaturquelle verwenden, falls vorhanden")
parser.add_argument("--use-mic", action="store_true", help="Enable microphone (ICS43434) reading if available")

# =========================================================
# ================ DATENSTRUKTUREN ========================
# =========================================================
events = []
upload_history = []
upload_counter = 0

# Smiley / Override
current_smiley_kind = None
smiley_override_time = 0.0
SMILEY_OVERRIDE_DURATION = 3

# Upload failure indicator
upload_failed_time = 0
UPLOAD_FAILED_DURATION = 2.0

# SMILEY persistence
SMILEY_EMA_ALPHA = 0.20
SMILEY_STATE_FILENAME = "smiley_state.json"
smiley_ema = 0.0

def _smiley_state_path():
    device_dir = os.path.join(BASE_DIR, DEVICE_ID)
    os.makedirs(device_dir, exist_ok=True)
    return os.path.join(device_dir, SMILEY_STATE_FILENAME)

def load_smiley_state():
    global smiley_ema
    path = _smiley_state_path()
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            smiley_ema = float(data.get("ema", 0.0))
            _LOG.info("Loaded smiley EMA: %.4f", smiley_ema)
        else:
            smiley_ema = 0.0
    except Exception as e:
        _LOG.exception("Failed to load smiley state: %s", e)
        smiley_ema = 0.0

def save_smiley_state():
    path = _smiley_state_path()
    try:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"ema": smiley_ema}, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        _LOG.debug("Saved smiley EMA: %.4f", smiley_ema)
    except Exception:
        _LOG.exception("Failed to save smiley state")

load_smiley_state()

# Rotation logic used by calculate_avg_smiley (keeps a simple rotating display)
ROTATION_ORDER = ["good", "meh", "bad"]
ROTATION_INTERVAL = 1.5
_rotation_idx = 0
_rotation_last = time.time()

def pct_round(good: int, meh: int, bad: int) -> Tuple[int,int,int]:
    total = good + meh + bad
    if total == 0:
        return 0,0,0
    fg = (good / total) * 100.0
    fm = (meh / total) * 100.0
    fb = (bad / total) * 100.0
    ig = int(fg)
    im = int(fm)
    ib = int(fb)
    remainder = 100 - (ig + im + ib)
    fracs = [ (fg - ig, 'g'), (fm - im, 'm'), (fb - ib, 'b') ]
    fracs.sort(reverse=True)
    for i in range(remainder):
        if fracs[i % 3][1] == 'g':
            ig += 1
        elif fracs[i % 3][1] == 'm':
            im += 1
        else:
            ib += 1
    return ig, im, ib

def calculate_avg_smiley(good: int, meh: int, bad: int):
    """
    Return (kind, (pct_good,pct_meh,pct_bad)).
    Uses rotation for kind to reproduce v7 behavior.
    """
    global _rotation_idx, _rotation_last
    pct_good, pct_meh, pct_bad = pct_round(good, meh, bad)
    now = time.time()
    if now - _rotation_last >= ROTATION_INTERVAL:
        _rotation_idx = (_rotation_idx + 1) % len(ROTATION_ORDER)
        _rotation_last = now
    kind = ROTATION_ORDER[_rotation_idx]
    return kind, (pct_good, pct_meh, pct_bad)

# =========================================================
# ================ SENSOR / UPLOAD HELPERS ===============
# =========================================================
def avg_sensor_values():
    buf = sensor.sensor_buffer
    if not buf:
        return {"temp":0,"db":0,"co2":0,"voc":0}
    # sensor_buffer may contain SensorSample objects or legacy tuples
    try:
        # dataclass-like
        t = sum(getattr(s, "temp", s[0]) for s in buf) / len(buf)
        d = sum(getattr(s, "db", s[1]) for s in buf) / len(buf)
        c = sum(getattr(s, "co2", s[2]) for s in buf) / len(buf)
        v = sum(getattr(s, "voc", s[3]) for s in buf) / len(buf)
    except Exception:
        t = sum(s[0] for s in buf)/len(buf)
        d = sum(s[1] for s in buf)/len(buf)
        c = sum(s[2] for s in buf)/len(buf)
        v = sum(s[3] for s in buf)/len(buf)
    return {"temp":round(t,1),"db":round(d,1),"co2":int(c),"voc":int(v)}

def upload_to_server(avg_sensor, events_list):
    global upload_failed_time
    payload = {"device_id": DEVICE_ID, "events": events_list, "avg_sensor": avg_sensor}
    try:
        r = requests.post(SERVER_URL, json=payload, timeout=5)
        if r.status_code == 200:
            _LOG.info("✅ Upload erfolgreich: %s", r.json())
        else:
            _LOG.warning("❌ Fehler beim Upload: Status %s | %s", r.status_code, r.text)
            upload_failed_time = time.time()
    except Exception as e:
        _LOG.warning("⚠️ Upload fehlgeschlagen: %s", e)
        upload_failed_time = time.time()

def upload_cycle():
    global events, upload_counter, upload_history
    now = datetime.now()
    upload_counter += 1
    avg_sensor = avg_sensor_values()
    threading.Thread(target=upload_to_server, args=(avg_sensor, events.copy()), daemon=True).start()
    events.clear()
    try:
        sensor.sensor_buffer.clear()
    except Exception:
        pass
    upload_history.append((now.strftime("%Y-%m-%d"), upload_counter))
    _LOG.debug("upload_cycle: uploaded #%d", upload_counter)
    save_smiley_state()

def check_scheduled_upload():
    now = datetime.now()
    for idx, (hour, minute) in enumerate(UPLOAD_TIMES):
        if now.hour == hour and now.minute == minute and now.second < 5:
            today_str = now.strftime("%Y-%m-%d")
            if (not upload_history) or upload_history[-1][0] != today_str or upload_history[-1][1] < idx+1:
                upload_cycle()

# =========================================================
# ================ PUBLIC CALLBACKS for UI ===============
# =========================================================
good = meh = bad = 0

def get_counts() -> Tuple[int,int,int]:
    return good, meh, bad

def get_override_info():
    return current_smiley_kind, smiley_override_time, SMILEY_OVERRIDE_DURATION

def get_upload_info():
    return upload_failed_time, UPLOAD_FAILED_DURATION

def get_latest_sensor():
    """
    Return newest sensor sample (SensorSample object) if present,
    otherwise a fallback tuple (temp, db, co2, voc)
    """
    if sensor.sensor_buffer:
        try:
            return sensor.sensor_buffer[-1]
        except Exception:
            pass
    return (22.0, 0.0, 410, 10)

def on_vote(kind: str):
    """
    Called by UI when user votes.
    """
    global good, meh, bad, current_smiley_kind, smiley_override_time, smiley_ema
    ts = time.time()
    if kind == "good":
        good += 1
    elif kind == "meh":
        meh += 1
    else:
        bad += 1
    current_smiley_kind = kind
    smiley_override_time = ts
    # update EMA
    val = 1.0 if kind == "good" else (0.0 if kind == "meh" else -1.0)
    smiley_ema = (SMILEY_EMA_ALPHA * val) + ((1 - SMILEY_EMA_ALPHA) * smiley_ema)
    events.append({"kind": kind, "ts": ts})

def on_upload():
    upload_cycle()

# Load persisted smiley state at import time
load_smiley_state()

# =========================================================
# ================ START UI when run directly =============
# =========================================================
def _start_and_run_ui():
    # parse command line args here (only when running as script)
    args = parser.parse_args()
    POLL_INTERVAL = args.interval
    USE_SCD = args.use_scd
    USE_BME = args.use_bme
    USE_MIC = args.use_mic

    # Start sensor thread (simulator on desktop if no hardware)
    sensor.start(poll_interval=POLL_INTERVAL, use_scd=USE_SCD, use_bme=USE_BME, use_mic=USE_MIC)
    _LOG.info("Started sensors (simulator/hardware depending on environment)")

    # Import UI here to avoid circular imports at module import time
    import ui
    # Call UI.run with callbacks
    ui.run(
        get_counts,
        get_override_info,
        get_upload_info,
        get_latest_sensor,
        calculate_avg_smiley,
        pct_round,
        on_vote,
        on_upload
    )

    # UI returned (window closed) — clean up
    sensor.stop()
    save_smiley_state()
    # optionally do one last upload
    try:
        upload_cycle()
    except Exception:
        pass

if __name__ == "__main__":
    try:
        _start_and_run_ui()
    except Exception as e:
        _LOG.exception("Fatal error running UI: %s", e)
        try:
            sensor.stop()
        except Exception:
            pass
