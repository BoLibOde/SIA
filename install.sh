#!/bin/bash
# Download and run the SIA setup script (uses wget only)
#
# This script requires wget to be installed. If wget is missing it exits
# with instructions for installing it.

SETUP_URL="https://raw.githubusercontent.com/BoLibOde/SIA/master/setup.sh"

echo "Downloading setup.sh from $SETUP_URL"

if ! command -v wget >/dev/null 2>&1; then
    echo "Error: wget is not installed."
    echo "Install it on Raspberry Pi OS with:"
    echo "  sudo apt update && sudo apt install -y wget"
    exit 1
fi

cd "$HOME/Desktop/"

wget -O setup.sh "$SETUP_URL"
chmod +x setup.sh
./setup.sh
