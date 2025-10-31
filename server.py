import os
from flask import Flask, request, jsonify
import json
from datetime import datetime
import threading
import shutil
import zipfile
import time
import sys
import locale
import tempfile

# --- Deutsche Wochentage einstellen (optional) ---
try:
    locale.setlocale(locale.LC_TIME, 'de_DE.UTF-8')
except:
    pass

app = Flask(__name__)

# --- Basisordner für Server-Daten ---
BASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "server_data")
os.makedirs(BASE_DIR, exist_ok=True)

ARCHIVE_DIR = os.path.join(BASE_DIR, "archive")
os.makedirs(ARCHIVE_DIR, exist_ok=True)

# Globaler Lock für Dateizugriffe
file_lock = threading.Lock()

# =========================================================
# ================ SPEICHERN & HILFSFUNKTIONEN ===========
# =========================================================

def atomic_write_json(path, data):
    dir_name = os.path.dirname(path)
    os.makedirs(dir_name, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix="tmp_", dir=dir_name, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.remove(tmp_path)
        except Exception:
            pass
        raise

def update_daily_totals_async(dir_path, good, meh, bad, avg_sensor, count_new):
    def worker():
        year = os.path.basename(os.path.dirname(os.path.dirname(dir_path)))
        month = os.path.basename(os.path.dirname(dir_path))
        day = os.path.basename(dir_path)
        try:
            date_obj = datetime(int(year), int(month), int(day))
            weekday_name = date_obj.strftime("%A")
        except Exception:
            weekday_name = "?"

        totals_file = os.path.join(dir_path, "totals.json")

        with file_lock:
            if os.path.exists(totals_file):
                try:
                    with open(totals_file, "r", encoding="utf-8") as f:
                        totals = json.load(f)
                except Exception:
                    totals = {"good":0,"meh":0,"bad":0,"avg_sensor_day":{"temp":0,"db":0,"co2":0,"voc":0,"count":0}}
            else:
                totals = {"good":0,"meh":0,"bad":0,"avg_sensor_day":{"temp":0,"db":0,"co2":0,"voc":0,"count":0}}

            totals["good"] = int(totals.get("good",0)) + int(good)
            totals["meh"]  = int(totals.get("meh",0))  + int(meh)
            totals["bad"]  = int(totals.get("bad",0))  + int(bad)

            total_count = int(totals["avg_sensor_day"].get("count",0))
            if count_new > 0:
                try:
                    totals["avg_sensor_day"]["temp"] = round(
                        (totals["avg_sensor_day"]["temp"] * total_count + avg_sensor["temp"] * count_new) / (total_count + count_new), 1)
                    totals["avg_sensor_day"]["db"] = round(
                        (totals["avg_sensor_day"]["db"] * total_count + avg_sensor["db"] * count_new) / (total_count + count_new), 1)
                    totals["avg_sensor_day"]["co2"] = int(
                        (totals["avg_sensor_day"]["co2"] * total_count + avg_sensor["co2"] * count_new) / (total_count + count_new))
                    totals["avg_sensor_day"]["voc"] = int(
                        (totals["avg_sensor_day"]["voc"] * total_count + avg_sensor["voc"] * count_new) / (total_count + count_new))
                    totals["avg_sensor_day"]["count"] = total_count + count_new
                except Exception:
                    pass

            totals["weekday"] = weekday_name
            try:
                atomic_write_json(totals_file, totals)
            except Exception as e:
                print("[ERROR] Schreiben totals.json fehlgeschlagen:", e)

    threading.Thread(target=worker, daemon=True).start()

def archive_data_async(data_to_save):
    def worker():
        try:
            archive_file = os.path.join(ARCHIVE_DIR, f"archive_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.json")
            atomic_write_json(archive_file, data_to_save)
        except Exception as e:
            print("[ERROR] archive_data_async:", e)
    threading.Thread(target=worker, daemon=True).start()

# =========================================================
# ================ JAHRES-ARCHIVIERUNG ==================
# =========================================================

def archive_old_years_zip():
    current_year = datetime.now().year
    for device_id in os.listdir(BASE_DIR):
        device_path = os.path.join(BASE_DIR, device_id)
        if not os.path.isdir(device_path) or device_id=="archive":
            continue
        for year_folder in os.listdir(device_path):
            year_path = os.path.join(device_path, year_folder)
            if not year_folder.isdigit() or not os.path.isdir(year_path):
                continue
            year_int = int(year_folder)
            if year_int < current_year:
                zip_name = os.path.join(ARCHIVE_DIR, f"{device_id}_{year_folder}.zip")
                if os.path.exists(zip_name):
                    continue
                try:
                    with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as zipf:
                        for root, dirs, files in os.walk(year_path):
                            for file in files:
                                full_path = os.path.join(root, file)
                                arcname = os.path.relpath(full_path, BASE_DIR)
                                zipf.write(full_path, arcname)
                    shutil.rmtree(year_path)
                except Exception as e:
                    print(f"[ERROR] Fehler beim Archivieren Jahr {year_folder} von {device_id}: {e}")

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
# ================ LIVE-DASHBOARD =======================
# =========================================================

def live_daily_dashboard():
    def worker():
        while True:
            now = datetime.now()
            print("\033[2J\033[H")
            print(f"========== Live Dashboard {now.strftime('%Y-%m-%d')} ==========")
            for device_id in os.listdir(BASE_DIR):
                device_path = os.path.join(BASE_DIR, device_id)
                if not os.path.isdir(device_path) or device_id=="archive":
                    continue
                day_dir = os.path.join(device_path, now.strftime("%Y"), now.strftime("%m"), now.strftime("%d"))
                totals_file = os.path.join(day_dir, "totals.json")
                print(f"\n--- Device: {device_id} ---")
                if os.path.exists(totals_file):
                    try:
                        with open(totals_file, "r", encoding="utf-8") as f:
                            totals = json.load(f)
                        good = totals.get('good',0)
                        meh = totals.get('meh',0)
                        bad = totals.get('bad',0)
                        avg = totals.get("avg_sensor_day", {"temp":0,"db":0,"co2":0,"voc":0})
                        weekday = totals.get("weekday","?")
                        total_events = good+meh+bad

                        def bar(value, max_len=30):
                            if total_events==0:
                                return ' '*max_len
                            length = int((value/total_events)*max_len)
                            return "█"*length + " "*(max_len-length)

                        print(f"Wochentag: {weekday}")
                        print(f"Gut      : {good:3} |{bar(good)}|")
                        print(f"Meh      : {meh:3} |{bar(meh)}|")
                        print(f"Schlecht : {bad:3} |{bar(bad)}|")
                        print(f"Temperatur: {avg.get('temp',0)}°C  dB: {avg.get('db',0)}  CO2: {avg.get('co2',0)}ppm  VOC: {avg.get('voc',0)}ppb")
                    except Exception as e:
                        print(f"Fehler beim Laden Tageswerte von {device_id}: {e}")
                else:
                    print("Keine Daten für heute vorhanden.")
            print("==========================================")
            time.sleep(60)
    threading.Thread(target=worker, daemon=True).start()

# =========================================================
# ================ API-ENDPOINTS ========================
# =========================================================

@app.route("/upload", methods=["POST"])
def upload():
    data = request.get_json()
    if not data:
        return jsonify({"status":"error","message":"Keine Daten gesendet"}), 400

    device_id = data.get("device_id", "default")
    device_dir = os.path.join(BASE_DIR, device_id)
    os.makedirs(device_dir, exist_ok=True)

    events = data.get("events", [])
    avg_sensor = data.get("avg_sensor", {"temp":0,"db":0,"co2":0,"voc":0})
    count_new = len(events) if events else 1

    good = sum(1 for e in events if e.get("type")=="good")
    meh  = sum(1 for e in events if e.get("type")=="meh")
    bad  = sum(1 for e in events if e.get("type")=="bad")

    upload_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    data_to_save = {
        "upload_Timestamp": upload_timestamp,
        "device_id": device_id,
        "good": good,
        "meh": meh,
        "bad": bad,
        "avg_sensor": avg_sensor,
        "events": events
    }

    try:
        ts = datetime.strptime(upload_timestamp, "%Y-%m-%d %H:%M:%S")
        year, month, day = ts.strftime("%Y"), ts.strftime("%m"), ts.strftime("%d")
        dir_path = os.path.join(device_dir, year, month, day)
        os.makedirs(dir_path, exist_ok=True)

        with file_lock:
            existing_files = [f for f in os.listdir(dir_path) if f.startswith("upload") and f.endswith(".json")]
            upload_number = len(existing_files) + 1
            data_to_save["upload_number"] = upload_number
            file_path = os.path.join(dir_path, f"upload{upload_number}.json")
            atomic_write_json(file_path, data_to_save)

    except Exception as e:
        print("[ERROR] save_dated_json failed:", e)
        return jsonify({"status":"error","message":"Speichern fehlgeschlagen"}), 500

    update_daily_totals_async(dir_path, good, meh, bad, avg_sensor, count_new)
    archive_data_async(data_to_save)

    return jsonify({"status":"ok","upload_number":data_to_save.get("upload_number")}), 200

@app.route("/data/<device_id>/<year>/<month>/<day>", methods=["GET"])
def get_day_data(device_id, year, month, day):
    day_dir = os.path.join(BASE_DIR, device_id, year, month, day)
    if not os.path.exists(day_dir):
        return jsonify([])

    uploads = []
    for file_name in sorted(os.listdir(day_dir)):
        if file_name.startswith("upload") and file_name.endswith(".json"):
            file_path = os.path.join(day_dir, file_name)
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    uploads.append(json.load(f))
            except Exception:
                continue
    return jsonify(uploads)

# =========================================================
# ================ SERVER START ==========================
# =========================================================

if __name__=="__main__":
    archive_old_years_zip()
    daily_archive_scheduler()
    live_daily_dashboard()
    print(f"🚀 Server gestartet auf http://0.0.0.0:5000")
    app.run(host="0.0.0.0", port=5000, threaded=True)
