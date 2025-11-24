#!/usr/bin/env python3
"""
Simple test script to start sensor polling and print samples from sensor_buffer.
"""
import time
from sensor import start, stop, sensor_buffer

# Start sensor thread with SCD enabled, BME disabled, mic enabled
start(poll_interval=2.0, use_scd=True, use_bme=False, use_mic=True)

try:
    # Give sensors a little time to initialize
    time.sleep(3.0)
    for i in range(12):
        if sensor_buffer:
            s = sensor_buffer[-1]
            print(f"{i:02d}: time={time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(s.ts))}, "
                  f"temp={s.temp:.1f}C, rh={s.rh:.1f}%, db={s.db:.2f}dB, co2={s.co2}ppm, voc={s.voc}ppb")
        else:
            print(f"{i:02d}: no sensor data yet")
        time.sleep(2.0)
finally:
    stop()
    print("Stopped sensor thread.")