import os
from flask import Flask, request, jsonify
import json
from datetime import datetime

app = Flask(__name__)

# --- Basisordner für alle Daten ---
BASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(BASE_DIR, exist_ok=True)

# --- Funktionen zum Speichern und Aggregieren ---
def save_dated_json(data):
    """Speichert die Upload-Daten in data/Jahr/Monat/Tag/uploadX.json"""
    ts_str = data.get("upload_Timestamp") or data.get("timestamp")
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

def update_daily_totals(dir_path, good, meh, bad):
    """Aktualisiert die Tageszusammenfassung totals.json"""
    totals_file = os.path.join(dir_path, "totals.json")
    if os.path.exists(totals_file):
        with open(totals_file, "r") as f:
            try:
                totals = json.load(f)
            except json.JSONDecodeError:
                totals = {"good": 0, "meh": 0, "bad": 0}
    else:
        totals = {"good": 0, "meh": 0, "bad": 0}

    totals["good"] += good
    totals["meh"] += meh
    totals["bad"] += bad

    with open(totals_file, "w") as f:
        json.dump(totals, f, indent=4)

# --- Upload-Route ---
@app.route("/upload", methods=["POST"])
def upload():
    data = request.get_json()
    if not data:
        return jsonify({"status": "error", "message": "Keine Daten gesendet"}), 400

    # Regulärer Upload
    if data.get("type") == "regular":
        required_fields = ["upload_Timestamp", "good", "meh", "bad"]
        for field in required_fields:
            if field not in data:
                return jsonify({"status": "error", "message": f"Fehlendes Feld: {field}"}), 400
        dir_path = save_dated_json(data)
        update_daily_totals(dir_path, data["good"], data["meh"], data["bad"])
    # Live-Sensor Upload
    elif data.get("type") == "live":
        dir_path = save_dated_json(data)
        # keine Tages-Totals aktualisieren
    else:
        return jsonify({"status": "error", "message": "Unbekannter Upload-Typ"}), 400

    return jsonify({"status": "ok", "upload_number": data.get("upload_number", 0)}), 200

# --- Tagesdaten ---
@app.route("/data/<year>/<month>/<day>", methods=["GET"])
def get_day_data(year, month, day):
    day_dir = os.path.join(BASE_DIR, year, month, day)
    if not os.path.exists(day_dir):
        return jsonify([])

    uploads = []
    for file_name in sorted(os.listdir(day_dir)):
        if file_name.startswith("upload") and file_name.endswith(".json"):
            with open(os.path.join(day_dir, file_name), "r") as f:
                try:
                    uploads.append(json.load(f))
                except:
                    continue
    return jsonify(uploads)

# --- Tages-Totals ---
@app.route("/totals/<year>/<month>/<day>", methods=["GET"])
def get_day_totals(year, month, day):
    totals_file = os.path.join(BASE_DIR, year, month, day, "totals.json")
    if not os.path.exists(totals_file):
        return jsonify({"good": 0, "meh": 0, "bad": 0})
    with open(totals_file, "r") as f:
        return jsonify(json.load(f))

# --- Monatsdaten ---
@app.route("/data/<year>/<month>", methods=["GET"])
def get_month_data(year, month):
    month_dir = os.path.join(BASE_DIR, year, month)
    if not os.path.exists(month_dir):
        return jsonify({})

    month_data = {}
    for day in sorted(os.listdir(month_dir)):
        day_dir = os.path.join(month_dir, day)
        if not os.path.isdir(day_dir):
            continue

        uploads = []
        for file_name in sorted(os.listdir(day_dir)):
            if file_name.startswith("upload") and file_name.endswith(".json"):
                with open(os.path.join(day_dir, file_name), "r") as f:
                    try:
                        uploads.append(json.load(f))
                    except:
                        continue

        totals_file = os.path.join(day_dir, "totals.json")
        if os.path.exists(totals_file):
            with open(totals_file, "r") as f:
                try:
                    totals = json.load(f)
                except:
                    totals = {"good": 0, "meh": 0, "bad": 0}
        else:
            totals = {"good": 0, "meh": 0, "bad": 0}

        month_data[day] = {
            "uploads": uploads,
            "totals": totals
        }

    return jsonify(month_data)

