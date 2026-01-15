#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sensor.py

Reads data from hardware sensors or provides simulated data when enabled.
Supports SCD4x via I2C for CO2, temperature, humidity.
"""
from dataclasses import dataclass
import time
import threading
import logging
from random import uniform, randint

try:
    from sensirion_i2c_driver import I2cTransceiver  # Sensirion I2C driver for SCD4x
    from sensirion_i2c_scd.scd4x import Scd4xI2cDevice
    SCD4X_AVAILABLE = True
except ImportError:
    SCD4X_AVAILABLE = False

_LOG = logging.getLogger("sensor")


@dataclass
class SensorSample:
    """
    Represents a single sensor reading.
    """
    temp: float  # Temperature in °C
    db: float    # Decibel level (unused, currently static)
    co2: int     # CO2 concentration (ppm)
    voc: int     # VOC concentration (not supported, currently defaulted to 0)
    ts: float    # Timestamp (epoch time)


class SensorRunner:
    """
    Manages periodic sensor readings from hardware or simulation.
    """
    def __init__(self, simulation_mode=True):
        """
        Initializes the SensorRunner.

        Args:
            simulation_mode (bool): If True, simulate sensor data. If False, use real hardware.
        """
        self.simulation_mode = simulation_mode  # True for simulation, False for hardware
        self.running = False
        self.sensor_buffer = []  # Buffer to store sensor readings
        self.interval = 2.0  # Sensor polling interval
        self.thread = None
        self.lock = threading.Lock()  # Lock for thread-safe access
        self.scd4x = None

    def _initialize_scd4x(self):
        """
        Initializes the SCD4x sensor via I2C.
        """
        try:
            if not SCD4X_AVAILABLE:
                raise ImportError("Required library for SCD4x not installed. Install with 'pip install sensirion-i2c-scd'.")

            self.scd4x = Scd4xI2cDevice(I2cTransceiver(1, 0x62))  # I2C bus 1, default SCD4x address: 0x62
            _LOG.info("Initializing SCD4x sensor...")
            self.scd4x.stop_periodic_measurement()  # Reset sensor state
            time.sleep(1)
            self.scd4x.start_periodic_measurement()  # Start data collection
            _LOG.info("SCD4x successfully initialized.")
        except Exception as e:
            _LOG.error("Failed to initialize SCD4x: %s", e)
            raise RuntimeError("Could not initialize SCD4x sensor.") from e

    def start(self, interval=2.0):
        """
        Starts the sensor data-reading loop.
        """
        if self.running:
            _LOG.warning("SensorRunner is already running.")
            return
        self.interval = interval
        self.running = True
        if not self.simulation_mode:
            self._initialize_scd4x()  # Initialize hardware sensor in hardware mode
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        _LOG.info("SensorRunner started with interval: %.1f seconds (Simulation: %s).",
                  self.interval, "ON" if self.simulation_mode else "OFF")

    def stop(self):
        """Stops the SensorRunner."""
        self.running = False
        if self.thread:
            self.thread.join()
        if self.scd4x:
            try:
                self.scd4x.stop_periodic_measurement()
                _LOG.info("Stopped periodic measurement on SCD4x.")
            except Exception:
                pass
        _LOG.info("SensorRunner stopped.")

    def _append_sample(self, temp, db, co2, voc):
        """
        Appends a sensor sample to the buffer.
        """
        with self.lock:
            sample = SensorSample(temp=temp, db=db, co2=co2, voc=voc, ts=time.time())
            self.sensor_buffer.append(sample)
            if len(self.sensor_buffer) > 100:  # Limit buffer size to avoid memory overflow
                self.sensor_buffer.pop(0)
            _LOG.debug("New sample added: %s", sample)

    def _loop(self):
        """
        Continuously collects data from hardware or generates simulated values.
        """
        while self.running:
            try:
                if self.simulation_mode:
                    # Simulated Sensor Data
                    temp = uniform(22.0, 25.0)  # Simulated temperature
                    db = 0                    # Static decibel placeholder
                    co2 = randint(400, 500)   # Simulated CO2
                    voc = randint(10, 50)     # Simulated VOC
                    _LOG.debug("Simulated Data: Temp=%.1f°C, CO2=%dppm, VOC=%dppb", temp, co2, voc)
                else:
                    # Read Real Hardware Data (SCD4x)
                    if self.scd4x.get_data_ready_flag():
                        co2, temp, _ = self.scd4x.read_measurement()
                        voc = 0  # VOC data not supported
                        db = 0   # dB measurement not part of SCD4x
                        _LOG.debug("Hardware Data: Temp=%.1f°C, CO2=%dppm", temp, co2)
                    else:
                        _LOG.warning("SCD4x data not ready. Skipping cycle.")
                        time.sleep(self.interval)
                        continue

                # Append the sample
                self._append_sample(temp, db, co2, voc)

            except Exception as e:
                _LOG.error("Error during sensor loop: %s", e)

            time.sleep(self.interval)


