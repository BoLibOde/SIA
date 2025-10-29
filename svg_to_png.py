import os
import subprocess

# Pfad zu deinem Media-Ordner (anpassen, falls nötig)
MEDIA_DIR = "/home/bOde/Desktop/SIA/Media"

# Prüfen, ob Inkscape installiert ist
def check_inkscape():
    try:
        subprocess.run(["inkscape", "--version"], check=True, capture_output=True)
        print("✅ Inkscape gefunden.")
        return True
    except Exception as e:
        print("❌ Inkscape wurde nicht gefunden! Bitte installiere es mit:")
        print("   sudo apt install inkscape")
        return False

# SVG → PNG konvertieren
def convert_svg_to_png(svg_path, output_path):
    try:
        subprocess.run([
            "inkscape",
            svg_path,
            "--export-type=png",
            f"--export-filename={output_path}"
        ], check=True)
        print(f"🖼️  {os.path.basename(svg_path)} → {os.path.basename(output_path)}")
    except subprocess.CalledProcessError as e:
        print(f"⚠️ Fehler bei {svg_path}: {e}")

def main():
    if not check_inkscape():
        return

    # Alle SVG-Dateien im Media-Ordner finden
    for filename in os.listdir(MEDIA_DIR):
        if filename.lower().endswith(".svg"):
            svg_path = os.path.join(MEDIA_DIR, filename)
            png_path = os.path.join(MEDIA_DIR, filename.replace(".svg", ".png"))
            convert_svg_to_png(svg_path, png_path)

    print("\n✅ Alle SVG-Dateien wurden erfolgreich in PNGs umgewandelt.")

if __name__ == "__main__":
    main()
