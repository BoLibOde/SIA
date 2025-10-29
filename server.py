import os
from flask import Flask, request, jsonify
import json
from datetime import datetime
import threading

app = Flask(__name__)

# --- Basisordner für alle Daten ---
BASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(BASE_DIR, exist_ok=True)

ARCHIVE_DIR = os.path.join(BASE_DIR, "archive")
os.makedirs(ARCHIVE_DIR, exist_ok=True)

# --- Speichern der Uploads ---
def save_dated_json(data):
    ts_str = data.get("upload_Timestamp") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
    except:
        ts = datetime.now()

    year, month, day = ts.strftime("%Y"), ts.strftime("%m"), ts.strftime("%d")
    dir_path = os.path.join(BASE_DIR, year, month, day)
    os.makedirs(dir_path, exist_ok=True)

    existing_files = [f for f in os.listdir(dir_path) if f.startswith("upload") and f.endswith(".json")]
    upload_number = len(existing_files) + 1
    data["upload_number"] = upload_number
    file_path = os.path.join(dir_path, f"upload{upload_number}.json")

    with open(file_path, "w") as f:
        json.dump(data, f, indent=4)

    return dir_path

# --- Tages-Totals inkl. Sensorwerte ---
def update_daily_totals_async(dir_path, good, meh, bad, avg_sensor, count_new):
    def worker():
        totals_file = os.path.join(dir_path, "totals.json")
        if os.path.exists(totals_file):
            with open(totals_file, "r") as f:
                try:
                    totals = json.load(f)
                except json.JSONDecodeError:
                    totals = {"good":0,"meh":0,"bad":0,"avg_sensor_day":{"temp":0,"db":0,"co2":0,"voc":0,"count":0}}
        else:
            totals = {"good":0,"meh":0,"bad":0,"avg_sensor_day":{"temp":0,"db":0,"co2":0,"voc":0,"count":0}}

        # Events summieren
        totals["good"] += good
        totals["meh"]  += meh
        totals["bad"]  += bad

        # Tagesdurchschnitt Sensorwerte
        total_count = totals["avg_sensor_day"].get("count",0)
        if count_new > 0:
            totals["avg_sensor_day"]["temp"] = round(
                (totals["avg_sensor_day"]["temp"]*total_count + avg_sensor["temp"]*count_new)/(total_count+count_new),1)
            totals["avg_sensor_day"]["db"] = round(
                (totals["avg_sensor_day"]["db"]*total_count + avg_sensor["db"]*count_new)/(total_count+count_new),1)
            totals["avg_sensor_day"]["co2"] = int(
                (totals["avg_sensor_day"]["co2"]*total_count + avg_sensor["co2"]*count_new)/(total_count+count_new))
            totals["avg_sensor_day"]["voc"] = int(
                (totals["avg_sensor_day"]["voc"]*total_count + avg_sensor["voc"]*count_new)/(total_count+count_new))
            totals["avg_sensor_day"]["count"] = total_count + count_new

        with open(totals_file, "w") as f:
            json.dump(totals, f, indent=4)

    threading.Thread(target=worker, daemon=True).start()

# --- Archivierung im Hintergrund ---
def archive_data_async(data_to_save):
    def worker():
        archive_file = os.path.join(ARCHIVE_DIR, f"archive_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.json")
        with open(archive_file, "w") as f:
            json.dump(data_to_save, f, indent=4)
    threading.Thread(target=worker, daemon=True).start()

# --- Upload-Route ---
@app.route("/upload", methods=["POST"])
def upload():
    data = request.get_json()
    if not data:
        return jsonify({"status":"error","message":"Keine Daten gesendet"}),400

    events = data.get("events", [])
    avg_sensor = data.get("avg_sensor", {"temp":0,"db":0,"co2":0,"voc":0})
    count_new = len(events) if events else 1  # Für Sensor-Durchschnitt, mindestens 1

    good = sum(1 for e in events if e["type"]=="good")
    meh  = sum(1 for e in events if e["type"]=="meh")
    bad  = sum(1 for e in events if e["type"]=="bad")

    upload_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    data_to_save = {
        "upload_Timestamp": upload_timestamp,
        "good": good,
        "meh": meh,
        "bad": bad,
        "avg_sensor": avg_sensor,
        "events": events
    }

    dir_path = save_dated_json(data_to_save)
    update_daily_totals_async(dir_path, good, meh, bad, avg_sensor, count_new)
    archive_data_async(data_to_save)

    return jsonify({"status":"ok","upload_number":data_to_save["upload_number"]}),200

# --- Tagesdaten abrufen ---
@app.route("/data/<year>/<month>/<day>", methods=["GET"])
def get_day_data(year, month, day):
    day_dir = os.path.join(BASE_DIR, year, month, day)
    if not os.path.exists(day_dir):
        return jsonify([])

    uploads = []
    for file_name in sorted(os.listdir(day_dir)):
        if file_name.startswith("upload") and file_name.endswith(".json"):
            with open(os.path.join(day_dir, file_name),"r") as f:
                try:
                    uploads.append(json.load(f))
                except:
                    continue
    return jsonify(uploads)

# --- Server starten ---
if __name__=="__main__":
    app.run(host="0.0.0.0", port=5000, threaded=True)
