#!/usr/bin/env python3
# monitor_ccs811.py
"""
Auto-reset monitor for CCS811.

- Monitors ALG_RESULT_DATA periodically.
- If persistent APP_INVALID / HEATER faults or corrupted raw patterns are seen,
  toggles the RST GPIO (BCM) and continues monitoring.
- Default RST GPIO is BCM 18 (physical pin 12). Run with sudo.

Usage:
  sudo python3 tools/auto_reset_monitor.py --rst-gpio 18 --interval 1.0 --reset-after 6 --log /tmp/ccs811_monitor.csv
"""
from __future__ import annotations
import time
import csv
import argparse
import sys

# Prefer smbus2
try:
    from smbus2 import SMBus
except Exception:
    try:
        import smbus
        SMBus = smbus.SMBus
    except Exception:
        print("smbus or smbus2 required. Install python3-smbus or smbus2.")
        sys.exit(1)

# GPIO (optional)
try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except Exception:
    GPIO_AVAILABLE = False

ADDR = 0x5A
BUS = 1
REG_ALG = 0x02
REG_BASELINE = 0x11
REG_STATUS = 0x00

def read_alg(bus):
    raw = bus.read_i2c_block_data(ADDR, REG_ALG, 8)
    eco2 = (raw[0] << 8) | raw[1]
    tvoc = (raw[2] << 8) | raw[3]
    status = raw[4]
    errid = raw[5]
    return eco2, tvoc, status, errid, raw

def toggle_rst(pin: int, hold_ms: int = 150):
    if not GPIO_AVAILABLE:
        raise RuntimeError("RPi.GPIO not available")
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(pin, GPIO.OUT, initial=GPIO.HIGH)
    GPIO.output(pin, GPIO.LOW)
    time.sleep(hold_ms / 1000.0)
    GPIO.output(pin, GPIO.HIGH)
    time.sleep(0.25)
    GPIO.cleanup(pin)

def is_corrupted_raw(raw: list[int]) -> bool:
    # Patterns that indicate corrupted read / fill values
    if all(b in (0xFD, 0xFF, 0x7F) for b in raw[:8]):
        return True
    # MSB with 0x80 and LSB zero (0x8000) is also a sentinel/corrupt
    if raw[0] & 0x80 and raw[1] == 0x00:
        return True
    return False

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--bus", type=int, default=BUS)
    p.add_argument("--address", type=lambda s:int(s,0), default=ADDR)
    p.add_argument("--interval", type=float, default=1.0)
    p.add_argument("--rst-gpio", type=int, default=18, help="BCM pin for RST (default 18)")
    p.add_argument("--reset-after", type=int, default=6, help="Consecutive bad reads to trigger reset")
    p.add_argument("--log", type=str, default="/tmp/ccs811_monitor.csv")
    args = p.parse_args()

    if args.rst_gpio is not None and not GPIO_AVAILABLE:
        print("Warning: RPi.GPIO not available; --rst-gpio will be ignored.")
        args.rst_gpio = None

    try:
        bus = SMBus(args.bus)
    except Exception as e:
        print("Failed to open I2C bus:", e)
        sys.exit(1)

    # open CSV
    f = open(args.log, "a", newline="", encoding="utf-8")
    writer = csv.writer(f)
    writer.writerow(["ts_iso", "eco2", "tvoc", "status_hex", "errid_hex", "raw"])

    consecutive_bad = 0
    try:
        print("Starting CCS811 monitor (RST GPIO BCM=%s). Ctrl+C to stop." % (str(args.rst_gpio)))
        while True:
            try:
                eco2, tvoc, status, errid, raw = read_alg(bus)
                ts = time.strftime("%Y-%m-%dT%H:%M:%S")
                writer.writerow([ts, eco2, tvoc, "0x%02X" % status, "0x%02X" % errid, raw])
                f.flush()
                print(ts, "eCO2=", eco2, "TVOC=", tvoc, "STATUS=0x%02X" % status, "ERR=0x%02X" % errid, "RAW=", raw)

                bad = False
                if errid & 0x02:      # APP_INVALID
                    bad = True
                if errid & 0x04:      # HEATER_SUPPLY
                    bad = True
                if is_corrupted_raw(raw):
                    bad = True

                if bad:
                    consecutive_bad += 1
                else:
                    consecutive_bad = 0

                if consecutive_bad >= args.reset_after:
                    print("Persistent errors detected (count=%d). Triggering RST." % consecutive_bad)
                    if args.rst_gpio is not None:
                        try:
                            toggle_rst(args.rst_gpio)
                            print("RST toggled on BCM", args.rst_gpio)
                            # give device time to restart
                            time.sleep(0.6)
                        except Exception as e:
                            print("RST toggle failed:", e)
                    else:
                        print("No RST GPIO configured; please set --rst-gpio")
                    consecutive_bad = 0

            except Exception as e:
                # I/O error; count as bad and continue
                print("I/O error reading sensor:", e)
                consecutive_bad += 1

            time.sleep(args.interval)

    except KeyboardInterrupt:
        print("Monitor interrupted by user")
    finally:
        try:
            f.close()
        except:
            pass
        try:
            bus.close()
        except:
            pass

if __name__ == "__main__":
    main()