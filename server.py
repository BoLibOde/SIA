import os
from flask import Flask, send_from_directory, request, jsonify
import json

app = Flask(__name__)

# Absoluter Pfad zum Kirill_Website-Ordner
BASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Kirill_Website")

# JSON-Datei
JSON_FILE = os.path.join(BASE_DIR, "common", "json", "data.json")
os.makedirs(os.path.dirname(JSON_FILE), exist_ok=True)

# --- Routes ---
@app.route("/")
def index():
    # index.html ausliefern
    return send_from_directory(BASE_DIR, "index.html")

@app.route("/common/<path:path>")
def serve_common(path):
    # CSS/JS ausliefern
    return send_from_directory(os.path.join(BASE_DIR, "common"), path)

@app.route("/upload", methods=["POST"])
def upload():
    data = request.get_json()
    if not data:
        return jsonify({"status": "error", "message": "Keine Daten gesendet"}), 400

    if os.path.exists(JSON_FILE):
        try:
            with open(JSON_FILE, "r") as f:
                existing = json.load(f)
            if isinstance(existing, dict):
                existing = [existing]
        except json.JSONDecodeError:
            existing = []
    else:
        existing = []

    existing.append(data)

    with open(JSON_FILE, "w") as f:
        json.dump(existing, f, indent=4)

    return jsonify({"status": "ok", "saved_entries": len(existing)}), 200

@app.route("/data")
def data():
    if not os.path.exists(JSON_FILE):
        return jsonify([])
    with open(JSON_FILE, "r") as f:
        return jsonify(json.load(f))

if __name__ == "__main__":
    # Server für LAN-Zugriff
    app.run(host="0.0.0.0", port=5000)
