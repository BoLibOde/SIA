#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BurnIn.py

Run a CCS811 burn-in session, log data and save the sensor baseline atomically
so you can restore it later from your main sensor code.

Features:
- Ensures the CCS811 is in application mode (checks HW_ID and STATUS.APP_VALID).
- Sends APP_START and sets MEAS_MODE (default: Drive Mode 1 = 1 s).
- Logs timestamped eCO2/TVOC/STATUS/ERROR_ID to CSV while running.
- Periodically saves the 2-byte BASELINE register to disk and saves on clean exit.
- Retries on transient I2C errors; reports helpful messages.

Usage examples:
  # 48 hour burn-in, save baseline to default path
  sudo python3 BurnIn.py --hours 48 --save-baseline

  # Quick 2-hour test, baseline file in current dir
  python3 BurnIn.py --hours 2 --baseline-file ./ccs811_baseline.bin --save-baseline

  # Restore-only (write baseline to sensor then exit)
  sudo python3 BurnIn.py --restore-only --baseline-file /var/lib/ccs811/baseline.bin

Notes:
- The script requires access to the I2C bus (run as root or ensure user in i2c group).
- Default baseline file: ./data/ccs811_baseline.bin (created if necessary).
- The script will not overwrite an existing baseline file unless --force is used.
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

# Prefer smbus2 if available (better), fallback to smbus
try:
    from smbus2 import SMBus
except Exception:
    try:
        import smbus
        SMBus = smbus.SMBus
    except Exception:
        SMBus = None  # will error later

# CCS811 registers/commands
REG_STATUS = 0x00
REG_MEAS_MODE = 0x01
REG_ALG_RESULT_DATA = 0x02
REG_BASELINE = 0x11
REG_HW_ID = 0x20
CMD_APP_START = 0xF4

STATUS_ERROR = 0x01
STATUS_DATA_READY = 0x08
STATUS_APP_VALID = 0x10

DEFAULT_BASELINE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "ccs811_baseline.bin")
DEFAULT_LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "ccs811_burnin_log.csv")

running = True

def sigint_handler(signum, frame):
    global running
    running = False

signal.signal(signal.SIGINT, sigint_handler)
signal.signal(signal.SIGTERM, sigint_handler)

def safe_open_bus(busnum: int):
    if SMBus is None:
        raise RuntimeError("No SMBus/I2C library available (install smbus2 or python-smbus).")
    try:
        return SMBus(busnum)
    except Exception as e:
        raise RuntimeError(f"Failed to open I2C bus {busnum}: {e}")

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

def app_start_and_set_mode(bus, addr, drive_mode=1, interrupt=False):
    # Check HW_ID
    hw = safe_read_byte(bus, addr, REG_HW_ID)
    if hw != 0x81:
        raise RuntimeError(f"Unexpected HW_ID: 0x{hw:02X} (expected 0x81)")
    status = safe_read_byte(bus, addr, REG_STATUS)
    if not (status & STATUS_APP_VALID):
        raise RuntimeError(f"APP_VALID not set in STATUS (0x{status:02X}) - application firmware missing")
    # APP_START
    bus.write_byte(addr, CMD_APP_START)
    # give firmware time to start
    time.sleep(0.12)
    # set MEAS_MODE (drive mode)
    base_val = {0:0x00, 1:0x10, 2:0x20, 3:0x30, 4:0x40}.get(drive_mode, 0x10)
    if interrupt:
        base_val |= 0x08
    bus.write_byte_data(addr, REG_MEAS_MODE, base_val)
    time.sleep(0.05)

def read_alg(bus, addr):
    raw = safe_read_block(bus, addr, REG_ALG_RESULT_DATA, 8)
    eco2 = (raw[0] << 8) | raw[1]
    tvoc = (raw[2] << 8) | raw[3]
    status = raw[4]
    error_id = raw[5]
    return eco2, tvoc, status, error_id, raw

def read_baseline(bus, addr) -> Optional[bytes]:
    try:
        b = safe_read_block(bus, addr, REG_BASELINE, 2)
        return bytes([(b[0] & 0xFF), (b[1] & 0xFF)])
    except Exception:
        return None

