import pygame
import time
import json
import requests
import threading
import random
import os
from datetime import datetime

# --- Flask-Server ---
SERVER_URL = "http://127.0.0.1:5000/upload"
# SERVER_URL = "http://192.168.1.10:5000/upload"

# --- Upload-Zeiten (Stunden, Minuten) ---
UPLOAD_TIMES = [(9, 15), (12, 15), (15, 15), (18, 15)]

# --- Basisordner ---
BASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(BASE_DIR, exist_ok=True)

# =========================================================
# ================ PYGAME INITIALISIERUNG =================
# =========================================================

pygame.init()
screen = pygame.display.set_mode((1024, 600))
pygame.display.set_caption("Smiley + Sensoranzeige")
clock = pygame.time.Clock()

# Typeface-Font verwenden (Arial)
sensor_font = pygame.font.SysFont("Arial", 36)
mood_font = pygame.font.SysFont("Arial", 28)

# Smileys laden
good_smiley = pygame.image.load("Media/good.png").convert_alpha()
meh_smiley = pygame.image.load("Media/meh.png").convert_alpha()
bad_smiley = pygame.image.load("Media/bad.png").convert_alpha()

# =========================================================
# ================ DATENSTRUKTUREN =========================
# =========================================================

events = []
sensor_buffer = []
upload_history = []
running = True
current_smiley = meh_smiley
smiley_override_time = 0
SMILEY_OVERRIDE_DURATION = 3
upload_counter = 0

# =========================================================
# ================ HILFSFUNKTIONEN =========================
# =========================================================

def load_daily_totals():
    today = datetime.now()
    dir_path = os.path.join(BASE_DIR, today.strftime("%Y"), today.strftime("%m"), today.strftime("%d"))
    totals_file = os.path.join(dir_path, "totals.json")
    if os.path.exists(totals_file):
        with open(totals_file, "r") as f:
            try:
                return json.load(f)
            except:
                return {"good": 0, "meh": 0, "bad": 0,
                        "avg_sensor_day": {"temp": 0, "db": 0, "co2": 0, "voc": 0, "count": 0}}
    return {"good": 0, "meh": 0, "bad": 0,
            "avg_sensor_day": {"temp": 0, "db": 0, "co2": 0, "voc": 0, "count": 0}}

def draw_sensor_values(temp, db, co2, voc, smiley_rect):
    left_texts = [f"Temperatur:", f"{temp:.1f} °C", f"Dezibel:", f"{db:.1f} dB"]
    right_texts = [f"CO₂:", f"{co2} ppm", f"VOC:", f"{voc} ppb"]

    left_x = smiley_rect.left - 280
    right_x = smiley_rect.right + 60
    base_y = smiley_rect.top + 20

    for i, line in enumerate(left_texts):
        screen.blit(sensor_font.render(line, True, (255, 255, 255)), (left_x, base_y + i * 40))
    for i, line in enumerate(right_texts):
        screen.blit(sensor_font.render(line, True, (255, 255, 255)), (right_x, base_y + i * 40))

