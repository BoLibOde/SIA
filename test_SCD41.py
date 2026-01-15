#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
test_SCD41.py

This script tests the SCD4x sensor using the SensorRunner class.
"""

import logging
from sensor import SensorRunner

# Set up logging
logging.basicConfig(level=logging.DEBUG)
_LOG = logging.getLogger("test_SCD41")

try:
    # Instantiate SensorRunner with hardware mode (not simulation)
    sensor_runner = SensorRunner(simulation_mode=False)

    # Start the sensor runner
    sensor_runner.start(interval=2.0)
    _LOG.info("SensorRunner started successfully.")

    # Fetch data for a few readings and display them
    for i in range(5):  # Collect 5 readings for testing
        if sensor_runner.sensor_buffer:
            latest = sensor_runner.sensor_buffer[-1]
            print(f"Reading {i + 1}:")
            print(f"  CO2: {latest.co2} ppm")
            print(f"  Temperature: {latest.temp:.2f} °C")
            print(f"  VOC: {latest.voc} ppb (simulated if unsupported)")
        else:
            print(f"Waiting for sensor data... (Iteration {i + 1})")
        import time; time.sleep(2)  # Wait for 2 seconds between each reading

except Exception as e:
    _LOG.exception("Failed to initialize or read from the SCD4x sensor: %s", e)

finally:
    # Stop the SensorRunner (cleanup)
    sensor_runner.stop()
    _LOG.info("SensorRunner stopped.")