import time
from smbus2 import SMBus

SCD41_I2C_ADDR = 0x62
COMMAND_START_MEASUREMENT = [0x21, 0xB1]
COMMAND_GET_DATA_READY = [0xE4, 0xB8]
COMMAND_READ_MEASUREMENT = [0xEC, 0x05]
COMMAND_STOP_MEASUREMENT = [0x3F, 0x86]
COMMAND_SOFT_RESET = [0x36, 0x82]

def calculate_crc(data):
    crc = 0xFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x80:
                crc = (crc << 1) ^ 0x31
            else:
                crc <<= 1
    return crc & 0xFF

def main():
    with SMBus(1) as bus:
        # Reset the sensor
        print("Resetting SCD41...")
        try:
            bus.write_i2c_block_data(SCD41_I2C_ADDR, COMMAND_SOFT_RESET[0], COMMAND_SOFT_RESET[1:])
            time.sleep(1)
        except OSError as e:
            print(f"Error during soft reset: {e}")
            return

        # Start measurement
        print("Starting periodic measurements...")
        bus.write_i2c_block_data(SCD41_I2C_ADDR, COMMAND_START_MEASUREMENT[0], COMMAND_START_MEASUREMENT[1:])
        time.sleep(15)  # Initial warm-up

        try:
            while True:
                try:
                    # Check if data is ready
                    bus.write_i2c_block_data(SCD41_I2C_ADDR, COMMAND_GET_DATA_READY[0], COMMAND_GET_DATA_READY[1:])
                    response = bus.read_i2c_block_data(SCD41_I2C_ADDR, 0x00, 3)
                    print(f"Data ready response: {response}")

                    if (response[0] & 0x07FF) != 0:
                        # If data is ready, read measurement
                        bus.write_i2c_block_data(SCD41_I2C_ADDR, COMMAND_READ_MEASUREMENT[0], COMMAND_READ_MEASUREMENT[1:])
                        data = bus.read_i2c_block_data(SCD41_I2C_ADDR, 0x00, 9)
                        print(f"Raw measurement data: {data}")
                    else:
                        print("Data not ready, waiting...")
                    time.sleep(10)  # Delay between checks
                except OSError as e:
                    print(f"I2C error during measurements: {e}")
        except KeyboardInterrupt:
            print("Exiting measurement loop.")
        finally:
            print("Stopping measurements.")
            try:
                bus.write_i2c_block_data(SCD41_I2C_ADDR, COMMAND_STOP_MEASUREMENT[0], COMMAND_STOP_MEASUREMENT[1:])
            except OSError as e:
                print(f"Error stopping measurements: {e}")

if __name__ == "__main__":
    main()