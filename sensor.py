#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sensor.py (SCD41-only)

This version removes CCS811 entirely and only uses the SCD41 (or simulator).
Exposes start(...) and stop() and sensor_buffer (list of SensorSample objects).
Each SensorSample contains: temp (C), db (dB), co2 (ppm from SCD41), voc (Optional[int]), ts (epoch).
"""
from dataclasses import dataclass
import time
import threading
import os
import struct
import random
import logging
from typing import Optional

_LOG = logging.getLogger("sensor")
logging.getLogger("smbus").setLevel(logging.WARNING)

# Public buffer for device.py to read
sensor_buffer = []

@dataclass
class SensorSample:
    temp: float
    db: float
    co2: int
    voc: Optional[int]
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
        try:
            self.bus = SMBus(busnum)
        except Exception as e:
            raise RuntimeError(f"Failed to open I2C bus {busnum}: {e}")
        self.logger.info("SCD41 initialized on I2C bus %s, address 0x%02X", busnum, self.address)

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
        try:
            if SMBUS2:
                write = i2c_msg.write(self.address, bytes([msb, lsb] + (args or [])))
                self.bus.i2c_rdwr(write)
            else:
                self.bus.write_i2c_block_data(self.address, msb, [lsb] + (args or []))
        except Exception as e:
            raise RuntimeError(f"SCD41 write command 0x{cmd:04X} failed: {e}")

    def start_periodic(self):
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
        self._write_command(self.CMD_READ_MEASUREMENT)
        time.sleep(0.005)

        try:
            if SMBUS2:
                read = i2c_msg.read(self.address, 18)
                self.bus.i2c_rdwr(read)
                data = bytes(read)
            else:
                data = bytes(self.bus.read_i2c_block_data(self.address, 0, 18))
        except Exception as e:
            raise RuntimeError(f"SCD41 read failed: {e}")

        if len(data) != 18:
            raise RuntimeError(f"SCD41 returned unexpected length {len(data)}")

        values = []
        for i in range(0, 18, 6):
            w1 = data[i:i+2]
            crc1 = data[i+2]
            w2 = data[i+3:i+5]
            crc2 = data[i+5]
            if self._crc8(w1) != crc1 or self._crc8(w2) != crc2:
                raise RuntimeError("SCD41 CRC mismatch")
            float_bytes = bytes(w1 + w2)
            val = struct.unpack(">f", float_bytes)[0]
            values.append(val)
        co2 = int(round(values[0]))
        temp = float(values[1])
        hum = float(values[2])
        return co2, temp, hum

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

# -----------------------
# Sensor runner (SCD41-only)
# -----------------------
class SensorRunner:
    def __init__(self, poll_interval=2.0, use_scd=False, use_bme=False, use_mic=False):
        self.poll_interval = max(0.1, float(poll_interval))
        self.use_scd = use_scd
        self.use_bme = use_bme
        self.use_mic = use_mic
        self.running = False
        self.thread = None
        self.lock = threading.Lock()
        self.scd = None
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
        try:
            if isinstance(self.scd, SCD41):
                self.scd.stop_periodic()
        except Exception:
            pass
        _LOG.info("SensorRunner stopped")

    def _append_sample(self, temp, db, co2, voc):
        s = SensorSample(temp=float(temp), db=float(db), co2=int(co2), voc=voc, ts=time.time())
        with self.lock:
            sensor_buffer.append(s)
            # trim to reasonable size
            if len(sensor_buffer) > 600:
                del sensor_buffer[0: len(sensor_buffer) - 600]

    def _loop(self):
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
                        co2_scd, temp_scd, hum_scd = self.scd.read_measurement()

                # prepare sample values (voc not available since CCS811 removed)
                temp = temp_scd
                co2 = co2_scd
                voc = None  # no CCS811 -> VOC unknown
                # db left as placeholder; mic integration not implemented here
                db = db * 0.98 + random.random() * 0.5

                self._append_sample(temp, db, co2, voc)

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
    _RUNNER = SensorRunner(poll_interval=poll_interval, use_scd=use_scd, use_bme=use_bme, use_mic=use_mic)
    _RUNNER.start()

def stop():
    global _RUNNER
    if not _RUNNER:
        return
    _RUNNER.stop()
    _RUNNER = None
