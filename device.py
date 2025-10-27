import pygame
import requests
import json

# --- Server-Adresse ---
UPLOAD_URL = "http://192.168.178.115:5000/upload"  # IP deines Servers
#UPLOAD_URL = "http://192.168.178.115:5000/upload"  # IP deines Servers

# --- Pygame Setup ---
pygame.init()
screen = pygame.display.set_mode((600, 300))
pygame.display.set_caption("Pygame Upload Demo")
clock = pygame.time.Clock()
running = True

good = 0
meh = 0
bad = 0

while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_g:
                good += 1
                print(f"Good: {good}")
            elif event.key == pygame.K_m:
                meh += 1
                print(f"Meh: {meh}")
            elif event.key == pygame.K_b:
                bad += 1
                print(f"Bad: {bad}")
            elif event.key == pygame.K_BACKSPACE:
                good = meh = bad = 0
                print("Zähler zurückgesetzt.")
            elif event.key == pygame.K_RETURN:
                # Daten als JSON vorbereiten
                data = {"good": good, "meh": meh, "bad": bad}

                # --- Lokale Ausgabe ---
                print("Daten zum Upload:", data)

                # --- Upload an Flask-Server ---
                try:
                    response = requests.post(UPLOAD_URL, json=data)
                    if response.status_code == 200:
                        print("Upload erfolgreich! Server-Antwort:", response.json())
                    else:
                        print("Fehler beim Upload. Status-Code:", response.status_code)
                except Exception as e:
                    print("Fehler beim Upload:", e)

    # --- Bildschirm füllen ---
    screen.fill((0, 0, 0))
    pygame.display.flip()
    clock.tick(60)

pygame.quit()
