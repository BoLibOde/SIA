import time
from smbus2 import SMBus

# SCD41 sensor constants
SCD41_I2C_ADDR = 0x62
COMMAND_START_MEASUREMENT = [0x21, 0xB1]  # Command to start periodic measurements
COMMAND_GET_DATA_READY = [0xE4, 0xB8]  # Check if data is ready
COMMAND_READ_MEASUREMENT = [0xEC, 0x05]  # Read measurement results
COMMAND_STOP_MEASUREMENT = [0x3F, 0x86]  # Stop periodic measurements
COMMAND_SOFT_RESET = [0x36, 0x82]  # Soft reset


def calculate_crc(data):
    """Calculate CRC for Sensirion sensors."""
    crc = 0xFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x80:
                crc = (crc << 1) ^ 0x31
            else:
                crc <<= 1
    return crc & 0xFF


def is_data_ready(bus, address):
    """Check if data is ready to be read."""
    print("Checking if data is ready...")
    bus.write_i2c_block_data(address, COMMAND_GET_DATA_READY[0], COMMAND_GET_DATA_READY[1:])
    time.sleep(0.005)  # Short delay for response
    response = bus.read_i2c_block_data(address, 0x00, 3)
    print(f"Data ready response: {response}")

    # Corrected: Check data ready flag in the 1st byte
    ready_flag = (response[0] & 0x07FF)
    return ready_flag != 0


def scd41_read_measurement(bus, address):
    """Read CO2, temperature, and humidity values from the SCD41."""
    print("Reading measurement from sensor...")
    bus.write_i2c_block_data(address, COMMAND_READ_MEASUREMENT[0], COMMAND_READ_MEASUREMENT[1:])
    time.sleep(0.005)  # Short delay for sensor response

    # Read 9 bytes: 6 data bytes + 3 CRC bytes
    data = bus.read_i2c_block_data(address, 0x00, 9)
    print(f"Raw sensor data: {data}")

    # Verify CRC for the three measurement data fields
    for i in range(3):
        if calculate_crc(data[i * 3: i * 3 + 2]) != data[i * 3 + 2]:
            raise ValueError("CRC mismatch on data field")

    # Parse CO2, temperature, humidity from raw data and apply equations
    co2 = int.from_bytes(data[0:2], 'big')
    temp_raw = int.from_bytes(data[3:5], 'big')
    humidity_raw = int.from_bytes(data[6:8], 'big')

    temp = -45 + (175 * temp_raw) / 65535.0
    humidity = 100 * humidity_raw / 65535.0

    return co2, temp, humidity


def main():
    with SMBus(1) as bus:  # Open I2C bus (usually /dev/i2c-1)
        # Perform a soft reset to clean the sensor state
        print("Resetting SCD41...")
        bus.write_i2c_block_data(SCD41_I2C_ADDR, COMMAND_SOFT_RESET[0], COMMAND_SOFT_RESET[1:])
        time.sleep(1)  # Wait for 1 second after reset

        # Start periodic measurement
        print("Starting periodic measurements... Waiting for stabilization...")
        bus.write_i2c_block_data(SCD41_I2C_ADDR, COMMAND_START_MEASUREMENT[0], COMMAND_START_MEASUREMENT[1:])
        time.sleep(15)  # Wait 15 seconds for the sensor to stabilize and take its first measurement

        try:
            while True:
                # Check if the data is ready
                if is_data_ready(bus, SCD41_I2C_ADDR):
                    co2, temp, humidity = scd41_read_measurement(bus, SCD41_I2C_ADDR)
                    print(f"CO2: {co2} ppm, Temperature: {temp:.2f} °C, Humidity: {humidity:.2f} %")
                else:
                    print("Data not ready, waiting...")

                # Wait for the next measurement interval
                time.sleep(5)

        except KeyboardInterrupt:
            print("\nStopping measurements...")
        finally:
            # Stop periodic measurement
            print("Stopping sensor measurements...")
            bus.write_i2c_block_data(SCD41_I2C_ADDR, COMMAND_STOP_MEASUREMENT[0], COMMAND_STOP_MEASUREMENT[1:])
            print("SCD41 measurement stopped.")


if __name__ == "__main__":
    main()


