import time
import threading
import logging
from collections import namedtuple
from smbus2 import SMBus

_LOG = logging.getLogger("sensor")

# SCD41 sensor constants
SCD41_I2C_ADDR = 0x62
COMMAND_START_MEASUREMENT = [0x21, 0xB1]
COMMAND_GET_DATA_READY = [0xE4, 0xB8]
COMMAND_READ_MEASUREMENT = [0xEC, 0x05]
COMMAND_STOP_MEASUREMENT = [0x3F, 0x86]
COMMAND_SOFT_RESET = [0x36, 0x82]

# Named tuple for sensor samples (removed db, added humidity)
SensorSample = namedtuple("SensorSample", ["temp", "co2", "humidity"])


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
    bus.write_i2c_block_data(address, COMMAND_GET_DATA_READY[0], COMMAND_GET_DATA_READY[1:])
    time.sleep(0.005)
    response = bus.read_i2c_block_data(address, 0x00, 3)
    ready_flag = (response[0] & 0x07FF)
    return ready_flag != 0


def scd41_read_measurement(bus, address):
    """Read CO2, temperature, and humidity values from the SCD41."""
    bus.write_i2c_block_data(address, COMMAND_READ_MEASUREMENT[0], COMMAND_READ_MEASUREMENT[1:])
    time.sleep(0.005)

    data = bus.read_i2c_block_data(address, 0x00, 9)

    # Verify CRC for the three measurement data fields
    for i in range(3):
        if calculate_crc(data[i * 3: i * 3 + 2]) != data[i * 3 + 2]:
            raise ValueError("CRC mismatch on data field")

    # Parse CO2, temperature, humidity from raw data
    co2 = int.from_bytes(data[0:2], 'big')
    temp_raw = int.from_bytes(data[3:5], 'big')
    humidity_raw = int.from_bytes(data[6:8], 'big')

    temp = -45 + (175 * temp_raw) / 65535.0
    humidity = 100 * humidity_raw / 65535.0

    return co2, temp, humidity


class SensorRunner:
    """
    Manages sensor reading in a background thread.
    Supports both hardware (SCD41) and simulation modes.
    """

    def __init__(self, simulation_mode=False, buffer_size=10):
        self.simulation_mode = simulation_mode
        self.buffer_size = buffer_size
        self.sensor_buffer = []
        self._running = False
        self._thread = None
        self._bus = None

    def start(self, interval=2.0):
        """Start the sensor polling thread."""
        if self._running:
            _LOG.warning("SensorRunner already running")
            return

        self._running = True
        self._thread = threading.Thread(target=self._run_loop, args=(interval,), daemon=True)
        self._thread.start()
        _LOG.info("SensorRunner started (simulation=%s, interval=%.1fs)", self.simulation_mode, interval)

    def stop(self):
        """Stop the sensor polling thread."""
        if not self._running:
            return

        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

        # Clean up hardware
        if self._bus and not self.simulation_mode:
            try:
                self._bus.write_i2c_block_data(SCD41_I2C_ADDR, COMMAND_STOP_MEASUREMENT[0],
                                               COMMAND_STOP_MEASUREMENT[1:])
                self._bus.close()
            except Exception as e:
                _LOG.error("Error stopping sensor: %s", e)

        _LOG.info("SensorRunner stopped")

    def _run_loop(self, interval):
        """Main sensor polling loop."""
        if self.simulation_mode:
            self._simulation_loop(interval)
        else:
            self._hardware_loop(interval)

    def _simulation_loop(self, interval):
        """Simulated sensor data for testing."""
        import random
        _LOG.info("Running in SIMULATION mode")

        while self._running:
            # Generate simulated values
            temp = round(20.0 + random.uniform(-2, 2), 1)
            co2 = int(400 + random.uniform(-50, 150))
            humidity = round(45.0 + random.uniform(-5, 5), 1)

            sample = SensorSample(temp=temp, co2=co2, humidity=humidity)
            self._add_sample(sample)
            _LOG.debug("Simulated sample: %s", sample)

            time.sleep(interval)

    def _hardware_loop(self, interval):
        """Read from actual SCD41 hardware."""
        _LOG.info("Running in HARDWARE mode")

        try:
            self._bus = SMBus(1)

            # Soft reset
            _LOG.info("Resetting SCD41...")
            self._bus.write_i2c_block_data(SCD41_I2C_ADDR, COMMAND_SOFT_RESET[0], COMMAND_SOFT_RESET[1:])
            time.sleep(1)

            # Start periodic measurement
            _LOG.info("Starting SCD41 measurements...")
            self._bus.write_i2c_block_data(SCD41_I2C_ADDR, COMMAND_START_MEASUREMENT[0], COMMAND_START_MEASUREMENT[1:])
            time.sleep(5)  # Wait for first measurement

            while self._running:
                try:
                    if is_data_ready(self._bus, SCD41_I2C_ADDR):
                        co2, temp, humidity = scd41_read_measurement(self._bus, SCD41_I2C_ADDR)

                        sample = SensorSample(temp=temp, co2=co2, humidity=humidity)
                        self._add_sample(sample)
                        _LOG.info("Hardware sample: CO2=%d ppm, Temp=%.1f°C, Humidity=%.1f%%", co2, temp, humidity)
                    else:
                        _LOG.debug("Sensor data not ready")
                except Exception as e:
                    _LOG.error("Error reading sensor: %s", e)

                time.sleep(interval)

        except Exception as e:
            _LOG.exception("Fatal error in hardware loop: %s", e)
            _LOG.warning("Falling back to simulation mode")
            self._simulation_loop(interval)

    def _add_sample(self, sample):
        """Add a sample to the buffer (FIFO)."""
        self.sensor_buffer.append(sample)
        if len(self.sensor_buffer) > self.buffer_size:
            self.sensor_buffer.pop(0)


def main():
    """Standalone test function."""
    with SMBus(1) as bus:
        # Perform a soft reset
        print("Resetting SCD41...")
        bus.write_i2c_block_data(SCD41_I2C_ADDR, COMMAND_SOFT_RESET[0], COMMAND_SOFT_RESET[1:])
        time.sleep(1)

        # Start periodic measurement
        print("Starting periodic measurements...")
        bus.write_i2c_block_data(SCD41_I2C_ADDR, COMMAND_START_MEASUREMENT[0], COMMAND_START_MEASUREMENT[1:])
        time.sleep(5)

        try:
            while True:
                if is_data_ready(bus, SCD41_I2C_ADDR):
                    co2, temp, humidity = scd41_read_measurement(bus, SCD41_I2C_ADDR)
                    print(f"CO2: {co2} ppm, Temperature: {temp:.2f} °C, Humidity: {humidity:.2f} %")
                else:
                    print("Data not ready, waiting...")
                time.sleep(5)

        except KeyboardInterrupt:
            print("\nStopping measurements...")
        finally:
            print("Stopping sensor measurements...")
            bus.write_i2c_block_data(SCD41_I2C_ADDR, COMMAND_STOP_MEASUREMENT[0], COMMAND_STOP_MEASUREMENT[1:])
            print("SCD41 measurement stopped.")


if __name__ == "__main__":
    main()


