import os
from flask import Flask, request, jsonify
import json
from datetime import datetime, timedelta
import threading
import shutil
import zipfile
import time
import sys
import locale

# --- Deutsche Wochentage einstellen (optional) ---
try:
    locale.setlocale(locale.LC_TIME, 'de_DE.UTF-8')  # für Deutsch
except:
    pass  # falls Locale nicht unterstützt wird, bleibt Englisch

app = Flask(__name__)

# --- Basisordner für alle Server-Daten ---
BASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "server_data")
os.makedirs(BASE_DIR, exist_ok=True)

ARCHIVE_DIR = os.path.join(BASE_DIR, "archive")
os.makedirs(ARCHIVE_DIR, exist_ok=True)

# =========================================================
# ================ SPEICHERN & HILFSFUNKTIONEN ============
# =========================================================

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

def update_daily_totals_async(dir_path, good, meh, bad, avg_sensor, count_new):
    def worker():
        # Wochentag aus dem Ordnernamen ermitteln
        year, month, day = os.path.basename(os.path.dirname(os.path.dirname(dir_path))), \
                           os.path.basename(os.path.dirname(dir_path)), \
                           os.path.basename(dir_path)
        date_obj = datetime(int(year), int(month), int(day))
        weekday_name = date_obj.strftime("%A")  # Englisch, bei Locale auf Deutsch: "Montag" etc.

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

        # Wochentag hinzufügen/aktualisieren
        totals["weekday"] = weekday_name

        with open(totals_file, "w") as f:
            json.dump(totals, f, indent=4)

    threading.Thread(target=worker, daemon=True).start()

def archive_data_async(data_to_save):
    def worker():
        archive_file = os.path.join(ARCHIVE_DIR, f"archive_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.json")
        with open(archive_file, "w") as f:
            json.dump(data_to_save, f, indent=4)
    threading.Thread(target=worker, daemon=True).start()

# =========================================================
# ================ JAHRES-ARCHIVIERUNG ====================
# =========================================================

def archive_old_years_zip():
    current_year = datetime.now().year
    for year_folder in os.listdir(BASE_DIR):
        year_path = os.path.join(BASE_DIR, year_folder)
        if not year_folder.isdigit() or not os.path.isdir(year_path):
            continue
        year_int = int(year_folder)
        if year_int < current_year:
            zip_name = os.path.join(ARCHIVE_DIR, f"{year_folder}.zip")
            if os.path.exists(zip_name):
                continue
            with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, dirs, files in os.walk(year_path):
                    for file in files:
                        full_path = os.path.join(root, file)
                        arcname = os.path.relpath(full_path, BASE_DIR)
                        zipf.write(full_path, arcname)
            shutil.rmtree(year_path)

def daily_archive_scheduler():
    def worker():
        while True:
            try:
                archive_old_years_zip()
            except Exception as e:
                print(f"Fehler beim Archivieren: {e}")
            time.sleep(24*60*60)
    threading.Thread(target=worker, daemon=True).start()

# =========================================================
# ================ LIVE-DASHBOARD ========================
# =========================================================

def live_daily_dashboard():
    def worker():
        while True:
            now = datetime.now()
            day_dir = os.path.join(BASE_DIR, now.strftime("%Y"), now.strftime("%m"), now.strftime("%d"))
            totals_file = os.path.join(day_dir, "totals.json")

            sys.stdout.write("\033[2J\033[H")  # Clear screen & move cursor home
            print(f"========== Live Dashboard {now.strftime('%Y-%m-%d')} ==========")

            if os.path.exists(totals_file):
                try:
                    with open(totals_file, "r") as f:
                        totals = json.load(f)
                    good = totals['good']
                    meh = totals['meh']
                    bad = totals['bad']
                    avg = totals.get("avg_sensor_day", {"temp": 0, "db": 0, "co2": 0, "voc": 0})
                    weekday = totals.get("weekday", "?")

                    total_events = good + meh + bad
                    print(f"Wochentag: {weekday}")
                    print(f"Uploads heute: {total_events}")

                    def bar(value, max_len=30):
                        if total_events == 0:
                            return ''
                        length = int((value / total_events) * max_len)
                        return "█" * length + " " * (max_len - length)

                    print(f"Gut   : {good:3} |{bar(good)}|")
                    print(f"Meh   : {meh:3} |{bar(meh)}|")
                    print(f"Schlecht: {bad:3} |{bar(bad)}|")
                    print(f"\nTemperatur: {avg['temp']}°C  dB: {avg['db']}  CO2: {avg['co2']}ppm  VOC: {avg['voc']}ppb")

                except Exception as e:
                    print(f"Fehler beim Laden der Tageswerte: {e}")
            else:
                print("Keine Daten für heute vorhanden.")

            print("==========================================")
            time.sleep(60)
    threading.Thread(target=worker, daemon=True).start()

# =========================================================
# ================ API-ENDPUNKTE ==========================
# =========================================================

@app.route("/upload", methods=["POST"])
def upload():
    data = request.get_json()
    if not data:
        return jsonify({"status":"error","message":"Keine Daten gesendet"}),400

    events = data.get("events", [])
    avg_sensor = data.get("avg_sensor", {"temp":0,"db":0,"co2":0,"voc":0})
    count_new = len(events) if events else 1

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

# =========================================================
# ================ SERVER START ===========================
# =========================================================

if __name__=="__main__":
    archive_old_years_zip()
    daily_archive_scheduler()
    live_daily_dashboard()
    print(f"🚀 Server gestartet auf http://0.0.0.0:5000")
    app.run(host="0.0.0.0", port=5000, threaded=True)
