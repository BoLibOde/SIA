import pygame
import time
import json
import requests
import threading
import random
import os
import uuid
from datetime import datetime

# --- Flask-Server ---
SERVER_URL = "http://127.0.0.1:5000/upload"

# --- Upload-Zeiten (Stunden, Minuten) ---
UPLOAD_TIMES = [(9, 15), (12, 15), (15, 15), (18, 15)]

# --- Basisordner lokal ---
BASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(BASE_DIR, exist_ok=True)

# =========================================================
# ================ CLIENT-ID =============================
# =========================================================
# Jede Client-ID wird einmal erzeugt und lokal gespeichert
CLIENT_ID_FILE = os.path.join(BASE_DIR, "client_id.txt")
if os.path.exists(CLIENT_ID_FILE):
    with open(CLIENT_ID_FILE, "r") as f:
        DEVICE_ID = f.read().strip()
else:
    DEVICE_ID = str(uuid.uuid4())[:8]  # z.B. "a1b2c3d4"
    with open(CLIENT_ID_FILE, "w") as f:
        f.write(DEVICE_ID)
print(f"[INFO] Client-ID: {DEVICE_ID}")

# =========================================================
# ================ PYGAME INITIALISIERUNG =================
# =========================================================
pygame.init()
screen = pygame.display.set_mode((1024, 600))
pygame.display.set_caption(f"Smiley + Sensoranzeige ({DEVICE_ID})")
clock = pygame.time.Clock()

sensor_font = pygame.font.Font("Media/Silkscreen/Silkscreen-Regular.ttf", 36)
mood_font = pygame.font.Font("Media/Silkscreen/Silkscreen-Regular.ttf", 28)

# Smileys laden
good_smiley = pygame.image.load("Media/good.png").convert_alpha()
meh_smiley = pygame.image.load("Media/meh.png").convert_alpha()
bad_smiley = pygame.image.load("Media/bad.png").convert_alpha()

# =========================================================
# ================ DATENSTRUKTUREN ========================
# =========================================================
events = []
sensor_buffer = []
upload_history = []
running = True
current_smiley = meh_smiley
smiley_override_time = 0.0
SMILEY_OVERRIDE_DURATION = 3
upload_counter = 0
upload_failed_time = 0
UPLOAD_FAILED_DURATION = 2.0

# =========================================================
# ================ HILFSFUNKTIONEN =======================
# =========================================================
def load_daily_totals():
    today = datetime.now()
    dir_path = os.path.join(BASE_DIR, today.strftime("%Y"), today.strftime("%m"), today.strftime("%d"))
    totals_file = os.path.join(dir_path, "totals.json")
    if os.path.exists(totals_file):
        try:
            with open(totals_file, "r") as f:
                return json.load(f)
        except:
            return {"good":0,"meh":0,"bad":0,"avg_sensor_day":{"temp":0,"db":0,"co2":0,"voc":0,"count":0}}
    return {"good":0,"meh":0,"bad":0,"avg_sensor_day":{"temp":0,"db":0,"co2":0,"voc":0,"count":0}}

def avg_sensor_values():
    if not sensor_buffer:
        return {"temp":0,"db":0,"co2":0,"voc":0}
    t = sum(s[0] for s in sensor_buffer)/len(sensor_buffer)
    d = sum(s[1] for s in sensor_buffer)/len(sensor_buffer)
    c = sum(s[2] for s in sensor_buffer)/len(sensor_buffer)
    v = sum(s[3] for s in sensor_buffer)/len(sensor_buffer)
    return {"temp":round(t,1),"db":round(d,1),"co2":int(c),"voc":int(v)}

def draw_sensor_values(temp, db, co2, voc, smiley_rect):
    left_textTemp = [f"Temperatur:", f"{temp:.1f} °C"]
    left_textdB = [f"Dezibel:", f"{db:.1f} dB"]
    right_textCO2 = [f"CO2:", f"{co2} ppm"]
    right_textVOC = [f"VOC:", f"{voc} ppb"]
    left_x = smiley_rect.left - 280
    right_x = smiley_rect.right + 60
    base_yUP = smiley_rect.top + 80
    base_yDown = smiley_rect.top + 240
    for i, line in enumerate(left_textTemp):
        screen.blit(sensor_font.render(line, True, (255,255,255)), (left_x, base_yUP + i*40))
    for i, line in enumerate(left_textdB):
        screen.blit(sensor_font.render(line, True, (255,255,255)), (left_x, base_yDown + i*40))
    for i, line in enumerate(right_textCO2):
        screen.blit(sensor_font.render(line, True, (255,255,255)), (right_x, base_yUP + i*40))
    for i, line in enumerate(right_textVOC):
        screen.blit(sensor_font.render(line, True, (255,255,255)), (right_x, base_yDown + i*40))

# =========================================================
# ================ SMILEY-LOGIK ==========================
# =========================================================
def calculate_avg_smiley(good, meh, bad):
    total = good + meh + bad
    if total == 0:
        return meh_smiley, None
    if good == bad:
        smiley = meh_smiley
    elif good > bad:
        smiley = good_smiley
    else:
        smiley = bad_smiley
    pct_good = int((good / total) * 100)
    pct_meh  = int((meh / total) * 100)
    pct_bad  = int((bad / total) * 100)
    return smiley, (pct_good, pct_meh, pct_bad)

