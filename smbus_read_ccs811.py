import time
import smbus

BUS = 1
ADDR = 0x5A  # if your board uses 0x5B change this

bus = smbus.SMBus(BUS)

def read_alg_results(address):
    # ALG_RESULT_DATA starts at 0x02, 8 bytes
    data = bus.read_i2c_block_data(address, 0x02, 8)
    eco2 = (data[0] << 8) | data[1]
    tvoc = (data[2] << 8) | data[3]
    status = data[4]
    error_id = data[5]
    return eco2, tvoc, status, error_id, data

if __name__ == "__main__":
    try:
        eco2, tvoc, status, error_id, raw = read_alg_results(ADDR)
        print("RAW:", raw)
        print("eCO2: %d ppm" % eco2)
        print("TVOC: %d ppb" % tvoc)
        print("STATUS: 0x%02X" % status)
        print("ERROR_ID: 0x%02X" % error_id)
    except Exception as e:
        print("Failed to read via smbus:", e)
        print("Run 'sudo i2cdetect -y 1' and re-check wiring & WAKE/EN/RST states.")