def run_burnin(args):
    bus = safe_open_bus(args.bus)
    addr = args.address

    # Initialization / app mode
    print("Checking device...")
    try:
        app_start_and_set_mode(bus, addr, drive_mode=args.mode, interrupt=args.interrupt)
    except Exception as e:
        print("Initialization failed:", e)
        print("If the device is new, ensure APP_VALID is set and firmware present. Power-cycle and retry.")
        bus.close()
        return

    print("APP mode ready. MEAS_MODE set (mode %d)." % args.mode)

    # optionally restore baseline first (useful if you already have one and want to start there)
    if args.restore_only and args.baseline_file:
        bl = load_baseline_file(args.baseline_file)
        if bl is None:
            print("No baseline file found at", args.baseline_file)
        else:
            try:
                msb, lsb = bl[0], bl[1]
                safe_write_block(bus, addr, REG_BASELINE, [msb, lsb])
                time.sleep(0.05)
                print("Baseline restored to device from", args.baseline_file, "-> 0x%02X%02X" % (msb, lsb))
            except Exception as e:
                print("Failed to restore baseline:", e)
        bus.close()
        return

    # prepare logging
    log_file = args.log_file
    log_exists = os.path.exists(log_file)
    log_dir = os.path.dirname(log_file)
    if log_dir and not os.path.exists(log_dir):
        try:
            os.makedirs(log_dir, exist_ok=True)
        except Exception as e:
            print("Warning: cannot create log directory", log_dir, ":", e)

    csvfile = open(log_file, "a", newline="", encoding="utf-8")
    writer = csv.writer(csvfile)
    if not log_exists:
        writer.writerow(["ts_iso", "ts", "eCO2_ppm", "tvoc_ppb", "status_hex", "error_id_hex", "baseline_hex"])

    start_time = time.time()
    burnin_seconds = args.hours * 3600.0 if args.hours > 0 else None
    next_save = time.time() + args.save_interval if args.save_interval > 0 else None
    last_print = 0

    print("Starting sampling. Press Ctrl+C to stop.")
    try:
        while running:
            now = time.time()
            # check burn-in end
            if burnin_seconds and now - start_time >= burnin_seconds:
                print("Burn-in duration reached.")
                # read baseline and save if requested
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
                # if not exiting, continue sampling but don't save again immediately
                burnin_seconds = None

            # read result; handle transient errors gracefully
            try:
                eco2, tvoc, status, errid, raw = read_alg(bus, addr)
                iso = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(now))
                baseline_hex = ""
                # try to read baseline only when no error
                if args.baseline_file:
                    bl = read_baseline(bus, addr)
                    if bl:
                        baseline_hex = "0x%02X%02X" % (bl[0], bl[1])
                writer.writerow([iso, f"{now:.3f}", eco2, tvoc, "0x%02X" % status, "0x%02X" % errid, baseline_hex])
                csvfile.flush()
                if time.time() - last_print > 5:
                    print(f"{iso}  eCO2={eco2} ppm  TVOC={tvoc} ppb  STATUS=0x{status:02X}  ERROR_ID=0x{errid:02X}")
                    last_print = time.time()
            except Exception as e:
                print("I/O error reading sensor:", e)
                # small pause and attempt a re-init sequence
                time.sleep(0.2)
                try:
                    app_start_and_set_mode(bus, addr, drive_mode=args.mode, interrupt=args.interrupt)
                    time.sleep(0.2)
                except Exception:
                    # if re-init fails, continue loop and try later
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
        # final save on exit if requested
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
    p = argparse.ArgumentParser(description="CCS811 burn-in helper (save baseline for later use)")
    p.add_argument("--bus", type=int, default=1, help="I2C bus number (default 1)")
    p.add_argument("--address", type=lambda s: int(s,0), default=0x5A, help="I2C address (0x5A or 0x5B)")
    p.add_argument("--hours", type=float, default=48.0, help="Burn-in duration in hours (default 48). Set 0 to skip burn-in and just run.")
    p.add_argument("--sample-interval", type=float, default=1.0, help="Sampling interval in seconds to log (default 1.0). Match MEAS_MODE.")
    p.add_argument("--mode", type=int, choices=[0,1,2,3,4], default=1, help="Drive mode (0..4) - default 1 = 1s.")
    p.add_argument("--interrupt", action="store_true", help="Enable INT bit in MEAS_MODE")
    p.add_argument("--baseline-file", type=str, default=DEFAULT_BASELINE_FILE, help="Path to baseline file (2 bytes).")
    p.add_argument("--log-file", type=str, default=DEFAULT_LOG_FILE, help="CSV log file path.")
    p.add_argument("--save-baseline", action="store_true", help="Save baseline after burn-in and periodically.")
    p.add_argument("--save-interval", type=float, default=3600.0, help="Periodically save baseline every N seconds (default 3600). 0 to disable.")
    p.add_argument("--save-on-exit", action="store_true", help="Save baseline when the script is interrupted or exits.")
    p.add_argument("--exit-after-burnin", action="store_true", help="Exit when burn-in completes (after saving baseline).")
    p.add_argument("--restore-only", action="store_true", help="Only restore baseline from file to device and exit.")
    p.add_argument("--force", action="store_true", help="Overwrite baseline file if present (when saving).")
    args = p.parse_args()

    if args.save_baseline and args.baseline_file and os.path.exists(args.baseline_file) and not args.force:
        print("Baseline file already exists at", args.baseline_file)
        print("Use --force to overwrite or move/delete the existing file if you want a fresh baseline.")
        # Still allow running without saving; proceed.

    # If restore-only, do restore then exit (handled inside run)
    try:
        run_burnin(args)
    except KeyboardInterrupt:
        print("Interrupted by user")
    except Exception as e:
        print("Fatal error:", e)
        sys.exit(2)

if __name__ == "__main__":
    main()