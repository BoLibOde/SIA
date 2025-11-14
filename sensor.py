#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sensor.py

Separate Sensor module for SIA project.

Provides:
- SensorHub: encapsulates CCS811 + optional SCD4x (SCD41) + optional BME280.
- start(poll_interval, use_scd, use_bme): starts a daemon thread that periodically reads sensors
  and appends tuples (temp, db, co2, voc, timestamp) to sensor_buffer.
- stop(): stops the thread and cleans up sensors.
- sensor_buffer: a list shared with callers (max length capped).

Behavior:
- If Adafruit/CircuitPython libs and I2C are available, uses real sensors.
- Otherwise falls back to simulator values (matching original behavior).
"""

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from adafruit_bme280 import Adafruit_BME280_I2C  # type: ignore
    import adafruit_ccs811  # type: ignore
    import adafruit_scd4x  # type: ignore

import importlib
import time
import threading
import random
import logging

_LOG = logging.getLogger("sensor")
logging.basicConfig(level=logging.INFO)

sensor_buffer = []   # list of tuples (temp, db, co2, voc, timestamp)
_MAX_BUFFER = 500

def _try_import(module_name: str, attr: str = None):
    try:
        mod = importlib.import_module(module_name)
        return getattr(mod, attr) if attr else mod
    except Exception:
        return None

board = _try_import("board")
busio = _try_import("busio")
adafruit_ccs811 = _try_import("adafruit_ccs811")
Adafruit_BME280_I2C = _try_import("adafruit_bme280", "Adafruit_BME280_I2C")
adafruit_scd4x = _try_import("adafruit_scd4x")

_sensor_hub = None
_sensor_thread = None
_stop_event = threading.Event()
_hub_available = False
_lock = threading.Lock()

class SensorHub:
    def __init__(self, use_scd=False, use_bme=False):
        if board is None or busio is None:
            raise RuntimeError("I2C/board not available")

        self.use_scd = use_scd and (adafruit_scd4x is not None)
        self.use_bme = use_bme and (Adafruit_BME280_I2C is not None)
        self.i2c = None
        self.ccs = None
        self.scd = None
        self.bme = None

        try:
            self.i2c = busio.I2C(board.SCL, board.SDA)
        except Exception as e:
            _LOG.exception("I2C init failed: %s", e)
            raise

        if adafruit_ccs811 is None:
            raise RuntimeError("adafruit-circuitpython-ccs811 not installed")
        try:
            self.ccs = adafruit_ccs811.CCS811(self.i2c)
            start = time.time()
            while not getattr(self.ccs, "data_ready", True) and time.time() - start < 5.0:
                time.sleep(0.05)
        except Exception as e:
            _LOG.exception("CCS811 init failed: %s", e)
            raise

        if self.use_bme:
            try:
                self.bme = Adafruit_BME280_I2C(self.i2c)
            except Exception:
                _LOG.exception("BME280 init failed; continuing without BME")
                self.bme = None
                self.use_bme = False

        if self.use_scd:
            try:
                self.scd = adafruit_scd4x.SCD4X(self.i2c)
                try:
                    self.scd.start_periodic_measurement()
                except Exception:
                    pass
                start = time.time()
                while getattr(self.scd, "data_ready", True) is False and time.time() - start < 5.0:
                    time.sleep(0.05)
            except Exception:
                _LOG.exception("SCD4x init failed; continuing without SCD")
                self.scd = None
                self.use_scd = False

    def read_once(self):
        result = {
            "ccs_eco2": None,
            "ccs_tvoc": None,
            "scd_co2": None,
            "scd_temp_c": None,
            "scd_rh_pct": None,
            "temp_source": None,
        }

        try:
            if self.scd is not None:
                result["scd_co2"] = getattr(self.scd, "co2", None)
                result["scd_temp_c"] = getattr(self.scd, "temperature", None)
                result["scd_rh_pct"] = getattr(self.scd, "relative_humidity", None)
                if result["scd_temp_c"] is not None:
                    result["temp_source"] = "scd"
        except Exception:
            _LOG.exception("SCD read failed")

        if result["temp_source"] is None and self.bme is not None:
            try:
                t = self.bme.temperature
                result["scd_temp_c"] = t
                result["temp_source"] = "bme"
            except Exception:
                _LOG.exception("BME read failed")

        try:
            if result["scd_temp_c"] is not None:
                try:
                    self.ccs.temperature = float(result["scd_temp_c"])
                except Exception:
                    pass
        except Exception:
            pass

        try:
            if getattr(self.ccs, "data_ready", True):
                result["ccs_eco2"] = getattr(self.ccs, "eco2", None)
                result["ccs_tvoc"] = getattr(self.ccs, "tvoc", None)
        except Exception:
            _LOG.exception("CCS read failed")

        return result

    def close(self):
        try:
            if self.scd is not None:
                try:
                    self.scd.stop_periodic_measurement()
                except Exception:
                    pass
        except Exception:
            _LOG.exception("Error during SCD shutdown")

def _sensor_loop(poll_interval, use_scd, use_bme):
    global _sensor_hub, _hub_available
    if board is not None and adafruit_ccs811 is not None:
        try:
            _sensor_hub = SensorHub(use_scd=use_scd, use_bme=use_bme)
            _hub_available = True
            _LOG.info("SensorHub initialized (real sensors).")
        except Exception as e:
            _LOG.warning("SensorHub initialization failed, falling back to simulator: %s", e)
            _sensor_hub = None
            _hub_available = False
    else:
        _LOG.info("No CircuitPython environment or libs -> using simulator.")

    while not _stop_event.is_set():
        ts = time.time()
        if _hub_available and _sensor_hub is not None:
            try:
                s = _sensor_hub.read_once()
                temp = float(s.get("scd_temp_c") or 22.0)
                co2_from_scd = s.get("scd_co2")
                co2_from_ccs = s.get("ccs_eco2")
                co2 = int(co2_from_scd or co2_from_ccs or 410)
                tvoc = int(s.get("ccs_tvoc") or 0)
                db = random.uniform(35.0, 55.0)
                voc = tvoc if tvoc else random.randint(5, 20)
            except Exception:
                _LOG.exception("Error reading SensorHub; using simulator values")
                temp = random.uniform(20.0, 25.0)
                db = random.uniform(35.0, 55.0)
                co2 = random.randint(390, 430)
                voc = random.randint(5, 20)
        else:
            temp = random.uniform(20.0, 25.0)
            db = random.uniform(35.0, 55.0)
            co2 = random.randint(390, 430)
            voc = random.randint(5, 20)

        with _lock:
            sensor_buffer.append((round(float(temp), 2), round(float(db), 1), int(co2), int(voc), ts))
            if len(sensor_buffer) > _MAX_BUFFER:
                sensor_buffer.pop(0)

        _stop_event.wait(poll_interval)

    try:
        if _sensor_hub is not None:
            _sensor_hub.close()
    except Exception:
        pass
    _LOG.info("Sensor loop stopped.")

def start(poll_interval=2.0, use_scd=False, use_bme=False):
    global _sensor_thread, _stop_event
    if _sensor_thread is not None and _sensor_thread.is_alive():
        _LOG.debug("Sensor thread already running.")
        return
    _stop_event.clear()
    _sensor_thread = threading.Thread(target=_sensor_loop, args=(poll_interval, use_scd, use_bme), daemon=True)
    _sensor_thread.start()
    _LOG.info("Sensor thread started (interval=%s, use_scd=%s, use_bme=%s)", poll_interval, use_scd, use_bme)

def stop():
    global _sensor_thread, _stop_event
    _stop_event.set()
    if _sensor_thread is not None:
        _sensor_thread.join(timeout=3.0)
    _sensor_thread = None
    _LOG.info("Sensor module stopped.")