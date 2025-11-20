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

    sensor_font = load_font("Media/Silkscreen/Silkscreen-Regular.ttf", 28)
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

        # Write mood and sensor data side by side (minimal changes, mood colors kept).
        base_x = 40
        base_y = screen.get_height() - 150
        try:
            # Prepare mood lines (keep original colored values and percentages)
            mood_lines = [
                ("Gut:", str(good), (0,255,0), f"{pct_good}%"),
                ("Neutral:", str(meh), (255,200,0), f"{pct_meh}%"),
                ("Schlecht:", str(bad), (255,0,0), f"{pct_bad}%"),
            ]

            # Render mood surfaces and compute sizes
            mood_label_surfs = []
            mood_value_surfs = []
            mood_pct_surfs = []
            max_label_w = 0
            max_value_w = 0
            max_pct_w = 0
            max_line_h = 0
            for lbl, val, color, pct in mood_lines:
                s_lbl = mood_font.render(f"{lbl}", True, (255,255,255))          # label white
                s_val = mood_font.render(f"{val}", True, color)                # value colored
                s_pct = mood_font.render(f" | {pct}", True, color)             # pct colored
                mood_label_surfs.append(s_lbl)
                mood_value_surfs.append(s_val)
                mood_pct_surfs.append(s_pct)
                max_label_w = max(max_label_w, s_lbl.get_width())
                max_value_w = max(max_value_w, s_val.get_width())
                max_pct_w = max(max_pct_w, s_pct.get_width())
                max_line_h = max(max_line_h, s_lbl.get_height(), s_val.get_height(), s_pct.get_height())

            mood_gap = 12
            mood_block_width = max_label_w + mood_gap + max_value_w + mood_gap + max_pct_w

            # Position mood block (same baseline as original)
            mood_x = base_x
            mood_y = base_y

            # Draw mood block
            for i in range(len(mood_lines)):
                line_y = mood_y + i * (max_line_h + 8)
                screen.blit(mood_label_surfs[i], (mood_x, line_y))
                screen.blit(mood_value_surfs[i], (mood_x + max_label_w + mood_gap, line_y))
                screen.blit(mood_pct_surfs[i], (mood_x + max_label_w + mood_gap + max_value_w + mood_gap, line_y))

            # Prepare sensor block (right-aligned) and place it slightly higher to avoid VOC clipping.
            sensor_lines = [
                ("Temperatur:", f"{temp:.1f} °C"),
                ("Dezibel:", f"{db:.1f} dB"),
                ("CO2:", f"{co2} ppm"),
                ("VOC:", f"{voc} ppb"),
            ]

            sensor_label_surfs = []
            sensor_value_surfs = []
            max_sensor_label_w = 0
            max_sensor_value_w = 0
            max_sensor_line_h = 0
            for lbl, val in sensor_lines:
                s_lbl = sensor_font.render(lbl, True, (255,255,255))
                s_val = sensor_font.render(val, True, (255,255,255))
                sensor_label_surfs.append(s_lbl)
                sensor_value_surfs.append(s_val)
                max_sensor_label_w = max(max_sensor_label_w, s_lbl.get_width())
                max_sensor_value_w = max(max_sensor_value_w, s_val.get_width())
                max_sensor_line_h = max(max_sensor_line_h, s_lbl.get_height(), s_val.get_height())

            sensor_block_width = max_sensor_label_w + 8 + max_sensor_value_w
            max_allowed_sensor_x = screen.get_width() - sensor_block_width - 20

            # Right-align the sensor block (user requested rechtsbündig).
            sensor_x = max_allowed_sensor_x

            # Compute total sensor block height and choose sensor_y higher to avoid VOC being clipped.
            line_spacing = max_sensor_line_h + 8
            total_sensor_height = len(sensor_lines) * line_spacing

            # Prefer to position sensors slightly above the mood block baseline so VOC (last line) stays visible.
            # Start a bit higher than mood_y, but clamp to screen bounds.
            desired_sensor_y = mood_y - 20  # move sensors a bit higher than mood baseline
            # Ensure sensors are fully on-screen vertically
            sensor_y = min(desired_sensor_y, screen.get_height() - total_sensor_height - 20)
            sensor_y = max(20, sensor_y)

            # If right-aligned block overlaps mood block horizontally (no room), fall back to placing below mood block
            if sensor_x < mood_x + mood_block_width + 8:
                # Not enough horizontal space to the right: place the sensor block below mood block (guarantees visibility)
                sensor_x = mood_x
                sensor_y = mood_y + len(mood_lines) * (max_line_h + 8) + 12
                # Clamp vertically if still would run off-screen
                if sensor_y + total_sensor_height + 20 > screen.get_height():
                    sensor_y = max(20, screen.get_height() - total_sensor_height - 20)

            # Draw sensor block stacked vertically (labels + values)
            for i in range(len(sensor_lines)):
                line_y = sensor_y + i * line_spacing
                screen.blit(sensor_label_surfs[i], (sensor_x, line_y))
                screen.blit(sensor_value_surfs[i], (sensor_x + max_sensor_label_w + 8, line_y))

        except Exception:
            pass

        # Upload failed indicator
        if time.time() - upload_failed_time < UPLOAD_FAILED_DURATION:
            try:
                text = sensor_font.render("Upload fehlgeschlagen!", True, (255,50,50))
                screen.blit(text, (screen.get_width()//2 - text.get_width()//2, 50))
            except Exception:
                pass

        pygame.display.flip()
        clock.tick(30)

    pygame.quit()
    return