def draw_emotes(good, meh, bad):
    smiley, percentages = calculate_avg_smiley(good, meh, bad)
    rect = smiley.get_rect(center=(screen.get_width()//2, screen.get_height()//2 - 50))
    screen.blit(smiley, rect)

    if percentages:
        pct_good, pct_meh, pct_bad = percentages
        text = f"Positiv: {pct_good}% | Neutral: {pct_meh}% | Negativ: {pct_bad}%"
        text_surface = mood_font.render(text, True, (255,255,255))
        screen.blit(text_surface, (screen.get_width()//2 - text_surface.get_width()//2, rect.bottom + 10))

    base_x = 40
    base_y = screen.get_height() - 150
    line_height = 40
    screen.blit(mood_font.render(f"Gut: {good}", True, (0,255,0)), (base_x, base_y))
    screen.blit(mood_font.render(f"Neutral: {meh}", True, (255,200,0)), (base_x, base_y+line_height))
    screen.blit(mood_font.render(f"Schlecht: {bad}", True, (255,0,0)), (base_x, base_y+2*line_height))

    current_time = time.time()
    if current_time - upload_failed_time < UPLOAD_FAILED_DURATION:
        text = sensor_font.render("Upload fehlgeschlagen!", True, (255,50,50))
        screen.blit(text, (screen.get_width()//2 - text.get_width()//2, 50))

    return rect

# =========================================================
# ================ UPLOAD ================================
# =========================================================
def upload_to_server(avg_sensor, events):
    global upload_failed_time
    payload = {"device_id": DEVICE_ID, "events": events, "avg_sensor": avg_sensor}
    try:
        r = requests.post(SERVER_URL, json=payload, timeout=5)
        if r.status_code == 200:
            print("✅ Upload erfolgreich:", r.json())
        else:
            print(f"❌ Fehler beim Upload: Status {r.status_code} | {r.text}")
            upload_failed_time = time.time()
    except Exception as e:
        print(f"⚠️ Upload fehlgeschlagen: {e}")
        upload_failed_time = time.time()

def upload_cycle():
    global events, sensor_buffer, upload_counter, upload_history
    now = datetime.now()
    upload_counter += 1
    avg_sensor = avg_sensor_values()
    threading.Thread(target=upload_to_server, args=(avg_sensor, events.copy()), daemon=True).start()
    events.clear()
    sensor_buffer.clear()
    upload_history.append((now.strftime("%Y-%m-%d"), upload_counter))
    print(f"[DEBUG] upload_cycle: uploaded #{upload_counter}")

def check_scheduled_upload():
    now = datetime.now()
    for idx, (hour, minute) in enumerate(UPLOAD_TIMES):
        if now.hour == hour and now.minute == minute and now.second < 5:
            today_str = now.strftime("%Y-%m-%d")
            if (not upload_history) or upload_history[-1][0] != today_str or upload_history[-1][1] < idx+1:
                upload_cycle()

# =========================================================
# ================ SENSOR SIMULATOR ======================
# =========================================================
def sensor_simulator():
    while running:
        temp = random.uniform(20.0, 25.0)
        db   = random.uniform(35.0, 55.0)
        co2  = random.randint(390, 430)
        voc  = random.randint(5, 20)
        sensor_buffer.append((temp, db, co2, voc, time.time()))
        if len(sensor_buffer) > 500:
            sensor_buffer.pop(0)
        time.sleep(2)

threading.Thread(target=sensor_simulator, daemon=True).start()

# =========================================================
# ================ PYGAME HAUPTSCHLEIFE ==================
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
                events.append({"type":"good","timestamp":current_time})
            elif event.key == pygame.K_m:
                meh += 1
                current_smiley = meh_smiley
                smiley_override_time = current_time
                events.append({"type":"meh","timestamp":current_time})
            elif event.key == pygame.K_b:
                bad += 1
                current_smiley = bad_smiley
                smiley_override_time = current_time
                events.append({"type":"bad","timestamp":current_time})
            elif event.key == pygame.K_RETURN:
                upload_cycle()

    # Smiley Override 3 Sekunden
    if current_time - smiley_override_time > SMILEY_OVERRIDE_DURATION:
        totals = load_daily_totals()
        total_good = totals.get("good",0)+good
        total_meh  = totals.get("meh",0)+meh
        total_bad  = totals.get("bad",0)+bad
        current_smiley, _ = calculate_avg_smiley(total_good, total_meh, total_bad)
        smiley_override_time = current_time

    check_scheduled_upload()

    if sensor_buffer:
        temp, db, co2, voc, _ = sensor_buffer[-1]
    else:
        temp, db, co2, voc = (22.0, 45.0, 410, 10)

    screen.fill((0,0,0))
    rect = draw_emotes(good, meh, bad)
    draw_sensor_values(temp, db, co2, voc, rect)
    pygame.display.flip()
    clock.tick(30)

upload_cycle()
pygame.quit()