# --- Jahresdaten ---
@app.route("/data/<year>", methods=["GET"])
def get_year_data(year):
    year_dir = os.path.join(BASE_DIR, year)
    if not os.path.exists(year_dir):
        return jsonify({})

    year_data = {}
    for month in sorted(os.listdir(year_dir)):
        month_dir = os.path.join(year_dir, month)
        if not os.path.isdir(month_dir):
            continue

        month_data = {}
        for day in sorted(os.listdir(month_dir)):
            day_dir = os.path.join(month_dir, day)
            if not os.path.isdir(day_dir):
                continue

            uploads = []
            for file_name in sorted(os.listdir(day_dir)):
                if file_name.startswith("upload") and file_name.endswith(".json"):
                    with open(os.path.join(day_dir, file_name), "r") as f:
                        try:
                            uploads.append(json.load(f))
                        except:
                            continue

            totals_file = os.path.join(day_dir, "totals.json")
            if os.path.exists(totals_file):
                with open(totals_file, "r") as f:
                    try:
                        totals = json.load(f)
                    except:
                        totals = {"good": 0, "meh": 0, "bad": 0}
            else:
                totals = {"good": 0, "meh": 0, "bad": 0}

            month_data[day] = {
                "uploads": uploads,
                "totals": totals
            }

        year_data[month] = month_data

    return jsonify(year_data)

# --- Monatsreport ---
@app.route("/report/<year>/<month>", methods=["GET"])
def report_month(year, month):
    month_dir = os.path.join(BASE_DIR, year, month)
    if not os.path.exists(month_dir):
        return jsonify({"good": 0, "meh": 0, "bad": 0})

    total_good = total_meh = total_bad = 0
    for day in os.listdir(month_dir):
        day_dir = os.path.join(month_dir, day)
        if not os.path.isdir(day_dir):
            continue
        totals_file = os.path.join(day_dir, "totals.json")
        if os.path.exists(totals_file):
            with open(totals_file, "r") as f:
                try:
                    totals = json.load(f)
                    total_good += totals.get("good", 0)
                    total_meh += totals.get("meh", 0)
                    total_bad += totals.get("bad", 0)
                except:
                    continue

    return jsonify({"year": year, "month": month, "good": total_good, "meh": total_meh, "bad": total_bad})

# --- Jahresreport ---
@app.route("/report/<year>", methods=["GET"])
def report_year(year):
    year_dir = os.path.join(BASE_DIR, year)
    if not os.path.exists(year_dir):
        return jsonify({"good": 0, "meh": 0, "bad": 0})

    total_good = total_meh = total_bad = 0
    for month in os.listdir(year_dir):
        month_dir = os.path.join(year_dir, month)
        if not os.path.isdir(month_dir):
            continue
        for day in os.listdir(month_dir):
            day_dir = os.path.join(month_dir, day)
            if not os.path.isdir(day_dir):
                continue
            totals_file = os.path.join(day_dir, "totals.json")
            if os.path.exists(totals_file):
                with open(totals_file, "r") as f:
                    try:
                        totals = json.load(f)
                        total_good += totals.get("good", 0)
                        total_meh += totals.get("meh", 0)
                        total_bad += totals.get("bad", 0)
                    except:
                        continue

    return jsonify({"year": year, "good": total_good, "meh": total_meh, "bad": total_bad})

# --- Jahresübersicht mit allen Uploads ---
@app.route("/overview/<year>", methods=["GET"])
def overview_year(year):
    year_dir = os.path.join(BASE_DIR, year)
    if not os.path.exists(year_dir):
        return jsonify({"year": year, "months": {}, "totals": {"good": 0, "meh": 0, "bad": 0}})

    overview = {"year": year, "months": {}, "totals": {"good": 0, "meh": 0, "bad": 0}}

    for month in sorted(os.listdir(year_dir)):
        month_dir = os.path.join(year_dir, month)
        if not os.path.isdir(month_dir):
            continue

        month_data = {}
        for day in sorted(os.listdir(month_dir)):
            day_dir = os.path.join(month_dir, day)
            if not os.path.isdir(day_dir):
                continue

            uploads = []
            for file_name in sorted(os.listdir(day_dir)):
                if file_name.startswith("upload") and file_name.endswith(".json"):
                    with open(os.path.join(day_dir, file_name), "r") as f:
                        try:
                            uploads.append(json.load(f))
                        except:
                            continue

            totals_file = os.path.join(day_dir, "totals.json")
            if os.path.exists(totals_file):
                with open(totals_file, "r") as f:
                    try:
                        totals = json.load(f)
                    except:
                        totals = {"good": 0, "meh": 0, "bad": 0}
            else:
                totals = {"good": 0, "meh": 0, "bad": 0}

            month_data[day] = {"uploads": uploads, "totals": totals}

            overview["totals"]["good"] += totals.get("good", 0)
            overview["totals"]["meh"] += totals.get("meh", 0)
            overview["totals"]["bad"] += totals.get("bad", 0)

        overview["months"][month] = month_data

    return jsonify(overview)

# --- Server starten ---
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
