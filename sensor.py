#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sensor.py (updated)

- Reads optional environment variable CCS811_RST_GPIO (BCM pin).
- On persistent APP_INVALID or repeated corrupted reads, toggles RST GPIO (if configured)
  and retries initialization.
- Slightly longer startup delay and more robust init retry sequence.
- No API changes: start(), stop(), sensor_buffer remain the same.
"""
from dataclasses import dataclass
import time
import threading
import os
import random
import logging

_LOG = logging.getLogger("sensor")
logging.getLogger("smbus").setLevel(logging.WARNING)

# Try smbus2 first, then smbus
SMBUS_AVAILABLE = False
try:
    from smbus2 import SMBus
    SMBUS_AVAILABLE = True
except Exception:
    try:
        import smbus
        SMBus = smbus.SMBus
        SMBUS_AVAILABLE = True
    except Exception:
        SMBUS_AVAILABLE = False

# Optional GPIO for RST
try:
    import RPi.GPIO as GPIO
    RPI_GPIO_AVAILABLE = True
except Exception:
    RPI_GPIO_AVAILABLE = False

# --- Public buffer ---
sensor_buffer = []

# --- Sample dataclass ---
@dataclass
class SensorSample:
    temp: float
    db: float
    co2: int
    voc: int
    ts: float

# CCS811 specifics
_CCS_ADDR_DEFAULT = 0x5A
_CCS_REG_STATUS = 0x00
_CCS_REG_MEAS_MODE = 0x01
_CCS_REG_ALG_RESULT_DATA = 0x02
_CCS_REG_ENV_DATA = 0x05
_CCS_REG_BASELINE = 0x11
_CCS_REG_HW_ID = 0x20
_CCS_CMD_APP_START = 0xF4

_CCS_STATUS_DATA_READY = 0x08
_CCS_STATUS_ERROR = 0x01
_CCS_STATUS_APP_VALID = 0x10

_DRIVE_MODE_VALUES = {0:0x00,1:0x10,2:0x20,3:0x30,4:0x40}

_BASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(_BASE_DIR, exist_ok=True)
_DEFAULT_BASELINE_FILE = os.path.join(_BASE_DIR, "ccs811_baseline.bin")

_MAX_BUFFER = 600

# Read optional RST pin from environment (BCM numbering). Set to -1 if not provided.
try:
    CCS811_RST_GPIO = int(os.getenv("CCS811_RST_GPIO", "-1"))
except Exception:
    CCS811_RST_GPIO = -1

class CCS811:
    def __init__(self, busnum=1, address=_CCS_ADDR_DEFAULT, baseline_file=_DEFAULT_BASELINE_FILE, logger=_LOG, post_start_delay=0.25):
        self.busnum = busnum
        self.address = address
        self.baseline_file = baseline_file
        self.logger = logger
        self.bus = None
        self.inited = False
        self.post_start_delay = post_start_delay

        if not SMBUS_AVAILABLE:
            raise RuntimeError("smbus/smbus2 not available")

        try:
            self.bus = SMBus(self.busnum)
        except Exception as e:
            raise RuntimeError(f"Failed to open I2C bus {self.busnum}: {e}")

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

    def init(self, restore_baseline=True, drive_mode=1, interrupt=False, verify_after_restore=True):
        hw = self._read_byte(_CCS_REG_HW_ID)
        if hw != 0x81:
            raise RuntimeError(f"Unexpected HW_ID 0x{hw:02X}")

        status = self._read_byte(_CCS_REG_STATUS)
        if not (status & _CCS_STATUS_APP_VALID):
            raise RuntimeError(f"APP_VALID not set (STATUS=0x{status:02X})")

        # APP_START
        try:
            self.bus.write_byte(self.address, _CCS_CMD_APP_START)
            time.sleep(self.post_start_delay)
        except Exception as e:
            raise RuntimeError(f"Failed to send APP_START: {e}")

        # restore baseline if requested
        if restore_baseline and os.path.exists(self.baseline_file):
            try:
                b = self._load_baseline_file(self.baseline_file)
                if b is not None:
                    msb = (b >> 8) & 0xFF
                    lsb = b & 0xFF
                    self._write_block(_CCS_REG_BASELINE, [msb, lsb])
                    time.sleep(0.06)
                    # verify readback optionally
                    if verify_after_restore:
                        try:
                            rb = self._read_block(_CCS_REG_BASELINE, 2)
                            read_back = (rb[0] << 8) | rb[1]
                            if read_back == b:
                                self.logger.info("Restored baseline 0x%04X (verified)", b)
                            else:
                                self.logger.warning("Baseline write mismatch: wrote 0x%04X read 0x%04X", b, read_back)
                        except Exception:
                            self.logger.warning("Baseline verification read failed")
            except Exception as e:
                self.logger.warning("Failed to restore baseline: %s", e)

        # set MEAS_MODE
        val = _DRIVE_MODE_VALUES.get(drive_mode, 0x10)
        if interrupt:
            val |= 0x08
        try:
            self.bus.write_byte_data(self.address, _CCS_REG_MEAS_MODE, val)
            time.sleep(0.06)
        except Exception as e:
            raise RuntimeError(f"Failed to set MEAS_MODE: {e}")

        self.inited = True
        self.logger.info("CCS811 initialized (mode=%d)", drive_mode)

    def read(self):
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

class Simulator:
    def __init__(self):
        self.co2 = 415 + random.randint(-10, 10)
        self.tvoc = 10 + random.randint(-3, 3)
        self.t = 22.0 + random.random() - 0.5
        self.db = 0.0

    def init(self, *a, **k):
        _LOG.info("CCS811 simulator initialized")

    def read(self):
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
        return 0xA000

    def save_baseline_file(self, path=None):
        return None

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

        self.baseline_file = baseline_file
        self.baseline_save_interval = baseline_save_interval
        self.ccs_bus = ccs_bus
        self.ccs_addr = ccs_addr
        self.simulator = None

        # RST config from env
        self.rst_gpio = CCS811_RST_GPIO if CCS811_RST_GPIO >= 0 else None

    def _toggle_rst(self):
        if self.rst_gpio is None:
            return
        if not RPI_GPIO_AVAILABLE:
            _LOG.warning("RST GPIO configured but RPi.GPIO not available")
            return
        try:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.rst_gpio, GPIO.OUT, initial=GPIO.HIGH)
            GPIO.output(self.rst_gpio, GPIO.LOW)
            time.sleep(0.15)
            GPIO.output(self.rst_gpio, GPIO.HIGH)
            time.sleep(0.25)
            GPIO.cleanup(self.rst_gpio)
            _LOG.info("Toggled CCS811 RST via BCM %d", self.rst_gpio)
        except Exception as e:
            _LOG.warning("Failed to toggle RST: %s", e)

    def _init_ccs(self):
        if self.baseline_file:
            d = os.path.dirname(self.baseline_file)
            if d and not os.path.exists(d):
                try:
                    os.makedirs(d, exist_ok=True)
                except Exception:
                    pass

        if not SMBUS_AVAILABLE:
            self.simulator = Simulator()
            self.simulator.init()
            self.ccs = self.simulator
            return

        # try init several times, toggling RST if APP_INVALID persists
        attempts = 0
        while attempts < 4:
            attempts += 1
            try:
                self.ccs = CCS811(busnum=self.ccs_bus, address=self.ccs_addr, baseline_file=self.baseline_file, post_start_delay=0.25)
                self.ccs.init(restore_baseline=True, drive_mode=1, interrupt=False)
                _LOG.info("CCS811 initialized (attempt %d)", attempts)
                return
            except Exception as e:
                _LOG.warning("CCS811 init attempt %d failed: %s", attempts, e)
                time.sleep(0.25)
                if self.rst_gpio is not None:
                    _LOG.info("Toggling RST (init recovery)...")
                    self._toggle_rst()
                    time.sleep(0.4)
        _LOG.warning("Falling back to simulator after init failures")
        self.simulator = Simulator()
        self.simulator.init()
        self.ccs = self.simulator

    def start(self):
        if self.running:
            return
        self.running = True
        time.sleep(0.6)
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
        try:
            if isinstance(self.ccs, CCS811) and self.baseline_file:
                try:
                    b = self.ccs.save_baseline_file(self.baseline_file)
                    _LOG.info("Saved baseline on stop: 0x%04X", b if b is not None else 0)
                except Exception as e:
                    _LOG.warning("Failed to save baseline on stop: %s", e)
        except Exception:
            pass
        _LOG.info("SensorRunner stopped")

    def _append_sample(self, temp, db, co2, voc):
        s = SensorSample(temp=float(temp), db=float(db), co2=int(co2), voc=int(voc), ts=time.time())
        with self.lock:
            sensor_buffer.append(s)
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
        temp = 22.0
        db = 0.0

        time.sleep(0.2)

        consecutive_bad = 0
        BAD_RESET_THRESHOLD = 6

        while self.running:
            try:
                try:
                    eco2, tvoc, status, errid, raw = self.ccs.read()
                except Exception as e:
                    _LOG.warning("CCS read failed: %s", e)
                    if isinstance(self.ccs, CCS811):
                        try:
                            self.ccs.init(restore_baseline=True, drive_mode=1)
                            eco2, tvoc, status, errid, raw = self.ccs.read()
                        except Exception as e2:
                            _LOG.error("Re-init/read failed: %s", e2)
                            self.simulator = Simulator()
                            self.simulator.init()
                            self.ccs = self.simulator
                            eco2, tvoc, status, errid, raw = self.ccs.read()
                    else:
                        raise

                if status & _CCS_STATUS_ERROR:
                    dec = self._decode_error(errid)
                    _LOG.warning("CCS reported ERROR (STATUS=0x%02X) ERROR_ID=0x%02X -> %s", status, errid, ", ".join(dec))
                    if errid & 0x02 and isinstance(self.ccs, CCS811):
                        _LOG.info("APP_INVALID detected; attempting re-init")
                        try:
                            self.ccs.init(restore_baseline=True, drive_mode=1)
                        except Exception as e:
                            _LOG.error("Re-init after APP_INVALID failed: %s", e)

                # detect corrupted raw patterns and treat as invalid
                corrupted = all(b in (0xFD,0xFF,0x7F) for b in raw[:8]) or (raw[0] & 0x80 and raw[1] == 0x00)
                if corrupted:
                    consecutive_bad += 1
                    _LOG.warning("Corrupted read detected (cnt=%d) RAW=%s", consecutive_bad, raw)
                    # try quick retry
                    try:
                        time.sleep(0.12)
                        eco2_r, tvoc_r, status_r, errid_r, raw_r = self.ccs.read()
                        if not all(b in (0xFD,0xFF,0x7F) for b in raw_r[:8]):
                            eco2, tvoc, status, errid, raw = eco2_r, tvoc_r, status_r, errid_r, raw_r
                            consecutive_bad = 0
                    except Exception:
                        pass
                    # if repeated bad reads, try toggling RST if available
                    if consecutive_bad >= BAD_RESET_THRESHOLD and self.rst_gpio is not None:
                        _LOG.info("Repeated corrupted reads, toggling RST")
                        self._toggle_rst()
                        time.sleep(0.6)
                        try:
                            self.ccs.init(restore_baseline=True, drive_mode=1)
                            consecutive_bad = 0
                        except Exception:
                            pass
                else:
                    consecutive_bad = 0

                co2 = eco2
                voc = tvoc
                temp += (random.random() - 0.5) * 0.02
                db = db * 0.98 + random.random() * 0.5

                self._append_sample(temp, db, co2, voc)

                if self.baseline_file and (time.time() - last_baseline_save) >= self.baseline_save_interval:
                    try:
                        if isinstance(self.ccs, CCS811):
                            b = self.ccs.save_baseline_file(self.baseline_file)
                            _LOG.debug("Periodic baseline saved: 0x%04X", b if b is not None else 0)
                    except Exception as e:
                        _LOG.warning("Failed to periodic-save baseline: %s", e)
                    last_baseline_save = time.time()

            except Exception as e:
                _LOG.exception("Unhandled exception in sensor loop: %s", e)

            time.sleep(self.poll_interval)

# Module-level runner
_RUNNER = None

def start(poll_interval=2.0, use_scd=False, use_bme=False, use_mic=False):
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