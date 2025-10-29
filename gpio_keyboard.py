import RPi.GPIO as GPIO
import uinput
import time

# Set up GPIO
GPIO.setmode(GPIO.BCM)
button_pin = 17  # Change to your GPIO pin number
GPIO.setup(button_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

# Set up uinput
try:
    # Create a virtual keyboard device
    device = uinput.Device([uinput.KEY_A, uinput.KEY_B, uinput.KEY_C]) # Example keys, add more as needed
except FileNotFoundError:
    print("uinput device not found. Make sure it's enabled in /boot/config.txt")
    exit()

# Event loop
while True:
    if GPIO.input(button_pin) == GPIO.LOW:
        print("Button pressed")
        device.emit(uinput.KEY_A, 1)  # Send a keystroke (e.g., 'A')
        time.sleep(0.5)  # Debounce to prevent multiple presses
    time.sleep(0.01)
