#!/usr/bin/env python3
# Diagnostic helper (updated)
"""
diagnostic_ccs811.py

- Safer APP_START+MEAS_MODE with configurable post-start delay.
- Optional RST toggle via --rst-gpio when persistent APP_INVALID or other errors are detected.

Usage:
  sudo python3 diagnostic_ccs811.py [--rst-gpio 18] [--post-start-delay 0.25]
"""
import time
import argparse

# prefer smbus2
try:
    from smbus2 import SMBus
except Exception:
    import smbus
    SMBus = smbus.SMBus

# optional GPIO
try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except Exception:
    GPIO_AVAILABLE = False

ADDR = 0x5A
BUS = 1
REG_STATUS = 0x00
REG_ALG = 0x02
REG_HW_ID = 0x20
REG_BASELINE = 0x11
CMD_APP_START = 0xF4
REG_MEAS_MODE = 0x01

def safe_read_byte(bus, addr, reg):
    return bus.read_byte_data(addr, reg)

def safe_read_block(bus, addr, reg, length):
    return bus.read_i2c_block_data(addr, reg, length)

def toggle_reset(pin, hold_ms=150):
    if not GPIO_AVAILABLE:
        raise RuntimeError("RPi.GPIO not available")
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(pin, GPIO.OUT, initial=GPIO.HIGH)
    GPIO.output(pin, GPIO.LOW)
    time.sleep(hold_ms / 1000.0)
    GPIO.output(pin, GPIO.HIGH)
    time.sleep(0.2)
    GPIO.cleanup(pin)
    print("RST toggled on BCM", pin)

def perform_app_start(bus, post_start_delay=0.20):
    try:
        bus.write_byte(ADDR, CMD_APP_START)
        time.sleep(post_start_delay)
        bus.write_byte_data(ADDR, REG_MEAS_MODE, 0x10)  # mode 1
        time.sleep(0.08)
        return True
    except Exception as e:
        print("APP_START/MODE write failed:", e)
        return False

def main():
    p = argparse.ArgumentParser(description="CCS811 diagnostic helper")
    p.add_argument("--rst-gpio", type=int, default=None, help="Optional BCM GPIO to toggle RST for recovery")
    p.add_argument("--post-start-delay", type=float, default=0.25, help="Delay after APP_START before MEAS_MODE")
    args = p.parse_args()

    try:
        bus = SMBus(BUS)
    except Exception as e:
        print("Failed to open I2C bus:", e)
        return

    try:
        hw = safe_read_byte(bus, ADDR, REG_HW_ID)
        print("HW_ID: 0x%02X" % hw)
    except Exception as e:
        print("Failed to read HW_ID:", e)
        bus.close()
        return

    try:
        status = safe_read_byte(bus, ADDR, REG_STATUS)
        print("STATUS: 0x%02X" % status)
    except Exception as e:
        print("Failed to read STATUS:", e)

    try:
        raw = safe_read_block(bus, ADDR, REG_ALG, 8)
        eco2 = (raw[0]<<8) | raw[1]
        tvoc = (raw[2]<<8) | raw[3]
        status_in = raw[4]
        errid = raw[5]
        print("ALG_RAW:", raw)
        print("eCO2 =", eco2, "ppm   TVOC =", tvoc, "ppb")
        print("STATUS(in result): 0x%02X  ERROR_ID: 0x%02X" % (status_in, errid))
    except Exception as e:
        print("Failed to read ALG_RESULT_DATA:", e)

    try:
        bs = safe_read_block(bus, ADDR, REG_BASELINE, 2)
        baseline = (bs[0]<<8) | bs[1]
        print("BASELINE:", ["0x%02X" % b for b in bs], "=> 0x%04X" % baseline)
    except Exception as e:
        print("BASELINE read failed:", e)

    print("\nAttempting APP_START + set MEAS_MODE then re-read status/result...")
    if not perform_app_start(bus, post_start_delay=args.post_start_delay):
        print("APP_START attempt failed; try power-cycle and rerun this script.")
        bus.close()
        return

    time.sleep(0.25)
    try:
        status = safe_read_byte(bus, ADDR, REG_STATUS)
        raw = safe_read_block(bus, ADDR, REG_ALG, 8)
        eco2 = (raw[0]<<8) | raw[1]
        tvoc = (raw[2]<<8) | raw[3]
        status_in = raw[4]
        errid = raw[5]
        print("After APP_START -> STATUS: 0x%02X" % status)
        print("After APP_START -> ALG_RAW:", raw)
        print("eCO2 =", eco2, "ppm   TVOC =", tvoc, "ppb")
        print("STATUS(in result): 0x%02X  ERROR_ID=0x%02X" % (status_in, errid))
    except Exception as e:
        print("Read after APP_START failed:", e)

    # If user requested, toggle reset on APP_INVALID / persistent issues
    if args.rst_gpio is not None:
        if not GPIO_AVAILABLE:
            print("GPIO not available; cannot toggle RST")
        else:
            try:
                if 'errid' in locals() and (errid & 0x02):
                    print("APP_INVALID detected, toggling RST GPIO", args.rst_gpio)
                    toggle_reset(args.rst_gpio)
                    time.sleep(0.4)
                    print("Re-attempting APP_START after reset...")
                    perform_app_start(bus, post_start_delay=args.post_start_delay)
                    time.sleep(0.2)
                    try:
                        raw2 = safe_read_block(bus, ADDR, REG_ALG, 8)
                        eco2_2 = (raw2[0]<<8) | raw2[1]
                        tvoc_2 = (raw2[2]<<8) | raw2[3]
                        status_in2 = raw2[4]; errid2 = raw2[5]
                        print("Post-reset ALG_RAW:", raw2)
                        print("eCO2 =", eco2_2, "TVOC =", tvoc_2, "STATUS=0x%02X ERROR_ID=0x%02X" % (status_in2, errid2))
                    except Exception as e:
                        print("Read after reset failed:", e)
                else:
                    print("No APP_INVALID detected; not toggling RST.")
            except Exception as e:
                print("RST toggle failed:", e)

    bus.close()

if __name__ == "__main__":
    main()