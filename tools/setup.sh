#!/usr/bin/env bash
# Ensure this script runs under bash (so `set -o pipefail` works).
if [ -z "${BASH_VERSION:-}" ]; then
  if command -v bash >/dev/null 2>&1; then
    exec bash "$0" "$@"
  else
    echo "Error: this script requires bash. Please install bash and re-run." >&2
    exit 1
  fi
fi

set -euo pipefail

# =============================================================================
# SIA Raspberry Pi Setup Script (minimal-first ordering)
# =============================================================================

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

REPO_URL="https://github.com/BoLibOde/SIA.git"
INSTALL_DIR="$HOME/Desktop/SIA"
VENV_NAME=".venv"

echo -e "${GREEN}=== SIA Raspberry Pi Setup Script ===${NC}"
echo ""

# Prevent running as root
if [ "$(id -u)" -eq 0 ]; then
    echo -e "${RED}Do not run this script as root.${NC}"
    echo "Run it as your normal user (the script uses sudo for apt commands)."
    exit 1
fi

# -----------------------
# Phase 0: apt update once
# -----------------------
echo -e "${YELLOW}[1/5] Updating package lists...${NC}"
sudo apt update

# ------------------------------------------------------
# Phase 1: Install minimal prerequisites (git, python, venv)
# ------------------------------------------------------
echo -e "${YELLOW}[2/5] Installing minimal prerequisites (git, python, venv)...${NC}"
sudo apt install -y git python3 python3-pip python3-venv
echo -e "${GREEN}Minimal prerequisites installed.${NC}"

# ------------------------------------------------------
# Phase 2: Clone repository and create virtual environment
# ------------------------------------------------------
echo -e "${YELLOW}[3/5] Cloning repository and creating virtualenv...${NC}"
mkdir -p "$HOME/Desktop"
cd "$HOME/Desktop"

if [ -d "$INSTALL_DIR" ]; then
    echo "Removing existing $INSTALL_DIR"
    rm -rf "$INSTALL_DIR"
fi

git clone "$REPO_URL"
cd "$INSTALL_DIR"

echo "Creating virtual environment at $INSTALL_DIR/$VENV_NAME"
python3 -m venv "$VENV_NAME"

# Activate venv
# shellcheck disable=SC1091
source "$VENV_NAME/bin/activate"

# Upgrade pip in the venv
pip install --upgrade pip
echo -e "${GREEN}Virtual environment created and pip upgraded.${NC}"

# ------------------------------------------------------
# Phase 3: Install remaining system libraries needed by pip packages
# ------------------------------------------------------
echo -e "${YELLOW}[4/5] Installing system libraries required for Python packages...${NC}"
# These can be installed while venv is active; sudo apt affects the system, not the venv
sudo apt install -y \
    python3-dev \
    libsdl2-dev \
    libsdl2-image-dev \
    libsdl2-mixer-dev \
    libsdl2-ttf-dev \
    libportaudio2 \
    libportaudiocpp0 \
    portaudio19-dev

echo -e "${GREEN}System libraries installed.${NC}"

# ------------------------------------------------------
# Phase 4: Install Python dependencies inside the venv
# ------------------------------------------------------
echo -e "${YELLOW}[5/5] Installing Python dependencies...${NC}"
if [ -f requirements.txt ]; then
    pip install -r requirements.txt
else
    echo "No requirements.txt found in $INSTALL_DIR"
fi

# Optional audio packages
pip install sounddevice numpy || echo "Warning: sounddevice/numpy may fail on some systems"

deactivate

echo -e "${GREEN}=== Setup Complete! ===${NC}"
echo ""
echo "To run the SIA application:"
echo "  1. cd $INSTALL_DIR"
echo "  2. source $VENV_NAME/bin/activate"
echo "  3. python ui.py  (or the appropriate entry point)"
echo ""
