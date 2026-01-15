#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
device.py

Main entry point for the SIA program.
- Initializes and runs the SensorRunner.
- Provides callbacks for UI integration.
- Allows switching between simulation mode and hardware mode.
"""
import os
import time
import logging
import threading
import argparse
from datetime import datetime

import requests

from sensor import SensorRunner  # Import the SensorRunner class

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO)
_LOG = logging.getLogger("device")

# --- Command-Line Arguments ---
parser = argparse.ArgumentParser(description="SIA Client (Smiley + Sensoranzeige)")
parser.add_argument("--interval", "-i", type=float, default=2.0, help="Sensor poll interval in seconds")
parser.add_argument("--use-scd", action="store_true", help="Use SCD4x (SCD40/SCD41) sensor if available")
parser.add_argument("--simulation", action="store_true", help="Use simulated sensor data instead of hardware")

# --- State Variables ---
good = meh = bad = 0
smiley_override_time = 0.0
events = []
upload_failed_time = 0
UPLOAD_FAILED_DURATION = 2.0
SMILEY_EMA_ALPHA = 0.20
smiley_ema = 0.0
upload_counter = 0

# Device-specific configurations
DEVICE_ID = os.getenv("DEVICE_ID", "default_device")
SERVER_URL = "http://127.0.0.1:5000/upload"

# --- Helper Functions ---
def avg_sensor_values():
    """Calculate averages of sensor data."""
    try:
        if not sensor_runner.sensor_buffer:
            return {"temp": 0, "db": 0, "co2": 0}
        temp = round(sum(s.temp for s in sensor_runner.sensor_buffer) / len(sensor_runner.sensor_buffer), 1)
        db = round(sum(s.db for s in sensor_runner.sensor_buffer) / len(sensor_runner.sensor_buffer), 1)
        co2 = round(sum(s.co2 for s in sensor_runner.sensor_buffer) / len(sensor_runner.sensor_buffer), 0)
        return {"temp": temp, "db": db, "co2": co2}
    except Exception as e:
        _LOG.exception("Error computing average sensor values: %s", e)
        return {"temp": 0, "db": 0, "co2": 0}

def upload_cycle():
    """Handles the upload of sensor data."""
    global events, upload_counter
    avg_sensor = avg_sensor_values()
    upload_counter += 1
    threading.Thread(
        target=upload_to_server,
        args=(avg_sensor, events.copy()),
        daemon=True
    ).start()
    events.clear()

def upload_to_server(avg_sensor, events_list):
    """Uploads sensor data to the server."""
    global upload_failed_time
    payload = {
        "device_id": DEVICE_ID,
        "events": events_list,
        "avg_sensor": avg_sensor
    }
    try:
        _LOG.info("Uploading data payload...")
        response = requests.post(SERVER_URL, json=payload, timeout=5)
        if response.status_code == 200:
            _LOG.info("Upload successful: %s", response.json())
        else:
            _LOG.warning("Upload failed with status: %s", response.text)
            upload_failed_time = time.time()
    except Exception as e:
        upload_failed_time = time.time()
        _LOG.exception("Upload error: %s", e)

def on_vote(kind: str):
    """Handles user vote input (good, meh, bad)."""
    global good, meh, bad, smiley_override_time, smiley_ema
    ts = time.time()
    if kind == "good":
        good += 1
    elif kind == "meh":
        meh += 1
    elif kind == "bad":
        bad += 1
    smiley_override_time = ts
    value = {"good": 1.0, "meh": 0.0, "bad": -1.0}.get(kind, 0.0)
    smiley_ema = SMILEY_EMA_ALPHA * value + (1 - SMILEY_EMA_ALPHA) * smiley_ema
    events.append({"kind": kind, "timestamp": ts})
    _LOG.info("Vote received: %s | Updated votes - Good: %d, Meh: %d, Bad: %d", kind, good, meh, bad)

def get_latest_sensor():
    """Fetch the latest sensor sample from the sensor buffer."""
    if sensor_runner.sensor_buffer:
        latest = sensor_runner.sensor_buffer[-1]
        _LOG.info("Latest sensor sample: %s", latest)
        return latest
    else:
        _LOG.warning("Sensor buffer is empty. Returning default.")
        return None


# --- Main Application ---
if __name__ == "__main__":
    try:
        # Parse command-line arguments
        args = parser.parse_args()
        POLL_INTERVAL = args.interval
        SIMULATION_MODE = args.simulation  # True for simulation mode
        USE_SCD = args.use_scd  # Use SCD4x sensor if available

        # Create SensorRunner instance
        sensor_runner = SensorRunner(simulation_mode=SIMULATION_MODE)

        # Start the SensorRunner
        sensor_runner.start(interval=POLL_INTERVAL)
        _LOG.info("SensorRunner started with a polling interval of %.1f seconds (Simulation: %s).",
                  POLL_INTERVAL, "ON" if SIMULATION_MODE else "OFF")

        # Start the UI
        import ui
        ui.run(
            lambda: (good, meh, bad),  # Mood counts
            lambda: ("meh", smiley_override_time, 3.0),  # Smiley override
            lambda: (upload_failed_time, UPLOAD_FAILED_DURATION),  # Upload failure info
            get_latest_sensor,  # Latest sensor data
            lambda g, m, b: ("meh", (33, 33, 33)),  # Placeholder for smiley percentages
            lambda g, m, b: (60, 20, 20),  # Placeholder for rounded percentages
            on_vote,  # User mood votes
            upload_cycle  # Trigger upload
        )
    except Exception as e:
        _LOG.exception("Fatal error in device.py: %s", e)
    finally:
        _LOG.info("Stopping SensorRunner...")
        sensor_runner.stop()
