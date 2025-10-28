from flask import Flask, request, jsonify, send_from_directory
import os, json

app = Flask(__name__)

# Neuer Speicherort für JSON-Daten
JSON_FOLDER = os.path.join("common", "json")
os.makedirs(JSON_FOLDER, exist_ok=True)  # Ordner erstellen, falls nicht vorhanden
FILE_PATH = os.path.join(JSON_FOLDER, "data.json")


@app.route("/")
def index():
    return send_from_directory(".", "index.html")


@app.route("/common/<path:path>")
def serve_common(path):
    return send_from_directory("common", path)


@app.route("/upload", methods=["POST"])
def upload():
    data = request.get_json()
    if os.path.exists(FILE_PATH):
        try:
            with open(FILE_PATH, "r") as f:
                existing = json.load(f)
            if isinstance(existing, dict):
                existing = [existing]
        except json.JSONDecodeError:
            existing = []
    else:
        existing = []

    existing.append(data)

    # Speichern im neuen Pfad
    with open(FILE_PATH, "w") as f:
        json.dump(existing, f, indent=4)

    return jsonify({"status": "ok", "saved_entries": len(existing)}), 200


@app.route("/data")
def data():
    if not os.path.exists(FILE_PATH):
        return jsonify([])
    with open(FILE_PATH, "r") as f:
        return jsonify(json.load(f))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
