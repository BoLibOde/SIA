#!/usr/bin/env bash
set -euo pipefail

# Download setup.sh onto the user's Desktop and run it from there.
# Requires wget to be installed.

SETUP_URL="https://raw.githubusercontent.com/BoLibOde/SIA/master/setup.sh"
DEST_DIR="$HOME/Desktop"
DEST_FILE="$DEST_DIR/setup.sh"

echo "Preparing to download setup.sh to $DEST_FILE"

if ! command -v wget >/dev/null 2>&1; then
    cat <<EOF >&2
Error: wget is not installed.
Install it on Raspberry Pi OS with:
  sudo apt update && sudo apt install -y wget
Then re-run this script.
EOF
    exit 1
fi

mkdir -p "$DEST_DIR"
wget -O "$DEST_FILE" "$SETUP_URL"
chmod +x "$DEST_FILE"

echo "Downloaded and made executable: $DEST_FILE"
echo "Running setup.sh from $DEST_DIR"
# Execute explicitly with bash to ensure bash-only features work
bash "$DEST_FILE"
