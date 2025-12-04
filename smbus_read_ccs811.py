#!/usr/bin/env python3
import time
import smbus
import errno
import subprocess

BUS = 1
ADDR = 0x5A  # change to 0x5B if your board uses that

# CCS811 registers / commands / masks
REG_STATUS = 0x00
REG_MEAS_MODE = 0x01
REG_ALG_RESULT_DATA = 0x02
REG_HW_ID = 0x20
REG_BASELINE = 0x11
CMD_APP_START = 0xF4

# Status bits
STATUS_DATA_READY = 0x08
STATUS_ERROR = 0x01
STATUS_APP_VALID = 0x10

bus = smbus.SMBus(BUS)

def read_reg(addr, reg, retries=3, delay=0.05):
    for i in range(retries):
        try:
            return bus.read_byte_data(addr, reg)
        except OSError as e:
            if getattr(e, 'errno', None) == errno.EIO and i < retries - 1:
                time.sleep(delay)
                continue
            raise

def read_block(addr, reg, length, retries=3, delay=0.05):
    for i in range(retries):
        try:
            return bus.read_i2c_block_data(addr, reg, length)
        except OSError as e:
            if getattr(e, 'errno', None) == errno.EIO and i < retries - 1:
                time.sleep(delay)
                continue
            raise

def read_alg_results(addr):
    data = read_block(addr, REG_ALG_RESULT_DATA, 8)
    eco2 = (data[0] << 8) | data[1]
    tvoc = (data[2] << 8) | data[3]
    status = data[4]
    error_id = data[5]
    return eco2, tvoc, status, error_id, data

def init_and_start(addr):
    hw = read_reg(addr, REG_HW_ID)
    print("HW_ID: 0x%02X" % hw)
    if hw != 0x81:
        raise RuntimeError("Unexpected HW_ID (0x%02X). Expected 0x81." % hw)
    status = read_reg(addr, REG_STATUS)
    print("STATUS before start: 0x%02X" % status)
    if not (status & STATUS_APP_VALID):
        raise RuntimeError("APP_VALID not set in STATUS. Application firmware missing.")
    print("Sending APP_START...")
    bus.write_byte(addr, CMD_APP_START)
    time.sleep(0.1)
    print("Setting MEAS_MODE to 1s (0x10)...")
    bus.write_byte_data(addr, REG_MEAS_MODE, 0x10)
    time.sleep(0.1)

def try_reinit(addr):
    print("Attempting re-initialization sequence...")
    try:
        init_and_start(addr)
        print("Re-init successful.")
        return True
    except Exception as e:
        print("Re-init failed:", e)
        return False

def show_recent_dmesg():
    try:
        out = subprocess.check_output(["dmesg", "--ctime", "--kernel", "--follow=false"], stderr=subprocess.DEVNULL)
        lines = out.decode(errors='ignore').splitlines()
        for l in lines[-30:]:
            if 'i2c' in l.lower() or 'bcm' in l.lower():
                print("dmesg:", l)
    except Exception:
        pass

if __name__ == "__main__":
    try:
        print("Initializing sensor...")
        init_and_start(ADDR)
        print("Starting read loop (press Ctrl+C to stop).")
        while True:
            try:
                status = read_reg(ADDR, REG_STATUS)
            except OSError as e:
                print("I/O error reading STATUS:", e)
                # transient retry and reinit logic
                ok = try_reinit(ADDR)
                if not ok:
                    print("If re-init failed, please power-cycle the module and check wiring/power.")
                    show_recent_dmesg()
                    raise
                else:
                    time.sleep(1)
                    continue

            print("STATUS: 0x%02X" % status)
            if status & STATUS_ERROR:
                print("Device reported ERROR (STATUS=0x%02X). Trying to read ERROR_ID..." % status)
                try:
                    _, _, s, err, raw = read_alg_results(ADDR)
                    print("ERROR_ID: 0x%02X RAW: %s" % (err, raw))
                except Exception as ex:
                    print("Could not read ALG_RESULT_DATA for ERROR_ID:", ex)
                # try re-init once
                if not try_reinit(ADDR):
                    print("Re-init failed after ERROR. Please check hardware, WAKE/RST pins and power.")
                    show_recent_dmesg()
                    raise RuntimeError("Device remains in error state.")
                continue

            if status & STATUS_DATA_READY:
                try:
                    eco2, tvoc, s, err, raw = read_alg_results(ADDR)
                    print("ALG_RESULT_DATA RAW:", raw)
                    print("eCO2: %d ppm  TVOC: %d ppb  STATUS: 0x%02X  ERROR_ID: 0x%02X" % (eco2, tvoc, s, err))
                except OSError as e:
                    print("I/O error reading ALG_RESULT_DATA:", e)
                    # retry policy: try re-init and continue
                    if not try_reinit(ADDR):
                        print("Re-init failed after I/O error. Please power-cycle and check wiring.")
                        show_recent_dmesg()
                        raise
            time.sleep(0.8)

    except KeyboardInterrupt:
        print("Stopped by user.")
    except Exception as e:
        print("Fatal error:", e)
        print("Diagnostic checklist:")
        print("- Confirm VCC is a solid 3.3V (measure while running).")
        print("- Verify WAKE / nWAKE / RST pin states per your breakout documentation.")
        print("- If using long wires or breadboard, try a short cable or direct soldering.")
        print("- Remove other I2C devices and test isolation.")
        print("- Power-cycle the module and rerun.")
        print("Run 'dmesg | tail -n 40' and paste output here if the problem persists.")
