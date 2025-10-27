import pygame
import json
import requests

pygame.init()
screen = pygame.display.set_mode((600, 300))
clock = pygame.time.Clock()
running = True

good = 0
meh = 0
bad = 0


UPLOAD_URL = "http://127.0.0.1:5000/upload"  #URL einsetzen

while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

        # --- Tastenaktionen ---
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_g:
                good += 1
                print(f"Good : {good}")

            elif event.key == pygame.K_m:
                meh += 1
                print(f"Meh : {meh}")

            elif event.key == pygame.K_b:
                bad += 1
                print(f"Bad : {bad}")

            elif event.key == pygame.K_BACKSPACE:
                good = meh = bad = 0
                print("Zähler zurückgesetzt.")

            # Wenn Enter gedrückt wird -> JSON speichern und hochladen
            elif event.key == pygame.K_RETURN:
                data = {"good": good, "meh": meh, "bad": bad}

                # --- JSON lokal speichern ---
                with open("summary.json", "w") as f:
                    json.dump(data, f, indent=4)
                print("summary.json gespeichert!")

                # --- JSON hochladen ---
                try:
                    response = requests.post(UPLOAD_URL, json=data)
                    print("Upload erfolgreich!")
                    print("Server-Antwort:", response.status_code)
                except Exception as e:
                    print("Fehler beim Upload:", e)

    # --- Anzeige aktualisieren ---
    screen.fill("black")
    pygame.display.flip()
    clock.tick(60)

pygame.quit()
