from flask import Flask, request, jsonify, send_from_directory
import os
import json

app = Flask(__name__)

# Basisordner für die Website
BASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Kirill_Website")

# Pfad für die JSON-Datei
JSON_FILE = os.path.join(BASE_DIR, "common", "json", "data.json")
os.makedirs(os.path.dirname(JSON_FILE), exist_ok=True)  # Ordner automatisch erstellen

# --- Routes ---

@app.route("/")
def index():
    """Index-Seite ausliefern"""
    return send_from_directory(BASE_DIR, "index.html")


@app.route("/common/<path:path>")
def serve_common(path):
    """CSS/JS-Dateien ausliefern"""
    return send_from_directory(os.path.join(BASE_DIR, "common"), path)


@app.route("/upload", methods=["POST"])
def upload():
    """Daten vom Client empfangen und speichern"""
    data = request.get_json()
    if not data:
        return jsonify({"status": "error", "message": "Keine Daten gesendet"}), 400

    # Bestehende Daten laden
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

    # Neue Daten hinzufügen
    existing.append(data)

    # Speichern
    with open(JSON_FILE, "w") as f:
        json.dump(existing, f, indent=4)

    return jsonify({"status": "ok", "saved_entries": len(existing)}), 200


@app.route("/data")
def data():
    """Gespeicherte JSON-Daten zurückgeben"""
    if not os.path.exists(JSON_FILE):
        return jsonify([])
    with open(JSON_FILE, "r") as f:
        return jsonify(json.load(f))


# --- Server starten ---
if __name__ == "__main__":
    # 0.0.0.0 erlaubt Zugriff aus dem LAN
    app.run(host="0.0.0.0", port=5000)
