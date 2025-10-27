from flask import Flask, request, jsonify
import json

app = Flask(__name__)

@app.route('/upload', methods=['POST'])
def upload_data():
    try:
        data = request.get_json()  # JSON vom Client empfangen
        print("Empfangene Daten:", data)

        # In Datei speichern
        with open("uploaded_data.json", "w") as f:
            json.dump(data, f, indent=4)

        return jsonify({"status": "success", "message": "Daten empfangen"}), 200
    except Exception as e:
        print("Fehler:", e)
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    # Starte den Server lokal auf Port 5000
    app.run(host='127.0.0.1', port=5000, debug=True)
