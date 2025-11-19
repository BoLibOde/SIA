#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
device.py

Hauptlogik, Sensor-Start/Stop, Uploads und Smiley-Logik.
Die Pygame-UI ist in ui.py; device.py liefert nur die Zustands-API (ohne Surfaces).
"""
import time
import json
import requests
import threading
import os
import argparse
import logging
from datetime import datetime

import sensor
import ui  # unsere UI-Datei (ui.run wird später aufgerufen)

# --- Konfiguration ---
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

# --- Command line args ---
parser = argparse.ArgumentParser(description="SIA Client (Smiley + Sensoranzeige)")
parser.add_argument("--interval", "-i", type=float, default=2.0, help="Sensor Poll-Intervall in Sekunden (default 2.0)")
parser.add_argument("--use-scd", action="store_true", help="SCD4x (SCD40/SCD41) verwenden, falls vorhanden")
parser.add_argument("--use-bme", action="store_true", help="BME280 als Temperaturquelle verwenden, falls vorhanden")
args = parser.parse_args()

POLL_INTERVAL = args.interval
USE_SCD = args.use_scd
USE_BME = args.use_bme

# Start sensor thread/module
sensor.start(poll_interval=POLL_INTERVAL, use_scd=USE_SCD, use_bme=USE_BME)

# =========================================================
# ================ DATENSTRUKTUREN ========================
# =========================================================
events = []
upload_history = []
upload_counter = 0

# Smiley / Override (hier nur kinds: "good"/"meh"/"bad" bzw. None)
current_smiley_kind = None
smiley_override_time = 0.0
SMILEY_OVERRIDE_DURATION = 3

# Upload failure indicator
upload_failed_time = 0
UPLOAD_FAILED_DURATION = 2.0

# =========================================================
# ================ SMILEY: Persistente Logik =============
# =========================================================
SMILEY_EMA_ALPHA = 0.20
SMILEY_NEUTRAL_ZONE = 0.12
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
        _LOG.warning("Failed to load smiley state: %s", e)
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
    except Exception as e:
        _LOG.warning("Failed to save smiley state: %s", e)

load_smiley_state()

# Rotation state for ties -> now used to rotate through ALL three variants continuously
ROTATION_ORDER = ["good", "meh", "bad"]
ROTATION_INTERVAL = 1.5  # seconds between rotation steps
_rotation_idx = 0
_rotation_last = time.time()

def pct_round(good, meh, bad):
    total = good + meh + bad
    if total == 0:
        return (0,0,0)
    raw = [good * 100.0 / total, meh * 100.0 / total, bad * 100.0 / total]
    rounded = [int(r) for r in raw]
    diff = 100 - sum(rounded)
    if diff > 0:
        idx = max(range(3), key=lambda i: raw[i] - rounded[i])
        rounded[idx] += diff
    return tuple(rounded)

def calculate_avg_smiley_kind(good, meh, bad):
    """
    Neue Behavior:
    - Ignoriere Counts für die Auswahl des großen Smileys.
    - Rotiere kontinuierlich durch alle drei Varianten (good/meh/bad).
    - Gebe trotzdem die Prozentwerte zurück, damit die UI sie anzeigen kann.
    Rückgabe: (kind_string, (pct_good,pct_meh,pct_bad))
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
# ================ HILFSFUNKTIONEN =======================
# =========================================================
def load_daily_totals():
    today = datetime.now()
    dir_path = os.path.join(BASE_DIR, today.strftime("%Y"), today.strftime("%m"), today.strftime("%d"))
    totals_file = os.path.join(dir_path, "totals.json")
    if os.path.exists(totals_file):
        try:
            with open(totals_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {"good":0,"meh":0,"bad":0,"avg_sensor_day":{"temp":0,"db":0,"co2":0,"voc":0,"count":0}}
    return {"good":0,"meh":0,"bad":0,"avg_sensor_day":{"temp":0,"db":0,"co2":0,"voc":0,"count":0}}

def avg_sensor_values():
    buf = sensor.sensor_buffer
    if not buf:
        return {"temp":0,"db":0,"co2":0,"voc":0}
    t = sum(s[0] for s in buf)/len(buf)
    d = sum(s[1] for s in buf)/len(buf)
    c = sum(s[2] for s in buf)/len(buf)
    v = sum(s[3] for s in buf)/len(buf)
    return {"temp":round(t,1),"db":round(d,1),"co2":int(c),"voc":int(v)}

def upload_to_server(avg_sensor, events):
    global upload_failed_time
    payload = {"device_id": DEVICE_ID, "events": events, "avg_sensor": avg_sensor}
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

# Counters stored in module-level vars so callbacks can modify them
good = meh = bad = 0

def get_counts():
    return good, meh, bad

def get_override_info():
    # returns (current_smiley_kind, smiley_override_time, SMILEY_OVERRIDE_DURATION)
    return current_smiley_kind, smiley_override_time, SMILEY_OVERRIDE_DURATION

def get_upload_info():
    return upload_failed_time, UPLOAD_FAILED_DURATION

def get_latest_sensor():
    if sensor.sensor_buffer:
        try:
            t, d, c, v, _ = sensor.sensor_buffer[-1]
            return t, d, c, v
        except Exception:
            pass
    return (22.0, 45.0, 410, 10)

def on_vote(kind):
    """
    Wird von UI aufgerufen, wenn Nutzer g/m/b drückt.
    Aktualisiert lokale Zähler, Events und Override (nur kinds, keine Surfaces).
    """
    global good, meh, bad, current_smiley_kind, smiley_override_time
    ts = time.time()
    if kind == "good":
        good += 1
        current_smiley_kind = "good"
        events.append({"type":"good","timestamp":ts})
    elif kind == "meh":
        meh += 1
        current_smiley_kind = "meh"
        events.append({"type":"meh","timestamp":ts})
    elif kind == "bad":
        bad += 1
        current_smiley_kind = "bad"
        events.append({"type":"bad","timestamp":ts})
    smiley_override_time = ts

def on_upload():
    upload_cycle()

# =========================================================
# ================ START UI (blockierend) =================
# =========================================================
ui.run(
    get_counts=get_counts,
    get_override_info=get_override_info,
    get_upload_info=get_upload_info,
    get_latest_sensor=get_latest_sensor,
    calculate_avg_smiley=calculate_avg_smiley_kind,
    pct_round=pct_round,
    on_vote=on_vote,
    on_upload=on_upload
)

# Aufräumen nach UI-Ende
sensor.stop()
save_smiley_state()
upload_cycle()