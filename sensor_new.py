import time
import board
import busio
import adafruit_ccs811

# Initialize I2C bus
i2c = busio.I2C(board.SCL, board.SDA)

# Initialize CCS811 sensor
ccs811 = adafruit_ccs811.CCS811(i2c)

# Wait for the sensor to be ready
while not ccs811.data_ready:
    pass

# Optional: Calibrate temperature with an external sensor if available for better accuracy
# temp = ccs811.temperature
# ccs811.temp_offset = temp - 25.0

while True:
    if ccs811.data_ready:
        print("eCO2: {} ppm, TVOC: {} ppb".format(ccs811.eco2, ccs811.tvoc))
    time.sleep(1) # Read every second (Mode 1)
