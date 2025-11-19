#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ui.py

Pygame-basierte Anzeige und Eventloop.
UI lädt alle Images selbst (nach pygame.init()) und mappt
device-provided kinds ("good","meh","bad") auf diese Surfaces.
"""
import pygame
import time
import logging

_LOG = logging.getLogger("ui")

def load_font(path, size):
    try:
        return pygame.font.Font(path, size)
    except Exception:
        _LOG.warning("Font %s nicht gefunden, benutze Default-Font.", path)
        return pygame.font.SysFont(None, size)

def load_image(path, fallback_color, size=None):
    try:
        img = pygame.image.load(path).convert_alpha()
        if size is not None:
            img = pygame.transform.smoothscale(img, size)
        return img
    except Exception:
        _LOG.warning("Bild %s nicht gefunden, benutze Platzhalter.", path)
        w, h = size if size is not None else (200,200)
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        surf.fill(fallback_color)
        return surf

def run(get_counts,
        get_override_info,
        get_upload_info,
        get_latest_sensor,
        calculate_avg_smiley,
        pct_round,
        on_vote,
        on_upload):
    """
    Startet die Pygame-Loop. Blockierend. Gibt zurück, wenn der Nutzer
    das Fenster schließt (oder QUIT auslöst).
    """
    pygame.init()
    screen = pygame.display.set_mode((1024, 600))
    pygame.display.set_caption("Smiley + Sensoranzeige")
    clock = pygame.time.Clock()

    sensor_font = load_font("Media/Silkscreen/Silkscreen-Regular.ttf", 36)
    mood_font = load_font("Media/Silkscreen/Silkscreen-Regular.ttf", 28)

    # Lade grosse Smileys (200x200) und kleine Varianten (48x48)
    big_good = load_image("Media/good.png", (0,255,0), size=(200,200))
    big_meh  = load_image("Media/meh.png", (255,200,0), size=(200,200))
    big_bad  = load_image("Media/bad.png", (255,0,0), size=(200,200))
    small_good = pygame.transform.smoothscale(big_good, (48,48))
    small_meh  = pygame.transform.smoothscale(big_meh,  (48,48))
    small_bad  = pygame.transform.smoothscale(big_bad,  (48,48))

    kind_to_big = {"good": big_good, "meh": big_meh, "bad": big_bad}
    kind_to_small = {"good": small_good, "meh": small_meh, "bad": small_bad}

    running = True
    while running:
        now = time.time()
        for evt in pygame.event.get():
            if evt.type == pygame.QUIT:
                running = False
            elif evt.type == pygame.KEYDOWN:
                if evt.key == pygame.K_g:
                    on_vote("good")
                elif evt.key == pygame.K_m:
                    on_vote("meh")
                elif evt.key == pygame.K_b:
                    on_vote("bad")
                elif evt.key == pygame.K_RETURN:
                    on_upload()

        # Get current state from device via callbacks
        good, meh, bad = get_counts()
        current_kind, smiley_override_time, SMILEY_OVERRIDE_DURATION = get_override_info()
        upload_failed_time, UPLOAD_FAILED_DURATION = get_upload_info()
        temp, db, co2, voc = get_latest_sensor()

        # Draw background
        screen.fill((0,0,0))

        # Draw mood scale (white line) above the big smiley
        left_margin = 110
        right_margin = screen.get_width() - 110
        y = screen.get_height()//2 - 270
        pygame.draw.line(screen, (255,255,255), (left_margin, y), (right_margin, y), 4)

        try:
            lbl_bad = sensor_font.render("Schlecht", True, (255,255,255))
            lbl_meh = sensor_font.render("Neutral", True, (255,255,255))
            lbl_good= sensor_font.render("Gut", True, (255,255,255))
            screen.blit(lbl_bad,  ((left_margin - lbl_bad.get_width()//2) + 40, y + 12))
            screen.blit(lbl_meh,  ((left_margin+right_margin)//2 - lbl_meh.get_width()//2, y + 12))
            screen.blit(lbl_good, (right_margin - lbl_good.get_width()//2, y + 12))
        except Exception:
            pass

        # Calculate score for small smiley position
        total = good + meh + bad
        if total > 0:
            score = (good - bad) / total
        else:
            # fallback: try to use EMA via calculate_avg_smiley which returns a kind
            kind_fallback, _ = calculate_avg_smiley(good, meh, bad)
            if kind_fallback == "good":
                score = 1.0
            elif kind_fallback == "bad":
                score = -1.0
            else:
                score = 0.0

        frac = (score + 1.0) / 2.0
        frac = max(0.0, min(1.0, frac))
        sx = left_margin + frac * (right_margin - left_margin)

        # choose small image by score segment
        if score >= 0.33:
            small_img = kind_to_small["good"]
        elif score <= -0.33:
            small_img = kind_to_small["bad"]
        else:
            small_img = kind_to_small["meh"]

        sw, sh = small_img.get_size()
        screen.blit(small_img, (sx - sw//2, y - sh//2))

        # Now decide which big smiley to show:
        now = time.time()
        if (now - smiley_override_time) < SMILEY_OVERRIDE_DURATION and current_kind is not None:
            big_smiley = kind_to_big.get(current_kind, kind_to_big["meh"])
            pct_good, pct_meh, pct_bad = pct_round(good, meh, bad)
        else:
            kind, (pct_good, pct_meh, pct_bad) = calculate_avg_smiley(good, meh, bad)
            big_smiley = kind_to_big.get(kind, kind_to_big["meh"])

        # Draw big smiley centered
        rect = big_smiley.get_rect(center=(screen.get_width()//2, screen.get_height()//2 - 50))
        screen.blit(big_smiley, rect)

        # Draw percentages
        try:
            text = f"Positiv: {pct_good}% | Neutral: {pct_meh}% | Negativ: {pct_bad}%"
            text_surface = mood_font.render(text, True, (255,255,255))
            screen.blit(text_surface, (screen.get_width()//2 - text_surface.get_width()//2, rect.bottom + 10))
        except Exception:
            pass

        # Draw counters left bottom
        base_x = 40
        base_y = screen.get_height() - 150
        line_height = 40
        try:
            screen.blit(mood_font.render(f"Gut: {good}", True, (0,255,0)), (base_x, base_y))
            screen.blit(mood_font.render(f"Neutral: {meh}", True, (255,200,0)), (base_x, base_y+line_height))
            screen.blit(mood_font.render(f"Schlecht: {bad}", True, (255,0,0)), (base_x, base_y+2*line_height))
        except Exception:
            pass

        # Upload failed indicator
        if time.time() - upload_failed_time < UPLOAD_FAILED_DURATION:
            try:
                text = sensor_font.render("Upload fehlgeschlagen!", True, (255,50,50))
                screen.blit(text, (screen.get_width()//2 - text.get_width()//2, 50))
            except Exception:
                pass

        # Sensor values at sides
        try:
            left_textTemp = [f"Temperatur:", f"{temp:.1f} °C"]
            left_textdB = [f"Dezibel:", f"{db:.1f} dB"]
            right_textCO2 = [f"CO2:", f"{co2} ppm"]
            right_textVOC = [f"VOC:", f"{voc} ppb"]
            left_x = rect.left - 280
            right_x = rect.right + 60
            base_yUP = rect.top + 80
            base_yDown = rect.top + 240
            for i, line in enumerate(left_textTemp):
                screen.blit(sensor_font.render(line, True, (255,255,255)), (left_x, base_yUP + i*40))
            for i, line in enumerate(left_textdB):
                screen.blit(sensor_font.render(line, True, (255,255,255)), (left_x, base_yDown + i*40))
            for i, line in enumerate(right_textCO2):
                screen.blit(sensor_font.render(line, True, (255,255,255)), (right_x, base_yUP + i*40))
            for i, line in enumerate(right_textVOC):
                screen.blit(sensor_font.render(line, True, (255,255,255)), (right_x, base_yDown + i*40))
        except Exception:
            pass

        pygame.display.flip()
        clock.tick(30)

    pygame.quit()
    return