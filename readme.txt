Dateisystem struktur:

data/
├── 2025/
│   └── 10/
│       └── 29/
│           ├── upload1.json      # Erster Upload des Tages (inkl. Sensorwerte + Events)
│           ├── upload2.json      # Zweiter Upload
│           ├── upload3.json      # Dritter Upload
│           └── totals.json       # Tages-Summe: good, meh, bad + avg_sensor_day
└── archive/
    ├── archive_2025-10-29_09-15-03.json  # Archivierter Upload
    ├── archive_2025-10-29_12-15-07.json
    └── archive_2025-10-29_15-15-01.json

uploadX.json enthalten:

{
  "upload_Timestamp": "2025-10-29 09:15:03",
  "good": 2,
  "meh": 1,
  "bad": 0,
  "avg_sensor": {
    "temp": 22.4,
    "db": 45.2,
    "co2": 410,
    "voc": 12
  },
  "events": [
    {"type": "good", "timestamp": 1698566103},
    {"type": "meh", "timestamp": 1698566120}
  ],
  "upload_number": 1
}


total.json enthalten:
{
  "good": 5,
  "meh": 3,
  "bad": 1,
  "avg_sensor_day": {
    "temp": 22.3,
    "db": 44.9,
    "co2": 412,
    "voc": 11,
    "count": 9
  }
}


archive/archive_YYYY-MM-DD_HH-MM-SS.json – jede Upload-Anfrage wird zusätzlich
hier gesichert, damit du ein Backup hast, unabhängig von den Tagesordnern.

Fazit:
Live-Daten existieren zunächst nur im Client (z. B. Pygame-Sensorpuffer).
Sobald ein Upload gemacht wird, landen sie in data/YYYY/MM/DD/uploadN.json, totals.json und im Archiv.
Dadurch hast du tagesweise getrennte Daten und eine gesicherte Historie.
