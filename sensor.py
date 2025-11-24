#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sensor.py

Sensor module for SIA project — Pimoroni-only SCD4x version.

Notes:
- This version uses the Pimoroni scd4x Python library (module name `scd4x`) exclusively
  for SCD4x (SCD40/SCD41). Adafruit's adafruit_scd4x support has been removed.
- The module still supports CCS811 (adafruit-circuitpython-ccs811) and BME280 (adafruit-circuitpython-bme280)
  if available. MicAdapter with sounddevice fallback remains for dB on desktops/Raspberry Pi.
- On desktop/PC without I2C pins the module will run a simulator thread so device.py and the UI run
  without hardware; set SIA_FORCE_REAL_SENSORS=1 to try real hardware even if detection fails.
"""

from typing import TYPE_CHECKING, Optional, List
if TYPE_CHECKING:
    from adafruit_bme280 import Adafruit_BME280_I2C  # type: ignore

import importlib
import time
import threading
import logging
from dataclasses import dataclass
import math
import os
import random

_LOG = logging.getLogger("sensor")
logging.basicConfig(level=logging.INFO)

# Calibration offset to convert dBFS to approximate dB SPL if you have a calibration value.
_MIC_CALIB_OFFSET = float(os.environ.get("SIA_MIC_CALIB_OFFSET", "0.0"))
# Force real sensors attempt even when detection says no
_FORCE_REAL = os.environ.get("SIA_FORCE_REAL_SENSORS", "").lower() in ("1", "true", "yes")

@dataclass
class SensorSample:
    temp: float      # °C
    rh: float        # relative humidity %
    db: float        # decibel reading (dBFS by default unless calibrated)
    co2: int         # CO2 ppm
    voc: int         # TVOC / VOC reading (device-specific units)
    ts: float        # unix timestamp

# Public buffer (list of SensorSample)
sensor_buffer: List[SensorSample] = []
_MAX_BUFFER = 500

def _try_import(module_name: str, attr: str = None):
    try:
        mod = importlib.import_module(module_name)
        return getattr(mod, attr) if attr else mod
    except Exception:
        return None

# Core sensor libs (may be None if not installed)
board = _try_import("board")
busio = _try_import("busio")
adafruit_ccs811 = _try_import("adafruit_ccs811")
Adafruit_BME280_I2C = _try_import("adafruit_bme280", "Adafruit_BME280_I2C")
# NOTE: adafruit_scd4x removed intentionally; we only use Pimoroni scd4x

_sensor_hub = None
_sensor_thread = None
_stop_event = threading.Event()
_hub_available = False
_lock = threading.Lock()

# ---------- MicAdapter (unchanged behavior) ----------
class MicAdapter:
    """
    Adapter that attempts to provide a decibel reading.
    Attempt order:
      - CircuitPython adafruit_ics43434 driver (if running in Blinka/CircuitPython env)
      - sounddevice + numpy fallback on Linux/desktop
    Returns dBFS (negative for typical signals) plus optional calibration offset.
    """
    def __init__(self, sample_rate: int = 44100, duration: float = 0.1):
        self.sample_rate = sample_rate
        self.duration = duration
        self._mode = None
        self._impl = None

        # Try CircuitPython ICS43434 driver
        adafruit_ics = _try_import("adafruit_ics43434")
        audiobusio = _try_import("audiobusio")
        if adafruit_ics and audiobusio:
            try:
                self._mode = "circuitpython"
                self._impl = (adafruit_ics, audiobusio)
                _LOG.info("MicAdapter: CircuitPython ICS43434 support available.")
                return
            except Exception:
                self._mode = None
                self._impl = None

        # Fallback: sounddevice + numpy on Linux/desktop
        sounddevice = _try_import("sounddevice")
        np = _try_import("numpy")
        if sounddevice and np:
            self._mode = "sounddevice"
            self._impl = (sounddevice, np)
            _LOG.info("MicAdapter: using sounddevice + numpy for microphone capture.")
            return

        _LOG.info("MicAdapter: no microphone backend available (install adafruit_ics43434 or sounddevice+numpy).")

    def read_db(self) -> Optional[float]:
        if self._mode == "circuitpython":
            _LOG.warning("MicAdapter: CircuitPython path not implemented in desktop mode.")
            return None

        if self._mode == "sounddevice":
            sounddevice, np = self._impl
            try:
                duration = max(0.05, min(0.5, self.duration))
                frames = int(self.sample_rate * duration)
                data = sounddevice.rec(frames, samplerate=self.sample_rate, channels=1, dtype='float32')
                sounddevice.wait()
                arr = np.squeeze(data)
                if arr.size == 0:
                    return None
                rms = float(np.sqrt(np.mean(arr * arr)))
                db = 20.0 * math.log10(max(rms, 1e-12))
                db += _MIC_CALIB_OFFSET
                return db
            except Exception as e:
                _LOG.exception("MicAdapter (sounddevice) read failed: %s", e)
                return None

        return None

    def close(self):
        return

# ---------- SCD4xAdapter (Pimoroni-only) ----------
class SCD4xAdapter:
    """
    Adapter that uses Pimoroni's scd4x library (module `scd4x`) only.
    Exposes:
      - data_ready (property bool)
      - read_co2() -> int | None
      - read_temperature() -> float | None
      - read_humidity() -> float | None
      - deinit()
    """
    def __init__(self):
        self._impl = None
        self._impl_name = None

        pimoroni_mod = _try_import("scd4x")
        if pimoroni_mod is None:
            raise RuntimeError("Pimoroni scd4x library not installed (pip install scd4x)")

        # Pimoroni exposes SCD4X class
        Cls = getattr(pimoroni_mod, "SCD4X", None) or getattr(pimoroni_mod, "Scd4x", None) or getattr(pimoroni_mod, "SCD4x", None)
        if not Cls:
            raise RuntimeError("Pimoroni scd4x module found but class SCD4X not present")

        try:
            # Pimoroni driver opens SMBus(1) internally; do not pass busio.I2C
            self._impl = Cls()
            self._impl_name = "pimoroni.scd4x.SCD4X"
            if hasattr(self._impl, "start_periodic_measurement"):
                try:
                    self._impl.start_periodic_measurement()
                except Exception:
                    pass
            _LOG.info("SCD4xAdapter: initialized Pimoroni scd4x driver")
        except Exception as e:
            raise RuntimeError(f"Failed to initialize Pimoroni SCD4X: {e}") from e

    @property
    def data_ready(self) -> bool:
        impl = self._impl
        if impl is None:
            return False
        try:
            return bool(impl.data_ready())
        except Exception:
            # fallback: assume ready
            return True

    def read_co2(self) -> Optional[int]:
        impl = self._impl
        if impl is None:
            return None
        try:
            co2, _, _, _ = impl.measure()
            return int(co2)
        except Exception:
            _LOG.exception("SCD4xAdapter: measure() failed when reading CO2")
            return None

    def read_temperature(self) -> Optional[float]:
        impl = self._impl
        if impl is None:
            return None
        try:
            _, temp, _, _ = impl.measure()
            return float(temp)
        except Exception:
            _LOG.exception("SCD4xAdapter: measure() failed when reading temperature")
            return None

    def read_humidity(self) -> Optional[float]:
        impl = self._impl
        if impl is None:
            return None
        try:
            _, _, rh, _ = impl.measure()
            return float(rh)
        except Exception:
            _LOG.exception("SCD4xAdapter: measure() failed when reading humidity")
            return None

    def deinit(self):
        impl = self._impl
        if impl and hasattr(impl, "stop_periodic_measurement"):
            try:
                impl.stop_periodic_measurement()
            except Exception:
                pass

# ---------- SensorHub ----------
class SensorHub:
    """
    Encapsulates CCS811 + Pimoroni SCD4x + optional BME280 + optional microphone adapter.
    Constructing this will attempt to initialize I2C devices and mic.
    """
    def __init__(self, use_scd=False, use_bme=False, use_mic=False):
        if board is None or busio is None:
            raise RuntimeError("I2C/board support not available")

        # require that board exposes SCL and SDA to consider I2C usable
        if not (hasattr(board, "SCL") and hasattr(board, "SDA")):
            raise RuntimeError("I2C pins not present on this platform")

        self.use_scd = use_scd
        self.use_bme = use_bme and (Adafruit_BME280_I2C is not None)
        self.use_mic = use_mic
        self.i2c = None
        self.ccs = None
        self.scd = None
        self.bme = None
        self.mic = None

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

        if self.use_scd:
            try:
                # Pimoroni-only adapter
                self.scd = SCD4xAdapter()
            except Exception as e:
                _LOG.exception("SCD4x init failed; continuing without SCD: %s", e)
                self.scd = None

        if self.use_mic:
            try:
                self.mic = MicAdapter()
            except Exception as e:
                _LOG.exception("MicAdapter init failed: %s", e)
                self.mic = None

    def deinit(self):
        try:
            if self.mic:
                self.mic.close()
        except Exception:
            pass
        try:
            if self.scd:
                self.scd.deinit()
        except Exception:
            pass

# ---------- Polling loops ----------
def _real_poll_loop(hub: SensorHub, poll_interval: float):
    global sensor_buffer, _stop_event, _MAX_BUFFER
    _LOG.info("Sensor thread started (real sensors, poll_interval=%.2f)", poll_interval)
    while not _stop_event.is_set():
        ts = time.time()
        temp = None
        rh = None
        co2 = None
        voc = None
        db = None

        # Read SCD4x if available (CO2, temperature, humidity)
        if hub.scd:
            try:
                if hub.scd.data_ready:
                    co2 = hub.scd.read_co2()
                    temp = hub.scd.read_temperature()
                    rh = hub.scd.read_humidity()
            except Exception:
                _LOG.exception("Error reading SCD4x sensor")

        # Read BME280 if available (overrides temperature/humidity if present)
        if hub.bme:
            try:
                temp = float(getattr(hub.bme, "temperature", temp))
                rh = float(getattr(hub.bme, "relative_humidity", rh))
            except Exception:
                _LOG.exception("Error reading BME280")

        # Read CCS811 (TVOC / eCO2)
        if hub.ccs:
            try:
                co2 = co2 or int(getattr(hub.ccs, "eco2", getattr(hub.ccs, "eCO2", None) or co2 or 0))
                voc = int(getattr(hub.ccs, "tvoc", getattr(hub.ccs, "TVOC", getattr(hub.ccs, "voc", 0))))
            except Exception:
                _LOG.exception("Error reading CCS811")

        # Read microphone dB if available
        if hub.mic:
            try:
                dbv = hub.mic.read_db()
                if dbv is not None:
                    db = float(dbv)
            except Exception:
                _LOG.exception("Error reading microphone")

        # Fill defaults if missing (preserve previous defaults)
        if temp is None:
            temp = 22.0
        if rh is None:
            rh = 45.0
        if co2 is None:
            co2 = 410
        if voc is None:
            voc = 10
        if db is None:
            db = 0.0

        sample = SensorSample(temp=float(temp), rh=float(rh), db=float(db), co2=int(co2), voc=int(voc), ts=ts)
        with _lock:
            sensor_buffer.append(sample)
            if len(sensor_buffer) > _MAX_BUFFER:
                sensor_buffer[:] = sensor_buffer[-_MAX_BUFFER:]
        time.sleep(poll_interval)

def _simulator_poll_loop(poll_interval: float, use_mic: bool):
    """
    Simulator loop for desktop development. Generates plausible synthetic sensor values.
    If mic backend exists and use_mic is True, will try to read dB from MicAdapter.
    """
    global sensor_buffer, _stop_event, _MAX_BUFFER
    _LOG.info("Sensor thread started (simulator mode, poll_interval=%.2f)", poll_interval)

    mic = None
    if use_mic:
        try:
            mic = MicAdapter()
            if mic._mode is None:
                mic = None
        except Exception:
            mic = None

    while not _stop_event.is_set():
        ts = time.time()
        temp = 22.0 + random.uniform(-1.0, 1.0)
        rh = 45.0 + random.uniform(-5.0, 5.0)
        co2 = int(410 + max(0, random.gauss(0, 40)))
        voc = int(max(0, random.gauss(20, 10)))
        db = 0.0
        if mic:
            try:
                dbv = mic.read_db()
                if dbv is not None:
                    db = float(dbv)
                else:
                    db = 30.0 + random.uniform(-6.0, 6.0)
            except Exception:
                db = 30.0 + random.uniform(-6.0, 6.0)
        else:
            db = 30.0 + random.uniform(-6.0, 6.0)

        sample = SensorSample(temp=temp, rh=rh, db=db, co2=co2, voc=voc, ts=ts)
        with _lock:
            sensor_buffer.append(sample)
            if len(sensor_buffer) > _MAX_BUFFER:
                sensor_buffer[:] = sensor_buffer[-_MAX_BUFFER:]
        time.sleep(poll_interval)

# ---------- Public API: start / stop ----------
def _i2c_available() -> bool:
    """
    Determine if I2C-based sensors are likely usable on this system.
    Heuristic: board and busio modules exist and board exposes SCL/SDA.
    """
    if board is None or busio is None:
        return False
    if not (hasattr(board, "SCL") and hasattr(board, "SDA")):
        return False
    return True

def start(poll_interval: float = 2.0, use_scd: bool = False, use_bme: bool = False, use_mic: bool = False):
    """
    Start sensor polling thread.
    Automatically runs in simulator mode on desktop/PC when I2C pins are not available,
    unless environment variable SIA_FORCE_REAL_SENSORS is set to 1/true.
    """
    global _sensor_hub, _sensor_thread, _stop_event, _hub_available

    if _sensor_thread and _sensor_thread.is_alive():
        _LOG.info("Sensor thread already running")
        return

    _stop_event.clear()

    real_possible = _i2c_available()
    if _FORCE_REAL:
        _LOG.info("SIA_FORCE_REAL_SENSORS set; attempting real sensor init even if I2C detection failed.")
        real_possible = True

    if real_possible:
        # attempt to start real sensor hub; on failure fall back to simulator
        try:
            _sensor_hub = SensorHub(use_scd=use_scd, use_bme=use_bme, use_mic=use_mic)
            _sensor_thread = threading.Thread(target=_real_poll_loop, args=(_sensor_hub, poll_interval), daemon=True)
            _sensor_thread.start()
            _hub_available = True
            _LOG.info("Started real sensor hub")
            return
        except Exception as e:
            _LOG.warning("Failed to start real SensorHub (%s) — falling back to simulator", e)
            _sensor_hub = None
            _hub_available = False

    # Start simulator thread
    _sensor_thread = threading.Thread(target=_simulator_poll_loop, args=(poll_interval, use_mic), daemon=True)
    _sensor_thread.start()
    _hub_available = False
    _LOG.info("Started simulator sensor thread (no hardware)")

def stop():
    global _sensor_hub, _sensor_thread, _stop_event, _hub_available
    _stop_event.set()
    try:
        if _sensor_hub:
            _sensor_hub.deinit()
    except Exception:
        pass
    _sensor_thread = None
    _sensor_hub = None
    _hub_available = False