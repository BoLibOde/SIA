#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BurnIn.py (updated)

- Increased safe startup/post-APP_START delays to reduce APP_INVALID occurrences.
- Optional --rst-gpio to toggle CCS811 RST pin (BCM) on persistent invalid/error conditions.
- More aggressive recovery: retries, small read retries, APP_START re-send, optional RST toggle.
- Plausibility filtering of samples to avoid logging corrupted spikes.
- Periodic and on-exit atomic baseline save.

Usage examples:
  sudo python3 BurnIn.py --hours 48 --save-baseline --save-on-exit --baseline-file /var/lib/ccs811/baseline.bin
  sudo python3 BurnIn.py --hours 0.01 --save-baseline --baseline-file ./data/test_baseline.bin --rst-gpio 18
"""
from __future__ import annotations
import argparse
import os
import time
import csv
import signal
import sys
import tempfile
from typing import Optional

# Prefer smbus2
try:
    from smbus2 import SMBus
except Exception:
    try:
        import smbus
        SMBus = smbus.SMBus
    except Exception:
        SMBus = None

# Optional GPIO support for reset
try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except Exception:
    GPIO_AVAILABLE = False

# CCS811 regs
REG_STATUS = 0x00
REG_MEAS_MODE = 0x01
REG_ALG_RESULT_DATA = 0x02
REG_ENV_DATA = 0x05
REG_BASELINE = 0x11
REG_HW_ID = 0x20
CMD_APP_START = 0xF4

STATUS_ERROR = 0x01
STATUS_DATA_READY = 0x08
STATUS_APP_VALID = 0x10

DEFAULT_BASELINE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "ccs811_baseline.bin")
DEFAULT_LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "ccs811_burnin_log.csv")

# Plausibility thresholds
MAX_ECO2_PLAUSIBLE = 5000
MAX_TVOC_PLAUSIBLE = 10000

running = True
def sigint_handler(signum, frame):
    global running
    running = False
signal.signal(signal.SIGINT, sigint_handler)
signal.signal(signal.SIGTERM, sigint_handler)

# SMBus wrappers
def safe_open_bus(busnum: int):
    if SMBus is None:
        raise RuntimeError("No SMBus/I2C library available (install smbus2 or python-smbus).")
    return SMBus(busnum)

def safe_read_byte(bus, addr, reg, retries=3, delay=0.05):
    for i in range(retries):
        try:
            return bus.read_byte_data(addr, reg)
        except OSError:
            if i < retries - 1:
                time.sleep(delay)
                continue
            raise

def safe_read_block(bus, addr, reg, length, retries=3, delay=0.05):
    for i in range(retries):
        try:
            return bus.read_i2c_block_data(addr, reg, length)
        except OSError:
            if i < retries - 1:
                time.sleep(delay)
                continue
            raise

def safe_write_block(bus, addr, reg, data, retries=3, delay=0.05):
    for i in range(retries):
        try:
            return bus.write_i2c_block_data(addr, reg, data)
        except OSError:
            if i < retries - 1:
                time.sleep(delay)
                continue
            raise

# Baseline helpers
def save_baseline_file_atomic(baseline_bytes: bytes, path: str):
    d = os.path.dirname(path)
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d or ".", prefix=".tmp_baseline_")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(baseline_bytes)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except Exception:
            pass
        raise

def load_baseline_file(path: str) -> Optional[bytes]:
    if not path or not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        data = f.read()
    if len(data) != 2:
        return None
    return data

# GPIO reset
def toggle_gpio_reset(pin: int, hold_ms: int = 150):
    if not GPIO_AVAILABLE:
        raise RuntimeError("RPi.GPIO not available")
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(pin, GPIO.OUT, initial=GPIO.HIGH)
    GPIO.output(pin, GPIO.LOW)
    time.sleep(hold_ms / 1000.0)
    GPIO.output(pin, GPIO.HIGH)
    time.sleep(0.25)
    GPIO.cleanup(pin)

# CCS811 helpers
def app_start_and_mode(bus, addr, drive_mode=1, interrupt=False, post_start_delay=0.20):
    hw = safe_read_byte(bus, addr, REG_HW_ID)
    if hw != 0x81:
        raise RuntimeError(f"Unexpected HW_ID: 0x{hw:02X}")
    status = safe_read_byte(bus, addr, REG_STATUS)
    if not (status & STATUS_APP_VALID):
        raise RuntimeError(f"APP_VALID not set (STATUS=0x{status:02X})")
    bus.write_byte(addr, CMD_APP_START)
    time.sleep(post_start_delay)
    base_val = {0:0x00,1:0x10,2:0x20,3:0x30,4:0x40}.get(drive_mode,0x10)
    if interrupt:
        base_val |= 0x08
    bus.write_byte_data(addr, REG_MEAS_MODE, base_val)
    time.sleep(0.08)

def read_alg(bus, addr):
    raw = safe_read_block(bus, addr, REG_ALG_RESULT_DATA, 8)
    eco2 = (raw[0] << 8) | raw[1]
    tvoc = (raw[2] << 8) | raw[3]
    status = raw[4]
    errid = raw[5]
    return eco2, tvoc, status, errid, raw

def read_baseline(bus, addr) -> Optional[bytes]:
    try:
        b = safe_read_block(bus, addr, REG_BASELINE, 2)
        return bytes([b[0] & 0xFF, b[1] & 0xFF])
    except Exception:
        return None

def write_baseline(bus, addr, bl_bytes: bytes):
    msb, lsb = bl_bytes[0], bl_bytes[1]
    safe_write_block(bus, addr, REG_BASELINE, [msb, lsb])
    time.sleep(0.05)

# Main burn-in
def run_burnin(args):
    bus = safe_open_bus(args.bus)
    addr = args.address

    # startup delay
    time.sleep(max(0.5, args.startup_delay))

    # init with retries, optional RST on repeated fails
    init_ok = False
    for attempt in range(4):
        try:
            app_start_and_mode(bus, addr, drive_mode=args.mode, interrupt=args.interrupt, post_start_delay=args.post_start_delay)
            init_ok = True
            break
        except Exception as e:
            print(f"Init attempt {attempt+1} failed: {e}")
            time.sleep(0.25)
            if args.rst_gpio is not None and GPIO_AVAILABLE:
                try:
                    print("Toggling RST (init retry)...")
                    toggle_gpio_reset(args.rst_gpio)
                    time.sleep(0.3)
                except Exception as ge:
                    print("RST toggle failed:", ge)
    if not init_ok:
        print("Initialization failed after retries. Exiting.")
        bus.close()
        return

    # optional restore baseline
    if args.baseline_file and args.restore_before:
        bl = load_baseline_file(args.baseline_file)
        if bl:
            for i in range(3):
                try:
                    write_baseline(bus, addr, bl)
                    rb = read_baseline(bus, addr)
                    if rb == bl:
                        print(f"Restored baseline -> 0x{bl[0]:02X}{bl[1]:02X}")
                        break
                except Exception as e:
                    print("Baseline restore attempt failed:", e)
                time.sleep(0.2)

    print("APP mode ready. MEAS_MODE set (mode %d)." % args.mode)

    # logging setup
    log_file = args.log_file
    log_exists = os.path.exists(log_file)
    if log_file:
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            try:
                os.makedirs(log_dir, exist_ok=True)
            except Exception:
                pass
    csvfile = open(log_file, "a", newline="", encoding="utf-8")
    writer = csv.writer(csvfile)
    if not log_exists:
        writer.writerow(["ts_iso","ts","eCO2_ppm","tvoc_ppb","status_hex","error_id_hex","baseline_hex","note"])

    start_time = time.time()
    burnin_seconds = args.hours * 3600.0 if args.hours > 0 else None
    next_save = time.time() + args.save_interval if args.save_interval > 0 else None
    last_print = 0

    # counters for recovery
    consecutive_invalid = 0
    INVALID_RESET_THRESHOLD = max(6, args.invalid_threshold)

    print("Starting sampling. Press Ctrl+C to stop.")
    try:
        while running:
            now = time.time()
            if burnin_seconds and now - start_time >= burnin_seconds:
                print("Burn-in duration reached.")
                if args.save_baseline and args.baseline_file:
                    bl = read_baseline(bus, addr)
                    if bl:
                        try:
                            save_baseline_file_atomic(bl, args.baseline_file)
                            print("Saved baseline to", args.baseline_file, "-> 0x%02X%02X" % (bl[0], bl[1]))
                        except Exception as e:
                            print("Failed to save baseline file:", e)
                if args.exit_after_burnin:
                    break
                burnin_seconds = None

            try:
                eco2, tvoc, status, errid, raw = read_alg(bus, addr)
                iso = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(now))
                baseline_hex = ""
                if args.baseline_file:
                    bl = read_baseline(bus, addr)
                    if bl:
                        baseline_hex = "0x%02X%02X" % (bl[0], bl[1])

                note = ""
                plausible = True
                # basic plausibility checks
                if eco2 == 0 and tvoc == 0:
                    plausible = False; note = "zero_reading"
                elif eco2 < 350 or eco2 > MAX_ECO2_PLAUSIBLE:
                    plausible = False; note = "eco2_out_of_range"
                elif tvoc < 0 or tvoc > MAX_TVOC_PLAUSIBLE:
                    plausible = False; note = "tvoc_out_of_range"
                if all(b in (0xFD,0xFF,0x7F,0x00) for b in raw[:8]) and not (eco2==0 and tvoc==0):
                    plausible = False; note = "raw_fill"

                writer.writerow([iso, f"{now:.3f}", eco2, tvoc, "0x%02X"%status, "0x%02X"%errid, baseline_hex, note])
                csvfile.flush()

                if plausible:
                    consecutive_invalid = 0
                    if time.time() - last_print > 5:
                        print(f"{iso} eCO2={eco2} ppm TVOC={tvoc} ppb STATUS=0x{status:02X} ERROR_ID=0x{errid:02X}")
                        last_print = time.time()
                else:
                    consecutive_invalid += 1
                    print(f"{iso} INVALID sample ({note}) eCO2={eco2} TVOC={tvoc} STATUS=0x{status:02X} ERROR_ID=0x{errid:02X} (cnt={consecutive_invalid})")
                    # try a few quick retries
                    recovered = False
                    for i in range(2):
                        time.sleep(0.12)
                        try:
                            eco2b, tvocb, statusb, erridb, rawb = read_alg(bus, addr)
                            if (350 <= eco2b <= MAX_ECO2_PLAUSIBLE) and (0 <= tvocb <= MAX_TVOC_PLAUSIBLE):
                                recovered = True
                                eco2, tvoc, status, errid, raw = eco2b, tvocb, statusb, erridb, rawb
                                writer.writerow([iso + "_rec", f"{time.time():.3f}", eco2, tvoc, "0x%02X"%status, "0x%02X"%errid, baseline_hex, "recovered_on_retry"])
                                csvfile.flush()
                                consecutive_invalid = 0
                                break
                        except Exception:
                            pass

                    if not recovered:
                        # try APP_START sequence
                        try:
                            app_start_and_mode(bus, addr, drive_mode=args.mode, interrupt=args.interrupt, post_start_delay=args.post_start_delay)
                            time.sleep(0.15)
                        except Exception as e:
                            print("APP_START retry failed:", e)
                        # if still invalid enough times, toggle RST if available
                        if consecutive_invalid >= INVALID_RESET_THRESHOLD and args.rst_gpio is not None and GPIO_AVAILABLE:
                            try:
                                print("Persistent invalid readings; toggling RST GPIO", args.rst_gpio)
                                toggle_gpio_reset(args.rst_gpio)
                                time.sleep(0.5)
                                # re-init after reset
                                app_start_and_mode(bus, addr, drive_mode=args.mode, interrupt=args.interrupt, post_start_delay=args.post_start_delay)
                                consecutive_invalid = 0
                            except Exception as e:
                                print("RST recovery failed:", e)

            except Exception as e:
                print("I/O error reading sensor:", e)
                time.sleep(0.5)
                try:
                    app_start_and_mode(bus, addr, drive_mode=args.mode, interrupt=args.interrupt, post_start_delay=args.post_start_delay)
                except Exception:
                    pass

            # periodic baseline save
            if next_save and time.time() >= next_save:
                if args.save_baseline and args.baseline_file:
                    try:
                        bl = read_baseline(bus, addr)
                        if bl:
                            save_baseline_file_atomic(bl, args.baseline_file)
                            print("Periodic baseline saved to", args.baseline_file, "-> 0x%02X%02X" % (bl[0], bl[1]))
                    except Exception as e:
                        print("Periodic baseline save failed:", e)
                next_save = time.time() + args.save_interval

            time.sleep(max(0.2, args.sample_interval))
    finally:
        if args.save_on_exit and args.save_baseline and args.baseline_file:
            try:
                bl = read_baseline(bus, addr)
                if bl:
                    save_baseline_file_atomic(bl, args.baseline_file)
                    print("Saved baseline on exit to", args.baseline_file, "-> 0x%02X%02X" % (bl[0], bl[1]))
            except Exception as e:
                print("Failed to save baseline on exit:", e)
        csvfile.close()
        try:
            bus.close()
        except Exception:
            pass
        print("Burn-in script exiting.")

def main():
    p = argparse.ArgumentParser(description="Robust CCS811 burn-in helper")
    p.add_argument("--bus", type=int, default=1)
    p.add_argument("--address", type=lambda s:int(s,0), default=0x5A)
    p.add_argument("--hours", type=float, default=48.0)
    p.add_argument("--sample-interval", type=float, default=1.0)
    p.add_argument("--mode", type=int, choices=[0,1,2,3,4], default=1)
    p.add_argument("--interrupt", action="store_true")
    p.add_argument("--baseline-file", type=str, default=DEFAULT_BASELINE_FILE)
    p.add_argument("--log-file", type=str, default=DEFAULT_LOG_FILE)
    p.add_argument("--save-baseline", action="store_true")
    p.add_argument("--save-interval", type=float, default=3600.0)
    p.add_argument("--save-on-exit", action="store_true")
    p.add_argument("--exit-after-burnin", action="store_true")
    p.add_argument("--restore-before", action="store_true")
    p.add_argument("--restore-only", action="store_true")
    p.add_argument("--force", action="store_true")
    p.add_argument("--rst-gpio", type=int, default=None, help="Optional BCM GPIO for RST")
    p.add_argument("--startup-delay", type=float, default=0.8, help="Delay after process start before I2C init (seconds)")
    p.add_argument("--post-start-delay", type=float, default=0.25, help="Delay after APP_START before MEAS_MODE (seconds)")
    p.add_argument("--invalid-threshold", type=int, default=6, help="Consecutive invalid reads to trigger RST")
    args = p.parse_args()

    if args.rst_gpio is not None and not GPIO_AVAILABLE:
        print("Warning: GPIO requested but RPi.GPIO not available. --rst-gpio ignored.")

    if args.restore_only:
        try:
            bus = safe_open_bus(args.bus)
            time.sleep(max(0.5, args.startup_delay))
            if args.baseline_file:
                bl = load_baseline_file(args.baseline_file)
                if bl:
                    write_baseline(bus, args.address, bl)
                    print("Restored baseline to device -> 0x%02X%02X" % (bl[0], bl[1]))
                else:
                    print("No baseline file found at", args.baseline_file)
            bus.close()
        except Exception as e:
            print("Restore-only failed:", e)
        return

    try:
        run_burnin(args)
    except KeyboardInterrupt:
        print("Interrupted by user")
    except Exception as e:
        print("Fatal error:", e)
        sys.exit(2)

if __name__ == "__main__":
    main()