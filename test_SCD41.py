from sensor import SCD41

try:
    scd = SCD41()
    scd.start_periodic()
    co2, temp, hum = scd.read_measurement()
    print(f"SCD41 initialized successfully! CO2: {co2} ppm, Temp: {temp:.2f} °C, Humidity: {hum:.2f} %")
except Exception as e:
    print(f"Failed to initialize SCD41: {e}")