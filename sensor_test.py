#!/usr/bin/env python3
import time
from sensor import start, stop, sensor_buffer

# Start sensor thread with SCD enabled and BME disabled
start(poll_interval=2.0, use_scd=True, use_bme=False)

try:
    # Give sensors a little time to initialize
    time.sleep(3.0)
    for i in range(12):
        if sensor_buffer:
            temp, db, co2, voc, ts = sensor_buffer[-1]
            print(f"{i:02d}: time={time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ts))}, "
                  f"temp={temp}C, db={db}dB, co2={co2}ppm, voc={voc}ppb")
        else:
            print(f"{i:02d}: no sensor data yet")
        time.sleep(2.0)
finally:
    stop()
    print("Stopped sensor thread.")