def draw_emotes(good, meh, bad, current_smiley):
    rect = current_smiley.get_rect(center=(screen.get_width() // 2, screen.get_height() // 2 - 50))
    screen.blit(current_smiley, rect)

    mood_y = rect.bottom + 20
    spacing = 160
    screen.blit(mood_font.render(f"Gut: {good}", True, (0, 255, 0)), (screen.get_width() // 2 - spacing, mood_y))
    screen.blit(mood_font.render(f"Neutral: {meh}", True, (255, 165, 0)), (screen.get_width() // 2 - 50, mood_y))
    screen.blit(mood_font.render(f"Schlecht: {bad}", True, (255, 0, 0)), (screen.get_width() // 2 + 80, mood_y))
    return rect

def draw_upload_count():
    text_surface = mood_font.render(f"Uploads heute: {len(upload_history)}", True, (255, 255, 255))
    screen.blit(text_surface, (screen.get_width() // 2 - 100, screen.get_height() - 50))

def avg_sensor_values():
    if not sensor_buffer:
        return {"temp": 0, "db": 0, "co2": 0, "voc": 0}
    t = sum(s[0] for s in sensor_buffer) / len(sensor_buffer)
    d = sum(s[1] for s in sensor_buffer) / len(sensor_buffer)
    c = sum(s[2] for s in sensor_buffer) / len(sensor_buffer)
    v = sum(s[3] for s in sensor_buffer) / len(sensor_buffer)
    return {"temp": round(t, 1), "db": round(d, 1), "co2": int(c), "voc": int(v)}

# =========================================================
# ================ UPLOAD FUNKTIONEN =======================
# =========================================================

def upload_to_server(avg_sensor, events):
    payload = {"events": events, "avg_sensor": avg_sensor}
    try:
        r = requests.post(SERVER_URL, json=payload, timeout=5)
        if r.status_code == 200:
            print("✅ Upload erfolgreich:", r.json())
        else:
            print("❌ Fehler beim Upload:", r.status_code, r.text)
    except Exception as e:
        print("⚠️ Upload fehlgeschlagen:", e)

def upload_cycle():
    global events, sensor_buffer, upload_counter
    now = datetime.now()
    upload_counter += 1
    avg_sensor = avg_sensor_values()

    if sensor_buffer:
        window_start = datetime.fromtimestamp(sensor_buffer[0][4]).strftime("%Y-%m-%d %H:%M:%S")
        window_end = datetime.fromtimestamp(sensor_buffer[-1][4]).strftime("%Y-%m-%d %H:%M:%S")
    else:
        window_start = window_end = now.strftime("%Y-%m-%d %H:%M:%S")

    year = now.strftime("%Y")
    month = now.strftime("%m")
    day = now.strftime("%d")
    dir_path = os.path.join(BASE_DIR, year, month, day)
    os.makedirs(dir_path, exist_ok=True)

    good = sum(1 for e in events if e["type"] == "good")
    meh = sum(1 for e in events if e["type"] == "meh")
    bad = sum(1 for e in events if e["type"] == "bad")

    upload_data = {
        "upload_number": upload_counter,
        "upload_Timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
        "good": good,
        "meh": meh,
        "bad": bad,
        "avg_sensor": avg_sensor,
        "sensor_window_start": window_start,
        "sensor_window_end": window_end,
        "events": events.copy()
    }

    file_path = os.path.join(dir_path, f"upload{upload_counter}.json")
    with open(file_path, "w") as f:
        json.dump(upload_data, f, indent=4)

    totals_file = os.path.join(dir_path, "totals.json")
    if os.path.exists(totals_file):
        with open(totals_file, "r") as f:
            try:
                totals = json.load(f)
            except:
                totals = {"good": 0, "meh": 0, "bad": 0,
                          "avg_sensor_day": {"temp": 0, "db": 0, "co2": 0, "voc": 0, "count": 0}}
    else:
        totals = {"good": 0, "meh": 0, "bad": 0,
                  "avg_sensor_day": {"temp": 0, "db": 0, "co2": 0, "voc": 0, "count": 0}}

    totals["good"] += good
    totals["meh"] += meh
    totals["bad"] += bad

    total_count = totals["avg_sensor_day"].get("count", 0)
    count_new = len(sensor_buffer)
    if count_new > 0:
        totals["avg_sensor_day"]["temp"] = round(
            (totals["avg_sensor_day"]["temp"] * total_count + avg_sensor["temp"] * count_new) / (total_count + count_new), 1)
        totals["avg_sensor_day"]["db"] = round(
            (totals["avg_sensor_day"]["db"] * total_count + avg_sensor["db"] * count_new) / (total_count + count_new), 1)
        totals["avg_sensor_day"]["co2"] = int(
            (totals["avg_sensor_day"]["co2"] * total_count + avg_sensor["co2"] * count_new) / (total_count + count_new))
        totals["avg_sensor_day"]["voc"] = int(
            (totals["avg_sensor_day"]["voc"] * total_count + avg_sensor["voc"] * count_new) / (total_count + count_new))
        totals["avg_sensor_day"]["count"] = total_count + count_new

    with open(totals_file, "w") as f:
        json.dump(totals, f, indent=4)

    threading.Thread(target=upload_to_server, args=(avg_sensor, events.copy()), daemon=True).start()
    events.clear()
    sensor_buffer.clear()
    upload_history.append((now.strftime("%Y-%m-%d"), upload_counter))

def check_scheduled_upload():
    now = datetime.now()
    for idx, (hour, minute) in enumerate(UPLOAD_TIMES):
        if now.hour == hour and now.minute == minute and now.second < 5:
            today_str = now.strftime("%Y-%m-%d")
            if (not upload_history) or upload_history[-1][0] != today_str or upload_history[-1][1] < idx + 1:
                upload_cycle()

# =========================================================
# ================ SENSOR SIMULATOR =======================
# =========================================================

def sensor_simulator():
    while running:
        temp = random.uniform(20.0, 25.0)
        db = random.uniform(35.0, 55.0)
        co2 = random.randint(390, 430)
        voc = random.randint(5, 20)
        sensor_buffer.append((temp, db, co2, voc, time.time()))
        if len(sensor_buffer) > 500:
            sensor_buffer.pop(0)
        time.sleep(2)

threading.Thread(target=sensor_simulator, daemon=True).start()

# =========================================================
# ================ PYGAME HAUPTSCHLEIFE ===================
# =========================================================

good = meh = bad = 0

while running:
    current_time = time.time()
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_g:
                good += 1
                current_smiley = good_smiley
                smiley_override_time = current_time
                events.append({"type": "good", "timestamp": current_time})
            elif event.key == pygame.K_m:
                meh += 1
                current_smiley = meh_smiley
                smiley_override_time = current_time
                events.append({"type": "meh", "timestamp": current_time})
            elif event.key == pygame.K_b:
                bad += 1
                current_smiley = bad_smiley
                smiley_override_time = current_time
                events.append({"type": "bad", "timestamp": current_time})
            elif event.key == pygame.K_RETURN:
                upload_cycle()

    # --- Smiley-Reset nach 3 Sekunden ---
    if current_time - smiley_override_time > SMILEY_OVERRIDE_DURATION:
        totals = load_daily_totals()
        g, m, b = totals["good"], totals["meh"], totals["bad"]

        if g == 0 and m == 0 and b == 0:
            # Wechsel alle 1 Sekunde zwischen good/meh/bad
            phase = int(current_time) % 3
            if phase == 0:
                current_smiley = good_smiley
            elif phase == 1:
                current_smiley = meh_smiley
            else:
                current_smiley = bad_smiley
        else:
            max_value = max(g, m, b)
            if max_value == g:
                current_smiley = good_smiley
            elif max_value == m:
                current_smiley = meh_smiley
            else:
                current_smiley = bad_smiley

    check_scheduled_upload()

    if sensor_buffer:
        temp, db, co2, voc, _ = sensor_buffer[-1]
    else:
        temp, db, co2, voc = (22.0, 45.0, 410, 10)

    screen.fill((0, 0, 0))
    rect = draw_emotes(good, meh, bad, current_smiley)
    draw_sensor_values(temp, db, co2, voc, rect)
    draw_upload_count()
    pygame.display.flip()
    clock.tick(30)

upload_cycle()
pygame.quit()
