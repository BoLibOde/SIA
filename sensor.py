#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sensor.py

SCD4x (SCD40/SCD41) SensorRunner used by device.py.

Provides:
- SensorRunner(simulation_mode=False)
- .start(interval=2.0)
- .stop()
- .sensor_buffer: list of SensorSample objects (temp, humidity, co2, ts)
"""
from __future__ import annotations

from dataclasses import dataclass
import time
import threading
import random
import logging
from typing import List, Optional

try:
    from smbus2 import SMBus  # type: ignore
    SMBUS2_AVAILABLE = True
except Exception:
    SMBUS2_AVAILABLE = False
    SMBus = None  # type: ignore


_LOG = logging.getLogger("sensor")

# --- SCD41 constants ---
SCD41_I2C_ADDR = 0x62
COMMAND_START_MEASUREMENT = [0x21, 0xB1]  # start periodic measurements
COMMAND_GET_DATA_READY = [0xE4, 0xB8]     # check data ready
COMMAND_READ_MEASUREMENT = [0xEC, 0x05]   # read measurement
COMMAND_STOP_MEASUREMENT = [0x3F, 0x86]   # stop periodic measurements
COMMAND_SOFT_RESET = [0x36, 0x82]         # soft reset


@dataclass
class SensorSample:
    co2: int
    temp: float
    humidity: float
    ts: float


def calculate_crc(data: List[int]) -> int:
    """Calculate CRC for Sensirion sensors (2-byte words)."""
    crc = 0xFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x80:
                crc = (crc << 1) ^ 0x31
            else:
                crc <<= 1
    return crc & 0xFF


def _is_data_ready(bus: SMBus, address: int) -> bool:
    bus.write_i2c_block_data(address, COMMAND_GET_DATA_READY[0], COMMAND_GET_DATA_READY[1:])
    time.sleep(0.005)
    response = bus.read_i2c_block_data(address, 0x00, 3)

    # response[0:2] is a 16-bit value, response[2] is CRC
    # In practice many implementations check the 16-bit word != 0
    word = (response[0] << 8) | response[1]
    return word != 0


def _read_measurement(bus: SMBus, address: int) -> tuple[int, float, float]:
    bus.write_i2c_block_data(address, COMMAND_READ_MEASUREMENT[0], COMMAND_READ_MEASUREMENT[1:])
    time.sleep(0.005)

    data = bus.read_i2c_block_data(address, 0x00, 9)

    # 3 fields * (2 bytes + 1 crc)
    for i in range(3):
        word_bytes = data[i * 3: i * 3 + 2]
        crc = data[i * 3 + 2]
        if calculate_crc(word_bytes) != crc:
            raise ValueError("CRC mismatch on measurement field")

    co2 = int.from_bytes(bytes(data[0:2]), "big")
    temp_raw = int.from_bytes(bytes(data[3:5]), "big")
    hum_raw = int.from_bytes(bytes(data[6:8]), "big")

    temp = -45 + (175 * temp_raw) / 65535.0
    humidity = 100 * hum_raw / 65535.0
    return co2, temp, humidity


class SensorRunner:
    def __init__(self, simulation_mode: bool = False, max_buffer: int = 300):
        self.simulation_mode = simulation_mode
        self.max_buffer = max(10, int(max_buffer))

        self.sensor_buffer: List[SensorSample] = []
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._interval = 2.0

        # sim state
        self._sim_co2 = 420
        self._sim_temp = 22.0
        self._sim_hum = 45.0

    def start(self, interval: float = 2.0):
        if self._running:
            return
        self._interval = max(0.5, float(interval))
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        _LOG.info("SensorRunner started (interval=%.2fs, simulation=%s)", self._interval, self.simulation_mode)

    def stop(self):
        if not self._running:
            return
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        _LOG.info("SensorRunner stopped")

    def _append(self, co2: int, temp: float, humidity: float):
        s = SensorSample(co2=int(co2), temp=float(temp), humidity=float(humidity), ts=time.time())
        with self._lock:
            self.sensor_buffer.append(s)
            if len(self.sensor_buffer) > self.max_buffer:
                del self.sensor_buffer[0: len(self.sensor_buffer) - self.max_buffer]

    def _sim_step(self) -> tuple[int, float, float]:
        # gentle random walk
        self._sim_co2 = max(400, min(5000, self._sim_co2 + int(random.gauss(0, 2))))
        self._sim_temp += (random.random() - 0.5) * 0.05
        self._sim_hum += (random.random() - 0.5) * 0.10
        self._sim_hum = max(0.0, min(100.0, self._sim_hum))
        return self._sim_co2, self._sim_temp, self._sim_hum

    def _loop(self):
        if self.simulation_mode or not SMBUS2_AVAILABLE:
            if not SMBUS2_AVAILABLE and not self.simulation_mode:
                _LOG.warning("smbus2 not available; falling back to simulation mode")
            while self._running:
                co2, temp, hum = self._sim_step()
                self._append(co2, temp, hum)
                time.sleep(self._interval)
            return

        # Hardware mode
        try:
            with SMBus(1) as bus:
                # reset + start periodic
                bus.write_i2c_block_data(SCD41_I2C_ADDR, COMMAND_SOFT_RESET[0], COMMAND_SOFT_RESET[1:])
                time.sleep(1.0)

                bus.write_i2c_block_data(SCD41_I2C_ADDR, COMMAND_START_MEASUREMENT[0], COMMAND_START_MEASUREMENT[1:])
                # datasheet recommends waiting for first measurement; keep it modest
                time.sleep(5.0)

                while self._running:
                    try:
                        if _is_data_ready(bus, SCD41_I2C_ADDR):
                            co2, temp, hum = _read_measurement(bus, SCD41_I2C_ADDR)
                            self._append(co2, temp, hum)
                        else:
                            _LOG.debug("SCD41 data not ready yet")
                    except Exception as e:
                        _LOG.warning("SCD41 read failed: %s", e)

                    time.sleep(self._interval)

                # stop periodic
                try:
                    bus.write_i2c_block_data(SCD41_I2C_ADDR, COMMAND_STOP_MEASUREMENT[0], COMMAND_STOP_MEASUREMENT[1:])
                except Exception:
                    pass
        except Exception as e:
            _LOG.exception("Fatal error in SensorRunner hardware loop: %s", e)
            # fallback: keep running in simulation so UI/upload still works
            while self._running:
                co2, temp, hum = self._sim_step()
                self._append(co2, temp, hum)
                time.sleep(self._interval)