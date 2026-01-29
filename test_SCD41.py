import time
from smbus2 import SMBus

# Constants for the SCD41 sensor
SCD41_I2C_ADDR = 0x62
COMMAND_START_MEASUREMENT = [0x21, 0xB1]  # Command to start periodic measurements
COMMAND_GET_DATA_READY = [0xE4, 0xB8]  # Check if data is ready
COMMAND_READ_MEASUREMENT = [0xEC, 0x05]  # Read measurement results
COMMAND_STOP_MEASUREMENT = [0x3F, 0x86]  # Stop periodic measurements


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


def scd41_read_measurement(bus, address):
    """Read CO2, temperature, and humidity values from the SCD41."""
    bus.write_i2c_block_data(address, COMMAND_READ_MEASUREMENT[0], COMMAND_READ_MEASUREMENT[1:])
    time.sleep(0.005)  # Wait for the sensor

    # Read 9 bytes (6 data bytes + 3 CRC bytes)
    data = bus.read_i2c_block_data(address, 0x00, 9)

    # Verify CRC for all three data fields: CO2, temperature, humidity
    for i in range(3):
        if calculate_crc(data[i * 3:i * 3 + 2]) != data[i * 3 + 2]:
            raise ValueError("CRC mismatch")

    # Extract and calculate sensor values
    co2 = int.from_bytes(data[0:2], 'big')
    temp_raw = int.from_bytes(data[3:5], 'big')
    humidity_raw = int.from_bytes(data[6:8], 'big')

    temp = -45 + (175 * temp_raw) / 65535.0
    humidity = 100 * humidity_raw / 65535.0

    return co2, temp, humidity


def main():
    with SMBus(1) as bus:  # Open I2C bus (usually /dev/i2c-1)
        # Start periodic measurement
        bus.write_i2c_block_data(SCD41_I2C_ADDR, COMMAND_START_MEASUREMENT[0], COMMAND_START_MEASUREMENT[1:])
        time.sleep(1)  # Wait at least 5 seconds for first measurement

        try:
            while True:
                # Poll for data readiness
                bus.write_i2c_block_data(SCD41_I2C_ADDR, COMMAND_GET_DATA_READY[0], COMMAND_GET_DATA_READY[1:])
                time.sleep(0.005)
                ready = bus.read_i2c_block_data(SCD41_I2C_ADDR, 0x00, 3)

                if ready[1] & 0x07FF:  # Data is ready
                    co2, temp, humidity = scd41_read_measurement(bus, SCD41_I2C_ADDR)
                    print(f"CO2: {co2} ppm, Temperature: {temp:.2f} °C, Humidity: {humidity:.2f} %")
                else:
                    print("Sensor data not ready, retrying...")
                time.sleep(5)  # Wait for the next measurement (5-second interval)

        except KeyboardInterrupt:
            print("\nStopping measurements...")
        finally:
            # Stop periodic measurement
            bus.write_i2c_block_data(SCD41_I2C_ADDR, COMMAND_STOP_MEASUREMENT[0], COMMAND_STOP_MEASUREMENT[1:])
            print("SCD41 measurement stopped.")


if __name__ == "__main__":
    main()