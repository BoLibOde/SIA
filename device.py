import pygame
import json
import os
from datetime import datetime
import time

pygame.init()
screen = pygame.display.set_mode((800, 600))
pygame.display.set_caption("Stimmungs-Single-Smiley")
clock = pygame.time.Clock()
FPS = 30

# --- PNG Smileys laden ---
good_smiley = pygame.image.load("Media/good.png").convert_alpha()
meh_smiley  = pygame.image.load("Media/meh.png").convert_alpha()
bad_smiley  = pygame.image.load("Media/bad.png").convert_alpha()

# --- Tagesdurchschnitt laden ---
def load_daily_totals():
    today = datetime.now()
    dir_path = os.path.join("data", today.strftime("%Y"), today.strftime("%m"), today.strftime("%d"))
    totals_file = os.path.join(dir_path, "totals.json")
    if os.path.exists(totals_file):
        with open(totals_file, "r") as f:
            try:
                return json.load(f)
            except:
                return {"good":0,"meh":0,"bad":0}
    return {"good":0,"meh":0,"bad":0}

# --- Variablen ---
current_smiley = None
smiley_override_time = 0
SMILEY_OVERRIDE_DURATION = 3  # Sekunden
good = meh = bad = 0
font = pygame.font.SysFont("Consolas", 24)

running = True
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
            elif event.key == pygame.K_m:
                meh += 1
                current_smiley = meh_smiley
                smiley_override_time = current_time
            elif event.key == pygame.K_b:
                bad += 1
                current_smiley = bad_smiley
                smiley_override_time = current_time
            elif event.key == pygame.K_RETURN:
                totals = load_daily_totals()
                totals["good"] = totals.get("good",0) + good
                totals["meh"] = totals.get("meh",0) + meh
                totals["bad"] = totals.get("bad",0) + bad
                dir_path = os.path.join("data", datetime.now().strftime("%Y/%m/%d"))
                os.makedirs(dir_path, exist_ok=True)
                with open(os.path.join(dir_path, "totals.json"), "w") as f:
                    json.dump(totals, f, indent=4)
                good = meh = bad = 0

    # --- Smiley-Logik: Tagesdurchschnitt ---
    if current_smiley is None or (current_time - smiley_override_time > SMILEY_OVERRIDE_DURATION):
        totals = load_daily_totals()
        max_value = max(totals.get("good",0), totals.get("meh",0), totals.get("bad",0))
        if max_value == totals.get("good",0):
            current_smiley = good_smiley
        elif max_value == totals.get("meh",0):
            current_smiley = meh_smiley
        else:
            current_smiley = bad_smiley

    # --- Zeichnen ---
    screen.fill((30,30,30))  # dunkler Hintergrund
    rect = current_smiley.get_rect(center=(screen.get_width()//2, screen.get_height()//2))
    screen.blit(current_smiley, rect)

    # --- Zähler anzeigen ---
    totals = load_daily_totals()
    screen.blit(font.render(f"G: {totals.get('good',0)+good}", True, (0,255,0)), (10,10))
    screen.blit(font.render(f"M: {totals.get('meh',0)+meh}", True, (255,165,0)), (10,40))
    screen.blit(font.render(f"B: {totals.get('bad',0)+bad}", True, (255,0,0)), (10,70))

    pygame.display.flip()
    clock.tick(FPS)

pygame.quit()
