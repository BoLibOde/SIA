#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sensor.py

Provides a simple sensor runner that device.py imports and calls:

- start(poll_interval=2.0, use_scd=False, use_bme=False, use_mic=False)
- stop()
- sensor_buffer (list of SensorSample objects / tuples)

Behavior:
- Attempts to use a CCS811 (I2C) for eCO2 / TVOC.
- Restores baseline from disk (if present) during initialization so you don't need
  to re-burn every start.
- Periodically saves baseline to disk (hourly) while running.
- If CCS811 or smbus isn't available (desktop), falls back to a simple simulator
  that produces plausible eCO2/TVOC values.
- Always appends samples containing (temp, db, co2, voc, ts) so device.py's
  aggregation functions work unchanged.
"""
from dataclasses import dataclass
import time
import threading
import os
import math
import random
import logging

_LOG = logging.getLogger("sensor")
logging.getLogger("smbus").setLevel(logging.WARNING)

# --- Public buffer (device.py reads sensor.sensor_buffer) ---
sensor_buffer = []

# --- Sample dataclass ---
@dataclass
class SensorSample:
    temp: float   # degrees C
    db: float     # decibels (mic input) or 0 if not used
    co2: int      # eCO2 ppm
    voc: int      # TVOC ppb
    ts: float     # epoch timestamp

# --- CCS811 specifics ---
try:
    import smbus
    SMBUS_AVAILABLE = True
except Exception:
    SMBUS_AVAILABLE = False

# CCS811 registers / commands / masks
_CCS_ADDR_DEFAULT = 0x5A
_CCS_REG_STATUS = 0x00
_CCS_REG_MEAS_MODE = 0x01
_CCS_REG_ALG_RESULT_DATA = 0x02
_CCS_REG_BASELINE = 0x11
_CCS_REG_HW_ID = 0x20
_CCS_CMD_APP_START = 0xF4

_CCS_STATUS_DATA_READY = 0x08
_CCS_STATUS_ERROR = 0x01
_CCS_STATUS_APP_VALID = 0x10

# drive mode values
_DRIVE_MODE_VALUES = {0:0x00, 1:0x10, 2:0x20, 3:0x30, 4:0x40}

# default baseline file (relative to module directory)
_BASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(_BASE_DIR, exist_ok=True)
_DEFAULT_BASELINE_FILE = os.path.join(_BASE_DIR, "ccs811_baseline.bin")

# max buffer size
_MAX_BUFFER = 600  # keep recent samples (e.g. 2*polls per sec * minutes)

# --- CCS811 wrapper ---
class CCS811:
    def __init__(self, busnum=1, address=_CCS_ADDR_DEFAULT, baseline_file=_DEFAULT_BASELINE_FILE, logger=_LOG):
        self.busnum = busnum
        self.address = address
        self.baseline_file = baseline_file
        self.logger = logger
        self.bus = None
        self.inited = False

        if not SMBUS_AVAILABLE:
            raise RuntimeError("smbus not available on this platform")

        try:
            self.bus = smbus.SMBus(self.busnum)
        except Exception as e:
            raise RuntimeError(f"Failed to open I2C bus {self.busnum}: {e}")

    # low-level safe wrappers
    def _read_byte(self, reg, retries=3, delay=0.05):
        for i in range(retries):
            try:
                return self.bus.read_byte_data(self.address, reg)
            except OSError:
                if i < retries - 1:
                    time.sleep(delay)
                    continue
                raise

    def _read_block(self, reg, length, retries=3, delay=0.05):
        for i in range(retries):
            try:
                return self.bus.read_i2c_block_data(self.address, reg, length)
            except OSError:
                if i < retries - 1:
                    time.sleep(delay)
                    continue
                raise

    def _write_block(self, reg, data, retries=3, delay=0.05):
        for i in range(retries):
            try:
                return self.bus.write_i2c_block_data(self.address, reg, data)
            except OSError:
                if i < retries - 1:
                    time.sleep(delay)
                    continue
                raise

    def init(self, restore_baseline=True, drive_mode=1, interrupt=False):
        """
        Initialize CCS811:
        - check HW_ID
        - check APP_VALID in STATUS
        - send APP_START
        - optionally restore baseline
        - set MEAS_MODE
        """
        hw = self._read_byte(_CCS_REG_HW_ID)
        if hw != 0x81:
            raise RuntimeError(f"Unexpected HW_ID 0x{hw:02X} (expected 0x81)")

        status = self._read_byte(_CCS_REG_STATUS)
        if not (status & _CCS_STATUS_APP_VALID):
            raise RuntimeError(f"APP_VALID not set (STATUS=0x{status:02X}) - application firmware missing")

        # APP_START (command, no payload). For I2C write_byte is ok
        # but smbus write_byte takes address and value; use bus methods:
        try:
            self.bus.write_byte(self.address, _CCS_CMD_APP_START)
            time.sleep(0.1)
        except Exception as e:
            raise RuntimeError(f"Failed to send APP_START: {e}")

        # optional baseline restore
        if restore_baseline and os.path.exists(self.baseline_file):
            try:
                b = self._load_baseline_file(self.baseline_file)
                if b is not None:
                    # write baseline to register 0x11 (two bytes)
                    msb = (b >> 8) & 0xFF
                    lsb = b & 0xFF
                    self._write_block(_CCS_REG_BASELINE, [msb, lsb])
                    time.sleep(0.05)
                    self.logger.info("Restored baseline 0x%04X from %s", b, self.baseline_file)
            except Exception as e:
                self.logger.warning("Failed to restore baseline: %s", e)

        # set MEAS_MODE
        val = _DRIVE_MODE_VALUES.get(drive_mode, 0x10)
        if interrupt:
            val |= 0x08
        try:
            self.bus.write_byte_data(self.address, _CCS_REG_MEAS_MODE, val)
            time.sleep(0.05)
        except Exception as e:
            raise RuntimeError(f"Failed to set MEAS_MODE: {e}")

        self.inited = True
        self.logger.info("CCS811 initialized at 0x%02X (mode=%d, interrupt=%s)", self.address, drive_mode, interrupt)

    def read(self):
        """
        Read ALG_RESULT_DATA (8 bytes) and return (eco2, tvoc, status, error_id, raw)
        """
        raw = self._read_block(_CCS_REG_ALG_RESULT_DATA, 8)
        eco2 = (raw[0] << 8) | raw[1]
        tvoc = (raw[2] << 8) | raw[3]
        status = raw[4]
        error_id = raw[5]
        return eco2, tvoc, status, error_id, raw

    def read_baseline(self):
        b = self._read_block(_CCS_REG_BASELINE, 2)
        return (b[0] << 8) | b[1]

    def save_baseline_file(self, path=None):
        path = path or self.baseline_file
        try:
            b = self.read_baseline()
            # atomic write
            d = os.path.dirname(path)
            if d and not os.path.exists(d):
                os.makedirs(d, exist_ok=True)
            tmp = path + ".tmp"
            with open(tmp, "wb") as f:
                f.write(bytes([(b >> 8) & 0xFF, b & 0xFF]))
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
            self.logger.info("Saved baseline 0x%04X to %s", b, path)
            return b
        except Exception as e:
            self.logger.warning("Failed to save baseline to %s: %s", path, e)
            raise

    @staticmethod
    def _load_baseline_file(path):
        try:
            with open(path, "rb") as f:
                data = f.read()
            if len(data) != 2:
                return None
            return (data[0] << 8) | data[1]
        except Exception:
            return None

# --- Simulator (used when no smbus / no hardware) ---
class Simulator:
    def __init__(self):
        # start near ambient values
        self.co2 = 415 + random.randint(-10, 10)
        self.tvoc = 10 + random.randint(-3, 3)
        self.t = 22.0 + random.random() - 0.5
        self.db = 0.0

    def init(self, *a, **k):
        _LOG.info("CCS811 simulator initialized")

    def read(self):
        # slowly vary values
        self.co2 += int(random.gauss(0, 1))
        self.tvoc += int(random.gauss(0, 1))
        self.co2 = max(400, min(5000, self.co2))
        self.tvoc = max(0, min(60000, self.tvoc))
        status = _CCS_STATUS_DATA_READY | _CCS_STATUS_APP_VALID
        raw = [ (self.co2 >> 8) & 0xFF, self.co2 & 0xFF,
                (self.tvoc >> 8) & 0xFF, self.tvoc & 0xFF,
                status, 0x00, 0x00, 0x00 ]
        return self.co2, self.tvoc, status, 0x00, raw

    def read_baseline(self):
        # return synthetic baseline
        return 0xA000

    def save_baseline_file(self, path=None):
        # noop for simulator
        return None

# --- Runner thread / public start/stop API ---
class SensorRunner:
    def __init__(self, poll_interval=2.0, use_scd=False, use_bme=False, use_mic=False,
                 ccs_bus=1, ccs_addr=_CCS_ADDR_DEFAULT, baseline_file=_DEFAULT_BASELINE_FILE,
                 baseline_save_interval=3600):
        self.poll_interval = max(0.1, float(poll_interval))
        self.use_scd = use_scd
        self.use_bme = use_bme
        self.use_mic = use_mic
        self.ccs = None
        self.running = False
        self.thread = None
        self.lock = threading.Lock()

        # baseline config
        self.baseline_file = baseline_file
        self.baseline_save_interval = baseline_save_interval

        # hardware config
        self.ccs_bus = ccs_bus
        self.ccs_addr = ccs_addr

        # simulation fallback
        self.simulator = None

    def _init_ccs(self):
        if not SMBUS_AVAILABLE:
            self.simulator = Simulator()
            self.simulator.init()
            self.ccs = self.simulator
            return

        try:
            self.ccs = CCS811(busnum=self.ccs_bus, address=self.ccs_addr, baseline_file=self.baseline_file)
            # restore baseline (if present) and start in 1s mode
            self.ccs.init(restore_baseline=True, drive_mode=1, interrupt=False)
        except Exception as e:
            _LOG.warning("CCS811 init failed: %s — falling back to simulator", e)
            self.simulator = Simulator()
            self.simulator.init()
            self.ccs = self.simulator

    def start(self):
        if self.running:
            return
        self.running = True
        self._init_ccs()
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        _LOG.info("SensorRunner started (poll_interval=%.2f)", self.poll_interval)

    def stop(self):
        if not self.running:
            return
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)
        _LOG.info("SensorRunner stopped")

    def _append_sample(self, temp, db, co2, voc):
        s = SensorSample(temp=float(temp), db=float(db), co2=int(co2), voc=int(voc), ts=time.time())
        with self.lock:
            sensor_buffer.append(s)
            # trim buffer
            if len(sensor_buffer) > _MAX_BUFFER:
                del sensor_buffer[0: len(sensor_buffer) - _MAX_BUFFER]

    def _decode_error(self, err):
        msgs = []
        if err & 0x01: msgs.append("MSG_INVALID")
        if err & 0x02: msgs.append("APP_INVALID")
        if err & 0x04: msgs.append("HEATER_SUPPLY")
        if err & 0x08: msgs.append("HEATER_FAULT")
        if err & 0x10: msgs.append("MAX_RESISTANCE")
        return msgs or [f"UNKNOWN(0x{err:02X})"]

    def _loop(self):
        last_baseline_save = time.time()
        # starting temp/db placeholders (could hook BME or mic here)
        temp = 22.0
        db = 0.0

        # small warmup delay so device is ready
        time.sleep(0.2)

        while self.running:
            try:
                co2 = 0
                tvoc = 0
                try:
                    eco2, tvoc, status, errid, raw = self.ccs.read()
                except Exception as e:
                    # transient read failure -> attempt reinit once
                    _LOG.warning("CCS read failed: %s", e)
                    # attempt re-init for hardware backend
                    if isinstance(self.ccs, CCS811):
                        try:
                            self.ccs.init(restore_baseline=True, drive_mode=1)
                            eco2, tvoc, status, errid, raw = self.ccs.read()
                        except Exception as e2:
                            _LOG.error("Re-init/read failed: %s", e2)
                            # fall back to simulator to keep app running
                            self.simulator = Simulator()
                            self.simulator.init()
                            self.ccs = self.simulator
                            eco2, tvoc, status, errid, raw = self.ccs.read()
                    else:
                        # simulator error unlikely
                        raise

                # check status/error
                if status & _CCS_STATUS_ERROR:
                    # read error id if available and log
                    dec = self._decode_error(errid)
                    _LOG.warning("CCS reported ERROR (STATUS=0x%02X) ERROR_ID=0x%02X -> %s", status, errid, ", ".join(dec))
                    # if APP_INVALID error (0x02), try re-init once
                    if errid & 0x02 and isinstance(self.ccs, CCS811):
                        _LOG.info("APP_INVALID detected, attempting re-init")
                        try:
                            self.ccs.init(restore_baseline=True, drive_mode=1)
                        except Exception as e:
                            _LOG.error("Re-init after APP_INVALID failed: %s", e)

                # produce sample values (temperature & db are placeholders here)
                co2 = eco2
                voc = tvoc
                # temp/db: if BME or mic implemented, read here. For now keep stable temp and db.
                # Add slight ambient drift on long runs
                temp += (random.random() - 0.5) * 0.02
                db = db * 0.98 + random.random() * 0.5

                self._append_sample(temp, db, co2, voc)

                # periodic baseline save
                if self.baseline_file and (time.time() - last_baseline_save) >= self.baseline_save_interval:
                    try:
                        if isinstance(self.ccs, CCS811):
                            b = self.ccs.save_baseline_file(self.baseline_file)
                            _LOG.debug("Periodic baseline saved: 0x%04X", b if b is not None else 0)
                        else:
                            # simulator - noop
                            pass
                    except Exception as e:
                        _LOG.warning("Failed to periodic-save baseline: %s", e)
                    last_baseline_save = time.time()

            except Exception as e:
                _LOG.exception("Unhandled exception in sensor loop: %s", e)

            # sleep respecting poll_interval
            time.sleep(self.poll_interval)

# Module-level runner that device.py will use
_RUNNER = None

def start(poll_interval=2.0, use_scd=False, use_bme=False, use_mic=False):
    """
    Start sensor sampling in background. device.py calls this.
    """
    global _RUNNER
    if _RUNNER and _RUNNER.running:
        _LOG.info("Sensor already running")
        return
    _RUNNER = SensorRunner(poll_interval=poll_interval, use_scd=use_scd, use_bme=use_bme, use_mic=use_mic)
    _RUNNER.start()

def stop():
    global _RUNNER
    if not _RUNNER:
        return
    _RUNNER.stop()
    _RUNNER = None