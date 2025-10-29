import pygame
import os
import json
from datetime import datetime
import random
import time

pygame.init()
screen = pygame.display.set_mode((400, 400))
pygame.display.set_caption("Stimmungs-Single-Smiley")
clock = pygame.time.Clock()
font = pygame.font.SysFont("Consolas", 20)

# --- Pixel-Emotes (höhere Auflösung) ---
good_emote = [
    [0, 0, 1, 1, 1, 1, 1, 0, 0, 0],
    [0, 1, 0, 0, 0, 0, 0, 1, 0, 0],
    [1, 0, 1, 0, 0, 0, 1, 0, 1, 0],
    [1, 0, 0, 0, 0, 0, 0, 0, 0, 1],
    [1, 0, 0, 0, 0, 0, 0, 0, 0, 1],
    [1, 0, 1, 0, 0, 0, 1, 0, 1, 0],
    [0, 1, 0, 0, 0, 0, 0, 1, 0, 0],
    [0, 0, 1, 1, 1, 1, 1, 0, 0, 0]
]

meh_emote = [
    [0, 0, 1, 1, 1, 1, 1, 0, 0, 0],
    [0, 1, 0, 0, 0, 0, 0, 1, 0, 0],
    [1, 0, 1, 0, 0, 0, 1, 0, 1, 0],
    [1, 0, 0, 0, 0, 0, 0, 0, 0, 1],
    [1, 0, 0, 1, 1, 1, 0, 0, 0, 1],
    [1, 0, 0, 0, 0, 0, 0, 0, 0, 1],
    [0, 1, 0, 0, 0, 0, 0, 1, 0, 0],
    [0, 0, 1, 1, 1, 1, 1, 0, 0, 0]
]

bad_emote = [
    [0, 0, 1, 1, 1, 1, 1, 0, 0, 0],
    [0, 1, 0, 0, 0, 0, 0, 1, 0, 0],
    [1, 0, 1, 0, 0, 0, 1, 0, 1, 0],
    [1, 0, 0, 0, 0, 0, 0, 0, 0, 1],
    [1, 0, 0, 0, 0, 0, 0, 0, 0, 1],
    [0, 1, 0, 1, 1, 1, 1, 0, 1, 0],
    [0, 0, 1, 0, 0, 0, 0, 1, 0, 0],
    [0, 0, 0, 1, 1, 1, 1, 0, 0, 0]
]


def draw_emote(x, y, emote, pixel_size=20):
    for row_idx, row in enumerate(emote):
        for col_idx, val in enumerate(row):
            color = (255, 255, 0) if val else (0, 0, 0)
            pygame.draw.rect(screen, color,
                             (x + col_idx * pixel_size, y + row_idx * pixel_size, pixel_size, pixel_size))


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
                return {"good": 0, "meh": 0, "bad": 0}
    return {"good": 0, "meh": 0, "bad": 0}


# --- Variablen ---
current_smiley = None
smiley_override_time = 0
SMILEY_OVERRIDE_DURATION = 3  # Sekunden
good = meh = bad = 0

FPS = 30

running = True
while running:
    current_time = time.time()

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_g:
                good += 1
                current_smiley = good_emote
                smiley_override_time = current_time
            elif event.key == pygame.K_m:
                meh += 1
                current_smiley = meh_emote
                smiley_override_time = current_time
            elif event.key == pygame.K_b:
                bad += 1
                current_smiley = bad_emote
                smiley_override_time = current_time
            elif event.key == pygame.K_BACKSPACE:
                good = meh = bad = 0
            elif event.key == pygame.K_RETURN:
                totals = load_daily_totals()
                totals["good"] = totals.get("good", 0) + good
                totals["meh"] = totals.get("meh", 0) + meh
                totals["bad"] = totals.get("bad", 0) + bad
                os.makedirs(os.path.dirname(os.path.join("data", datetime.now().strftime("%Y/%m/%d"))), exist_ok=True)
                with open(os.path.join("data", datetime.now().strftime("%Y/%m/%d/totals.json")), "w") as f:
                    json.dump(totals, f, indent=4)
                good = meh = bad = 0

    # --- Smiley-Logik ---
    if current_smiley is None or (current_time - smiley_override_time > SMILEY_OVERRIDE_DURATION):
        totals = load_daily_totals()
        max_value = max(totals.get("good", 0), totals.get("meh", 0), totals.get("bad", 0))
        if max_value == totals.get("good", 0):
            current_smiley = good_emote
        elif max_value == totals.get("meh", 0):
            current_smiley = meh_emote
        else:
            current_smiley = bad_emote

    # --- Zeichnen ---
    screen.fill((0, 0, 0))
    draw_emote(100, 100, current_smiley)

    # --- Zähleranzeige ---
    totals = load_daily_totals()
    screen.blit(font.render(f"Good: {totals.get('good', 0) + good}", True, (255, 255, 0)), (10, 10))
    screen.blit(font.render(f"Meh: {totals.get('meh', 0) + meh}", True, (255, 255, 0)), (10, 35))
    screen.blit(font.render(f"Bad: {totals.get('bad', 0) + bad}", True, (255, 255, 0)), (10, 60))

    pygame.display.flip()
    clock.tick(FPS)

pygame.quit()
