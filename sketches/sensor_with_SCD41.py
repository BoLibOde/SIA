#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sensor.py

Combined sensor module that reads:
 - SCD41 (preferred CO2, Temperature, Humidity)
 - CCS811 (TVOC) — CCS811 is used only for TVOC; SCD41 data is supplied to CCS811 via ENV_DATA.

Behavior:
 - If hardware I2C libs are unavailable or sensors fail, falls back to simulators.
 - Restores and periodically saves CCS811 baseline to avoid re-burning.
 - Exposes start(...) and stop() and sensor_buffer (list of SensorSample objects).
 - Each SensorSample contains: temp (C), db (dB), co2 (ppm from SCD41), voc (ppb from CCS811), ts (epoch).
"""
from dataclasses import dataclass
import time
import threading
import os
import struct
import math
import random
import logging

_LOG = logging.getLogger("sensor")
logging.getLogger("smbus").setLevel(logging.WARNING)

# Public buffer for device.py to read
sensor_buffer = []

@dataclass
class SensorSample:
    temp: float
    db: float
    co2: int
    voc: int
    ts: float

# Try to import smbus2 first (better I2C support), fall back to smbus
SMBUS2 = False
try:
    from smbus2 import SMBus, i2c_msg
    SMBUS2 = True
except Exception:
    try:
        import smbus
        SMBus = smbus.SMBus
    except Exception:
        SMBus = None

# -----------------------
# SCD41 driver (minimal)
# -----------------------
class SCD41:
    """
    Minimal SCD41 driver using I2C.
    Uses periodic measurement mode and Read Measurement command.
    Parsing follows Sensirion convention: each float is sent as two 16-bit words,
    each word followed by a CRC8. Total 18 bytes = 3 values * (2*2bytes + 2*CRC) = 18.
    """
    ADDRESS = 0x62
    CMD_START_PERIODIC = 0x21B1
    CMD_READ_MEASUREMENT = 0xEC05
    CMD_STOP_PERIODIC = 0x3F86

    def __init__(self, busnum=1, address=None, logger=_LOG):
        self.address = address or self.ADDRESS
        self.busnum = busnum
        self.logger = logger
        if SMBus is None:
            raise RuntimeError("I2C bus not available")
        # use SMBus or smbus2 wrapper
        try:
            self.bus = SMBus(busnum)
        except Exception as e:
            raise RuntimeError(f"Failed to open I2C bus {busnum}: {e}")

    @staticmethod
    def _crc8(buf):
        # Sensirion CRC8, polynomial 0x31, init 0xFF
        crc = 0xFF
        for b in buf:
            crc ^= b
            for _ in range(8):
                if crc & 0x80:
                    crc = ((crc << 1) & 0xFF) ^ 0x31
                else:
                    crc = (crc << 1) & 0xFF
        return crc

    def _write_command(self, cmd, args=None):
        msb = (cmd >> 8) & 0xFF
        lsb = cmd & 0xFF
        data = [lsb] if args is None else [lsb] + list(args)
        # Many smbus implementations accept write_i2c_block_data with register=msb
        try:
            # Using smbus2 i2c_msg if available is preferable
            if SMBUS2:
                write = i2c_msg.write(self.address, bytes([msb, lsb] + (args or [])))
                self.bus.i2c_rdwr(write)
            else:
                # write_i2c_block_data will send [msb] as command/register byte then the list
                self.bus.write_i2c_block_data(self.address, msb, [lsb] + (args or []))
        except Exception as e:
            raise RuntimeError(f"SCD41 write command 0x{cmd:04X} failed: {e}")

    def start_periodic(self):
        # Start periodic measurement (no ambient pressure argument here)
        self._write_command(self.CMD_START_PERIODIC)
        time.sleep(0.05)

    def stop_periodic(self):
        try:
            self._write_command(self.CMD_STOP_PERIODIC)
            time.sleep(0.05)
        except Exception:
            pass

    def read_measurement(self, timeout=0.1):
        """
        Returns (co2_ppm:int, temperature_C:float, humidity_pct:float)
        """
        # Send read measurement command
        self._write_command(self.CMD_READ_MEASUREMENT)
        # small delay; datasheet allows immediate read but a few ms helps
        time.sleep(0.005)

        # Read 18 bytes
        try:
            if SMBUS2:
                # Use i2c_msg read
                read = i2c_msg.read(self.address, 18)
                self.bus.i2c_rdwr(read)
                data = bytes(read)
            else:
                # Try reading using read_i2c_block_data with 0 register (some implementations accept)
                data = bytes(self.bus.read_i2c_block_data(self.address, 0, 18))
        except Exception as e:
            raise RuntimeError(f"SCD41 read failed: {e}")

        if len(data) != 18:
            raise RuntimeError(f"SCD41 returned unexpected length {len(data)}")

        values = []
        # parse 3 values, each 6 bytes: word1(2) crc1(1) word2(2) crc2(1)
        for i in range(0, 18, 6):
            w1 = data[i:i+2]
            crc1 = data[i+2]
            w2 = data[i+3:i+5]
            crc2 = data[i+5]
            if self._crc8(w1) != crc1 or self._crc8(w2) != crc2:
                raise RuntimeError("SCD41 CRC mismatch")
            # combine w1 + w2 into 4 bytes big-endian float
            float_bytes = bytes(w1 + w2)
            # big-endian float32
            val = struct.unpack(">f", float_bytes)[0]
            values.append(val)
        co2 = int(round(values[0]))
        temp = float(values[1])
        hum = float(values[2])
        return co2, temp, hum

# -----------------------
# CCS811 wrapper (TVOC)
# -----------------------
class CCS811:
    ADDR = 0x5A
    REG_STATUS = 0x00
    REG_MEAS_MODE = 0x01
    REG_ALG = 0x02
    REG_ENV_DATA = 0x05
    REG_BASELINE = 0x11
    REG_HW_ID = 0x20
    CMD_APP_START = 0xF4

    STATUS_DATA_READY = 0x08
    STATUS_ERROR = 0x01
    STATUS_APP_VALID = 0x10

    def __init__(self, busnum=1, address=None, baseline_file=None, logger=_LOG):
        self.address = address or self.ADDR
        self.busnum = busnum
        self.baseline_file = baseline_file
        self.logger = logger
        if SMBus is None:
            raise RuntimeError("I2C bus not available")
        try:
            self.bus = SMBus(busnum)
        except Exception as e:
            raise RuntimeError(f"Failed to open I2C bus {busnum}: {e}")

    def _read_byte(self, reg, retries=3):
        for i in range(retries):
            try:
                return self.bus.read_byte_data(self.address, reg)
            except Exception:
                time.sleep(0.02)
        raise

    def _read_block(self, reg, length, retries=3):
        for i in range(retries):
            try:
                return self.bus.read_i2c_block_data(self.address, reg, length)
            except Exception:
                time.sleep(0.02)
        raise

    def _write_block(self, reg, data, retries=3):
        for i in range(retries):
            try:
                return self.bus.write_i2c_block_data(self.address, reg, data)
            except Exception:
                time.sleep(0.02)
        raise

    def init(self, restore_baseline=True, drive_mode=1, interrupt=False):
        hw = self._read_byte(self.REG_HW_ID)
        if hw != 0x81:
            raise RuntimeError(f"Unexpected CCS811 HW_ID 0x{hw:02X}")
        status = self._read_byte(self.REG_STATUS)
        if not (status & self.STATUS_APP_VALID):
            raise RuntimeError(f"CCS811 APP_VALID not set (STATUS=0x{status:02X})")
        # APP_START command (write_byte)
        try:
            # smbus write_byte(address, value) writes a single byte to device; that's fine for command-only
            self.bus.write_byte(self.address, self.CMD_APP_START)
            time.sleep(0.05)
        except Exception as e:
            raise RuntimeError(f"Failed to send APP_START to CCS811: {e}")

        # restore baseline if requested
        if restore_baseline and self.baseline_file and os.path.exists(self.baseline_file):
            try:
                with open(self.baseline_file, "rb") as f:
                    bdata = f.read()
                if len(bdata) == 2:
                    msb, lsb = bdata[0], bdata[1]
                    self._write_block(self.REG_BASELINE, [msb, lsb])
                    time.sleep(0.02)
                    self.logger.info("CCS811: restored baseline 0x%02X%02X", msb, lsb)
            except Exception as e:
                self.logger.warning("CCS811: failed to restore baseline: %s", e)

        # set MEAS_MODE
        mode_val = {0:0x00, 1:0x10, 2:0x20, 3:0x30, 4:0x40}.get(drive_mode, 0x10)
        if interrupt:
            mode_val |= 0x08
        try:
            self.bus.write_byte_data(self.address, self.REG_MEAS_MODE, mode_val)
            time.sleep(0.02)
        except Exception as e:
            raise RuntimeError(f"CCS811 set MEAS_MODE failed: {e}")

    def read(self):
        raw = self._read_block(self.REG_ALG, 8)
        eco2 = (raw[0] << 8) | raw[1]
        tvoc = (raw[2] << 8) | raw[3]
        status = raw[4]
        error_id = raw[5]
        return eco2, tvoc, status, error_id, raw

    def write_env_data(self, humidity_percent, temp_c):
        """
        Write ENV_DATA to CCS811 (register 0x05).
        Format per CCS811 programming guide:
         - humidity: uint16 = round(humidity_percent * 512) (1/512 %RH)
         - temperature: uint16 = round((temp_c + 25) * 512) (1/512 °C with +25 offset)
         - total 4 bytes sent (no CRC)
        """
        h_raw = int(round(humidity_percent * 512.0)) & 0xFFFF
        t_raw = int(round((temp_c + 25.0) * 512.0)) & 0xFFFF
        msb_h = (h_raw >> 8) & 0xFF
        lsb_h = h_raw & 0xFF
        msb_t = (t_raw >> 8) & 0xFF
        lsb_t = t_raw & 0xFF
        try:
            self._write_block(self.REG_ENV_DATA, [msb_h, lsb_h, msb_t, lsb_t])
        except Exception as e:
            raise RuntimeError(f"Failed to write ENV_DATA to CCS811: {e}")

    def read_baseline(self):
        b = self._read_block(self.REG_BASELINE, 2)
        return (b[0] << 8) | b[1]

    def save_baseline_file(self, path):
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
            self.logger.info("CCS811 baseline saved: 0x%04X -> %s", b, path)
            return b
        except Exception as e:
            self.logger.warning("CCS811 baseline save failed: %s", e)
            raise

# -----------------------
# Simulator classes
# -----------------------
class SCD41Simulator:
    def __init__(self):
        self.co2 = 415 + random.randint(-5, 5)
        self.temp = 22.0 + (random.random()-0.5)
        self.hum = 45.0 + (random.random()-2.0)
    def start_periodic(self):
        pass
    def read_measurement(self):
        # gentle random walk
        self.co2 = max(400, min(5000, self.co2 + int(random.gauss(0, 1))))
        self.temp += (random.random() - 0.5) * 0.05
        self.hum += (random.random() - 0.5) * 0.1
        return int(round(self.co2)), float(self.temp), float(self.hum)

class CCS811Simulator:
    def __init__(self):
        self.co2 = 415
        self.tvoc = 10
    def init(self, *a, **k):
        _LOG.info("CCS811 simulator init")
    def read(self):
        self.co2 += int(random.gauss(0, 1))
        self.tvoc += int(random.gauss(0, 1))
        self.co2 = max(400, min(5000, self.co2))
        self.tvoc = max(0, min(60000, self.tvoc))
        status = CCS811.STATUS_DATA_READY | CCS811.STATUS_APP_VALID
        raw = [ (self.co2>>8)&0xFF, self.co2&0xFF, (self.tvoc>>8)&0xFF, self.tvoc&0xFF, status, 0x00, 0x00, 0x00 ]
        return self.co2, self.tvoc, status, 0x00, raw
    def save_baseline_file(self, path):
        pass

# -----------------------
# Sensor runner
# -----------------------
class SensorRunner:
    def __init__(self, poll_interval=2.0, use_scd=False, use_bme=False, use_mic=False,
                 ccs_bus=1, ccs_addr=0x5A, baseline_file=None):
        self.poll_interval = max(0.1, float(poll_interval))
        self.use_scd = use_scd
        self.use_bme = use_bme
        self.use_mic = use_mic
        self.ccs_bus = ccs_bus
        self.ccs_addr = ccs_addr
        self.baseline_file = baseline_file or os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "ccs811_baseline.bin")
        self.running = False
        self.thread = None
        self.lock = threading.Lock()
        self.ccs = None
        self.scd = None
        self.sim_ccs = None
        self.sim_scd = None

    def _init_sensors(self):
        # Initialize SCD41 if requested
        if self.use_scd:
            try:
                self.scd = SCD41(busnum=1)
                self.scd.start_periodic()
                _LOG.info("SCD41 initialized")
            except Exception as e:
                _LOG.warning("SCD41 init failed: %s — using simulator", e)
                self.sim_scd = SCD41Simulator()
                self.scd = self.sim_scd
        else:
            # Not requested: use simulator for temperature/CO2/humidity
            self.sim_scd = SCD41Simulator()
            self.scd = self.sim_scd

        # Initialize CCS811 (for TVOC)
        try:
            self.ccs = CCS811(busnum=1, address=self.ccs_addr, baseline_file=self.baseline_file)
            # restore baseline and set mode 1 (1s)
            self.ccs.init(restore_baseline=True, drive_mode=1, interrupt=False)
            _LOG.info("CCS811 initialized")
        except Exception as e:
            _LOG.warning("CCS811 init failed: %s — using simulator", e)
            self.sim_ccs = CCS811Simulator()
            self.ccs = self.sim_ccs

    def start(self):
        if self.running:
            return
        self.running = True
        self._init_sensors()
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        _LOG.info("SensorRunner started (poll_interval=%.2f)", self.poll_interval)

    def stop(self):
        if not self.running:
            return
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)
        # Attempt to stop SCD41 periodic if hardware
        try:
            if isinstance(self.scd, SCD41):
                self.scd.stop_periodic()
        except Exception:
            pass
        _LOG.info("SensorRunner stopped")

    def _append_sample(self, temp, db, co2, voc):
        s = SensorSample(temp=float(temp), db=float(db), co2=int(co2), voc=int(voc), ts=time.time())
        with self.lock:
            sensor_buffer.append(s)
            # trim to reasonable size
            if len(sensor_buffer) > 600:
                del sensor_buffer[0: len(sensor_buffer) - 600]

    def _loop(self):
        last_baseline_save = time.time()
        temp = 22.0
        db = 0.0

        # small warmup
        time.sleep(0.2)

        while self.running:
            try:
                # 1) read SCD41 (CO2, temp, humidity)
                try:
                    co2_scd, temp_scd, hum_scd = self.scd.read_measurement()
                except Exception as e:
                    _LOG.warning("SCD41 read failed: %s", e)
                    # attempt a single re-init if hardware
                    if isinstance(self.scd, SCD41):
                        try:
                            self.scd.start_periodic()
                            time.sleep(0.1)
                            co2_scd, temp_scd, hum_scd = self.scd.read_measurement()
                        except Exception as e2:
                            _LOG.error("SCD41 reinit/read failed: %s", e2)
                            # fallback to simulator
                            self.sim_scd = SCD41Simulator()
                            self.scd = self.sim_scd
                            co2_scd, temp_scd, hum_scd = self.scd.read_measurement()
                    else:
                        # simulator error unlikely
                        co2_scd, temp_scd, hum_scd = self.scd.read_measurement()

                # 2) write ENV_DATA to CCS811 to improve TVOC accuracy
                try:
                    if isinstance(self.ccs, CCS811):
                        # use humidity percent and temperature C
                        self.ccs.write_env_data(hum_scd, temp_scd)
                except Exception as e:
                    _LOG.warning("Failed to write ENV_DATA to CCS811: %s", e)

                # 3) read CCS811 for TVOC (and ignore its eCO2)
                try:
                    eco2_ccs, tvoc, status, errid, raw = self.ccs.read()
                except Exception as e:
                    _LOG.warning("CCS811 read failed: %s", e)
                    # try re-init once if hardware
                    if isinstance(self.ccs, CCS811):
                        try:
                            self.ccs.init(restore_baseline=True, drive_mode=1)
                            eco2_ccs, tvoc, status, errid, raw = self.ccs.read()
                        except Exception as e2:
                            _LOG.error("CCS811 reinit/read failed: %s", e2)
                            self.sim_ccs = CCS811Simulator()
                            self.ccs = self.sim_ccs
                            eco2_ccs, tvoc, status, errid, raw = self.ccs.read()
                    else:
                        eco2_ccs, tvoc, status, errid, raw = self.ccs.read()

                # If CCS reports error, log details
                if status & CCS811.STATUS_ERROR:
                    _LOG.warning("CCS811 reported ERROR (STATUS=0x%02X) ERROR_ID=0x%02X", status, errid)
                    # if APP_INVALID (0x02) try re-init
                    if errid & 0x02 and isinstance(self.ccs, CCS811):
                        _LOG.info("CCS811 APP_INVALID detected; attempting re-init")
                        try:
                            self.ccs.init(restore_baseline=True, drive_mode=1)
                        except Exception as e:
                            _LOG.error("CCS811 re-init after APP_INVALID failed: %s", e)

                # prepare sample values:
                temp = temp_scd
                co2 = co2_scd
                voc = tvoc
                # db left as placeholder; mic integration not implemented here
                db = db * 0.98 + random.random() * 0.5

                self._append_sample(temp, db, co2, voc)

                # periodic baseline save for CCS811
                if (time.time() - last_baseline_save) >= 3600.0:
                    try:
                        if isinstance(self.ccs, CCS811):
                            self.ccs.save_baseline_file(self.baseline_file)
                    except Exception as e:
                        _LOG.warning("Failed to save CCS811 baseline: %s", e)
                    last_baseline_save = time.time()

            except Exception as e:
                _LOG.exception("Unhandled exception in sensor loop: %s", e)

            time.sleep(self.poll_interval)

# Module-level runner used by device.py
_RUNNER = None

def start(poll_interval=2.0, use_scd=False, use_bme=False, use_mic=False):
    global _RUNNER
    if _RUNNER and _RUNNER.running:
        _LOG.info("Sensor already running")
        return
    baseline_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "ccs811_baseline.bin")
    _RUNNER = SensorRunner(poll_interval=poll_interval, use_scd=use_scd, use_bme=use_bme, use_mic=use_mic,
                           ccs_bus=1, ccs_addr=0x5A, baseline_file=baseline_file)
    _RUNNER.start()

def stop():
    global _RUNNER
    if not _RUNNER:
        return
    _RUNNER.stop()
    _RUNNER = None