# SPDX-FileCopyrightText: 2021 ladyada for Adafruit Industries
# SPDX-License-Identifier: MIT

import time
import board
from board import *
import adafruit_ccs811
import busio

ccs811_i2c = board.I2C()  # uses board.SCL and board.SDA
# i2c = board.STEMMA_I2C()  # For using the built-in STEMMA QT connector on a microcontroller
ccs811 = adafruit_ccs811.CCS811(ccs811_i2c)

i2c = busio.I2C(SCL, SDA)
i2c.try_lock()
print(i2c.scan())
i2c.unlock()
i2c.deinit()

# Wait for the sensor to be ready
while not ccs811.data_ready:
    pass

while True:
    print(f"CO2: {ccs811.eco2} PPM, TVOC: {ccs811.tvoc} PPB")
    time.sleep(0.5)