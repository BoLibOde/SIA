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
from typing import Tuple, Optional

import sensor  # ensure this module is the SCD41-only sensor module

# --- Configuration ---
SERVER_URL = "http://127.0.0.1:5000/upload"
UPLOAD_TIMES = [(9, 15), (12, 15), (15, 15), (18, 15)]
BASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(BASE_DIR, exist_ok=True)

# --- Device ID ---
# DEVICE_ID can be provided via environment variable DEVICE_ID or a device_id.txt file inside BASE_DIR.
# Fallback to a default if neither is present.
_device_id_env = os.environ.get("DEVICE_ID")
_device_id_file = os.path.join(BASE_DIR, "device_id.txt")
if _device_id_env:
    DEVICE_ID = _device_id_env
elif os.path.exists(_device_id_file):
    try:
        with open(_device_id_file, "r", encoding="utf-8") as f:
            DEVICE_ID = f.read().strip()
            if not DEVICE_ID:
                DEVICE_ID = "01_Torben"
    except Exception:
        DEVICE_ID = "01_Torben"
else:
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

# Helper for percentage rounding
def pct_round(good: int, meh: int, bad: int) -> Tuple[int,int,int]:
    total = good + meh + bad
    if total == 0:
        return 0, 0, 0
    fg = int((good / total) * 100)
    fm = int((meh / total) * 100)
    fb = 100 - fg - fm
    return fg, fm, fb

# =========================================================
# ================ SENSOR / UPLOAD HELPERS ===============
# =========================================================
def avg_sensor_values():
    buf = sensor.sensor_buffer
    if not buf:
        return {"temp": 0, "db": 0, "co2": 0}  # no voc key if unavailable
    try:
        temp = round(sum(s.temp for s in buf) / len(buf), 1)
        db = round(sum(s.db for s in buf) / len(buf), 1)
        co2 = round(sum(s.co2 for s in buf) / len(buf), 0)
        voc_values = [s.voc for s in buf if s.voc is not None]
        if voc_values:
            voc = round(sum(voc_values) / len(voc_values), 0)
        else:
            voc = None
        result = {"temp": temp, "db": db, "co2": int(co2)}
        if voc is not None:
            result["voc"] = int(voc)
        return result
    except Exception as e:
        _LOG.exception("Error computing avg sensor values: %s", e)
        return {"temp": 0, "db": 0, "co2": 0}

def upload_to_server(avg_sensor, events_list):
    global upload_failed_time
    payload = {"device_id": DEVICE_ID, "events": events_list, "avg_sensor": avg_sensor}
    try:
        _LOG.info("Uploading to server with payload: %s", payload)
        response = requests.post(SERVER_URL, json=payload, timeout=5)
        if response.status_code == 200:
            _LOG.info("✅ Upload successful: %s", response.json())
        else:
            _LOG.warning("❌ Upload failed — Status: %s | Response: %s", response.status_code, response.text)
            upload_failed_time = time.time()
    except requests.exceptions.Timeout:
        _LOG.error("⚠️ Upload timeout.")
        upload_failed_time = time.time()
    except Exception as e:
        _LOG.exception("Unhandled error during upload: %s", e)
        upload_failed_time = time.time()

def upload_cycle():
    global events, upload_counter, upload_history
    try:
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
        _LOG.debug("upload_cycle: Uploaded #%d", upload_counter)
        save_smiley_state()
    except Exception as e:
        _LOG.exception("Unhandled error in upload_cycle: %s", e)

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

def on_vote(kind: str):
    """
    Called by UI when user votes. Updates smiley counters.
    """
    global good, meh, bad
    timestamp = time.time()
    if kind == "good":
        good += 1
    elif kind == "meh":
        meh += 1
    elif kind == "bad":
        bad += 1
    events.append({"kind": kind, "timestamp": timestamp})

def on_upload():
    upload_cycle()

# =========================================================
# ================ START UI when run directly =============
# =========================================================
if __name__ == "__main__":
    try:
        args = parser.parse_args()
        POLL_INTERVAL = args.interval
        sensor.start(poll_interval=POLL_INTERVAL, use_scd=args.use_scd, use_bme=args.use_bme, use_mic=args.use_mic)
    except Exception as e:
        _LOG.exception("Fatal startup error: %s", e)
        try:
            sensor.stop()
        except Exception:
            pass
