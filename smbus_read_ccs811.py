#!/usr/bin/env python3
import time
import csv
import os
import smbus

BUS = 1
ADDR = 0x5A            # 0x5A or 0x5B
LOG_FILE = "ccs811_log.csv"
BASELINE_FILE = "ccs811_baseline.bin"

# Registers / commands
REG_STATUS = 0x00
REG_MEAS_MODE = 0x01
REG_ALG_RESULT_DATA = 0x02
REG_ENV_DATA = 0x05       # optional: humidity/temperature
REG_BASELINE = 0x11
REG_HW_ID = 0x20
CMD_APP_START = 0xF4

# Status bits
STATUS_DATA_READY = 0x08
STATUS_ERROR = 0x01
STATUS_APP_VALID = 0x10

bus = smbus.SMBus(BUS)

def read_reg(addr, reg):
    return bus.read_byte_data(addr, reg)

def read_alg_results(addr):
    data = bus.read_i2c_block_data(addr, REG_ALG_RESULT_DATA, 8)
    eco2 = (data[0] << 8) | data[1]
    tvoc = (data[2] << 8) | data[3]
    status = data[4]
    error_id = data[5]
    return eco2, tvoc, status, error_id, data

def read_baseline(addr):
    b = bus.read_i2c_block_data(addr, REG_BASELINE, 2)
    return (b[0] << 8) | b[1]

def write_baseline(addr, baseline_value):
    msb = (baseline_value >> 8) & 0xFF
    lsb = baseline_value & 0xFF
    bus.write_i2c_block_data(addr, REG_BASELINE, [msb, lsb])

def init_sensor(addr):
    hw = read_reg(addr, REG_HW_ID)
    print("HW_ID: 0x%02X" % hw)
    if hw != 0x81:
        raise RuntimeError("Unexpected HW_ID (0x%02X). Expected 0x81." % hw)

    status = read_reg(addr, REG_STATUS)
    print("STATUS before start: 0x%02X" % status)
    if not (status & STATUS_APP_VALID):
        raise RuntimeError("APP_VALID not set in STATUS. Application firmware missing.")

    # Start application
    bus.write_byte(addr, CMD_APP_START)
    time.sleep(0.1)
    # Set MEAS_MODE to mode 1 (1s): MEAS_MODE register value 0x10
    bus.write_byte_data(addr, REG_MEAS_MODE, 0x10)
    time.sleep(0.1)

def maybe_restore_baseline(addr):
    if os.path.exists(BASELINE_FILE):
        with open(BASELINE_FILE, "rb") as f:
            data = f.read()
        if len(data) == 2:
            baseline_value = (data[0] << 8) | data[1]
            print("Restoring baseline 0x%04X" % baseline_value)
            write_baseline(addr, baseline_value)
            time.sleep(0.1)
        else:
            print("Baseline file present but invalid length; ignoring.")

def save_baseline_file(baseline_value):
    with open(BASELINE_FILE, "wb") as f:
        f.write(bytes([(baseline_value >> 8) & 0xFF, baseline_value & 0xFF]))
    print("Saved baseline 0x%04X to %s" % (baseline_value, BASELINE_FILE))

def log_row(timestamp, eco2, tvoc):
    header = not os.path.exists(LOG_FILE)
    with open(LOG_FILE, "a", newline="") as csvfile:
        w = csv.writer(csvfile)
        if header:
            w.writerow(["timestamp", "eCO2_ppm", "TVOC_ppb"])
        w.writerow([timestamp, eco2, tvoc])

if __name__ == "__main__":
    try:
        print("Initializing sensor...")
        init_sensor(ADDR)
        maybe_restore_baseline(ADDR)

        print("Starting sampling loop. Press Ctrl+C to stop.")
        start_time = time.time()
        last_baseline_save = start_time
        baseline_save_interval = 3600.0   # save baseline every hour (after burn-in)
        burnin_min_seconds = 48 * 3600.0  # recommended burn-in period (48h)
        while True:
            status = read_reg(ADDR, REG_STATUS)
            if status & STATUS_ERROR:
                print("STATUS error flagged: 0x%02X" % status)
                # attempt to read ERROR_ID from ALG_RESULT_DATA
                try:
                    _, _, s, err, raw = read_alg_results(ADDR)
                    print("ERROR_ID: 0x%02X RAW: %s" % (err, raw))
                except Exception as ex:
                    print("Could not read ALG_RESULT_DATA for ERROR_ID:", ex)
                raise RuntimeError("Device error state")

            if status & STATUS_DATA_READY:
                eco2, tvoc, s, err, raw = read_alg_results(ADDR)
                ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
                print("%s  eCO2=%d ppm  TVOC=%d ppb  STATUS=0x%02X" % (ts, eco2, tvoc, s))
                log_row(ts, eco2, tvoc)

                # periodically save baseline (only after a while)
                elapsed = time.time() - start_time
                if elapsed >= burnin_min_seconds and (time.time() - last_baseline_save) >= baseline_save_interval:
                    try:
                        baseline_value = read_baseline(ADDR)
                        save_baseline_file(baseline_value)
                        last_baseline_save = time.time()
                    except Exception as ex:
                        print("Failed to read/save baseline:", ex)
            time.sleep(0.2)

    except KeyboardInterrupt:
        print("Stopped by user.")
    except Exception as e:
        print("Error:", e)
        print("Make sure device is in application mode, powered by 3.3V, and wired correctly.")
