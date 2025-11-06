import os
import json
import random
from datetime import datetime, timedelta

BASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(BASE_DIR, exist_ok=True)


# --- Funktionen zum Speichern ---
def save_upload(year, month, day, upload_number, good, meh, bad, upload_ts, avg_sensor):
    dir_path = os.path.join(BASE_DIR, year, month, day)
    os.makedirs(dir_path, exist_ok=True)

    dt_obj = datetime.strptime(upload_ts, "%Y-%m-%d %H:%M:%S")
    sensor_window_start = (dt_obj - timedelta(seconds=random.randint(2, 10))).strftime("%Y-%m-%d %H:%M:%S")
    sensor_window_end = (dt_obj + timedelta(seconds=random.randint(1, 5))).strftime("%Y-%m-%d %H:%M:%S")

    event_types = ["good"] * good + ["meh"] * meh + ["bad"] * bad
    random.shuffle(event_types)
    events = [{"type": t, "timestamp": (dt_obj - timedelta(seconds=random.randint(0, 600))).timestamp()} for t in event_types]

    data = {
        "upload_number": upload_number,
        "upload_Timestamp": upload_ts,
        "good": good,
        "meh": meh,
        "bad": bad,
        "avg_sensor": avg_sensor,
        "sensor_window_start": sensor_window_start,
        "sensor_window_end": sensor_window_end,
        "events": events
    }

    file_path = os.path.join(dir_path, f"upload{upload_number}.json")
    with open(file_path, "w") as f:
        json.dump(data, f, indent=4)

    return dir_path


def update_totals(dir_path, good, meh, bad, avg_sensor):
    totals_file = os.path.join(dir_path, "totals.json")
    if os.path.exists(totals_file):
        with open(totals_file, "r") as f:
            try:
                totals = json.load(f)
            except:
                totals = {"good": 0, "meh": 0, "bad": 0,
                          "avg_sensor_day": {"temp": 0, "db": 0, "co2": 0, "voc": 0, "count": 0},
                          "weekday": ""}
    else:
        totals = {"good": 0, "meh": 0, "bad": 0,
                  "avg_sensor_day": {"temp": 0, "db": 0, "co2": 0, "voc": 0, "count": 0},
                  "weekday": ""}

    totals["good"] += good
    totals["meh"] += meh
    totals["bad"] += bad

    # Durchschnittswerte des Tages gleitend aktualisieren
    c = totals["avg_sensor_day"].get("count", 0)
    totals["avg_sensor_day"]["temp"] = (totals["avg_sensor_day"]["temp"] * c + avg_sensor["temp"]) / (c + 1)
    totals["avg_sensor_day"]["db"] = (totals["avg_sensor_day"]["db"] * c + avg_sensor["db"]) / (c + 1)
    totals["avg_sensor_day"]["co2"] = (totals["avg_sensor_day"]["co2"] * c + avg_sensor["co2"]) / (c + 1)
    totals["avg_sensor_day"]["voc"] = (totals["avg_sensor_day"]["voc"] * c + avg_sensor["voc"]) / (c + 1)
    totals["avg_sensor_day"]["count"] = c + 1

    # Wochentag aus dem Ordnernamen berechnen
    try:
        year = int(os.path.basename(os.path.dirname(os.path.dirname(dir_path))))
        month = int(os.path.basename(os.path.dirname(dir_path)))
        day = int(os.path.basename(dir_path))
        date_obj = datetime(year, month, day)
        totals["weekday"] = date_obj.strftime("%A")  # z.B. "Monday", oder auf Deutsch bei Locale
    except:
        totals["weekday"] = "?"

    with open(totals_file, "w") as f:
        json.dump(totals, f, indent=4)


# --- Monatsbasierte Maximalwerte ---
MONTH_MAX_VOTES = {
    1: (30, 80), 2: (40, 90), 3: (50, 110),
    4: (60, 120), 5: (80, 140), 6: (100, 160),
    7: (90, 150), 8: (80, 140), 9: (60, 120),
    10: (50, 110), 11: (40, 90), 12: (30, 80)
}


# --- Dummy-Daten Generator ---
def generate_dummy_data():
    start_date = datetime(2025, 1, 1)
    end_date = datetime.today()
    current_date = start_date

    while current_date <= end_date:
        year = current_date.strftime("%Y")
        month = current_date.month
        day = current_date.strftime("%d")

        min_votes, max_votes = MONTH_MAX_VOTES.get(month, (50, 140))
        total_votes = random.randint(min_votes, max_votes)
        remaining = total_votes

        for upload_number in range(1, 5):
            good = random.randint(0, remaining)
            meh = random.randint(0, remaining - good)
            bad = remaining - good - meh
            if bad < 0: bad = 0

            avg_sensor = {
                "temp": round(random.uniform(20.0, 25.0), 1),
                "db": round(random.uniform(35.0, 55.0), 1),
                "co2": random.randint(390, 430),
                "voc": random.randint(5, 20)
            }

            upload_ts = current_date.replace(
                hour=[9, 12, 15, 18][upload_number - 1],
                minute=15,
                second=random.randint(0, 59)
            ).strftime('%Y-%m-%d %H:%M:%S')

            dir_path = save_upload(year, f"{month:02}", day, upload_number, good, meh, bad, upload_ts, avg_sensor)
            update_totals(dir_path, good, meh, bad, avg_sensor)

        current_date += timedelta(days=1)


if __name__ == "__main__":
    generate_dummy_data()
    print("✅ Dummy-Daten mit Sensorwerten und Wochentagen erstellt (2025 bis heute).")
