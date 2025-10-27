from flask import Flask, request, jsonify
import os
import json

app = Flask(__name__)

# Ordner für gespeicherte Dateien
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
FILE_PATH = os.path.join(UPLOAD_FOLDER, "data.json")


@app.route("/upload", methods=["POST"])
def upload():
    data = request.get_json()  # JSON-Daten vom Client
    print("Empfangene Daten:", data)

    # Prüfe, ob die Datei schon existiert
    if os.path.exists(FILE_PATH):
        try:
            with open(FILE_PATH, "r") as f:
                existing = json.load(f)
            # Falls die Datei ein Dict war, in eine Liste umwandeln
            if isinstance(existing, dict):
                existing = [existing]
        except json.JSONDecodeError:
            existing = []
    else:
        existing = []

    # Neuen Datensatz hinzufügen
    existing.append(data)

    # Speichern
    with open(FILE_PATH, "w") as f:
        json.dump(existing, f, indent=4)

    return jsonify({"status": "ok", "saved_entries": len(existing)}), 200


@app.route("/view", methods=["GET"])
def view():
    """Zeigt die gespeicherten Daten an"""
    if not os.path.exists(FILE_PATH):
        return jsonify({"error": "Keine Daten gefunden"}), 404

    with open(FILE_PATH, "r") as f:
        content = json.load(f)
    return jsonify(content), 200


@app.route("/")
def index():
    return "<h3>Server läuft ✅ — sende POST /upload mit JSON-Daten.</h3>"


if __name__ == "__main__":
    # 0.0.0.0 erlaubt Zugriffe von anderen Geräten im selben Netzwerk
    app.run(host="0.0.0.0", port=5000)
#    app.run(host="127.0.0.1", port=5000)