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
- Requires Adafruit/CircuitPython libs and I2C to be available. Simulator fallback has been
  intentionally disabled so only real sensors can be used.
"""

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from adafruit_bme280 import Adafruit_BME280_I2C  # type: ignore
    import adafruit_ccs811  # type: ignore
    import adafruit_scd4x  # type: ignore

import importlib
import time
import threading
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

    # Simulator fallback intentionally disabled: require real hardware/libs.
    if board is None or adafruit_ccs811 is None:
        _LOG.error("CircuitPython environment or required libs not available; simulator is disabled. Exiting sensor loop.")
        return

    try:
        _sensor_hub = SensorHub(use_scd=use_scd, use_bme=use_bme)
        _hub_available = True
        _LOG.info("SensorHub initialized (real sensors).")
    except Exception as e:
        _LOG.exception("SensorHub initialization failed and simulator is disabled: %s", e)
        return

    while not _stop_event.is_set():
        ts = time.time()
        try:
            s = _sensor_hub.read_once()

            # Require actual sensor values. If critical values are missing, stop.
            temp = s.get("scd_temp_c")
            co2_from_scd = s.get("scd_co2")
            co2_from_ccs = s.get("ccs_eco2")

            if temp is None:
                _LOG.error("Temperature not available from sensors; stopping sensor loop (simulator disabled).")
                break

            co2_val = co2_from_scd if co2_from_scd is not None else co2_from_ccs
            if co2_val is None:
                _LOG.error("CO2 not available from sensors; stopping sensor loop (simulator disabled).")
                break

            # tvoc might be absent; default to 0 when missing (not a simulator fallback).
            tvoc = s.get("ccs_tvoc") or 0

            # db (decibel) measurement is not provided by these sensors. Set to 0.0 to keep tuple shape.
            db = 0.0
            voc = int(tvoc)

            # Append the measured values (rounded to existing format)
            with _lock:
                sensor_buffer.append((round(float(temp), 2), round(float(db), 1), int(co2_val), int(voc), ts))
                if len(sensor_buffer) > _MAX_BUFFER:
                    sensor_buffer.pop(0)

        except Exception:
            _LOG.exception("Error reading SensorHub; stopping sensor loop (simulator disabled).")
            break

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