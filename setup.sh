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
# SIA Raspberry Pi Setup Script (robust)
# =============================================================================

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Configuration
REPO_URL="https://github.com/BoLibOde/SIA.git"
INSTALL_DIR="$HOME/Desktop/SIA"
VENV_NAME=".venv"

echo -e "${GREEN}=== SIA Raspberry Pi Setup Script ===${NC}"
echo ""

# Prevent running as root (to avoid HOME=/root issues)
if [ "$(id -u)" -eq 0 ]; then
    echo -e "${RED}Do not run this script as root.${NC}"
    echo "Run it as your normal user (the script uses sudo for apt commands)."
    exit 1
fi

# -----------------------------------------------------------------------------
# Step 1: Update System and Install Required Packages
# -----------------------------------------------------------------------------
echo -e "${YELLOW}[1/6] Updating system packages...${NC}"
sudo apt update
sudo apt upgrade -y

echo -e "${YELLOW}[2/6] Installing required packages...${NC}"
sudo apt install -y \
    git \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    libsdl2-dev \
    libsdl2-image-dev \
    libsdl2-mixer-dev \
    libsdl2-ttf-dev \
    libportaudio2 \
    libportaudiocpp0 \
    portaudio19-dev

echo -e "${GREEN}System packages installed successfully.${NC}"

# -----------------------------------------------------------------------------
# Step 2: Remove Existing SIA Directory
# -----------------------------------------------------------------------------
echo -e "${YELLOW}[3/6] Removing existing SIA directory (if exists)...${NC}"
if [ -d "$INSTALL_DIR" ]; then
    rm -rf "$INSTALL_DIR"
    echo -e "${GREEN}Removed existing SIA directory.${NC}"
else
    echo "No existing SIA directory found."
fi

# -----------------------------------------------------------------------------
# Step 3: Clone Repository
# -----------------------------------------------------------------------------
echo -e "${YELLOW}[4/6] Cloning SIA repository...${NC}"

# Ensure Desktop directory exists
mkdir -p "$HOME/Desktop"

cd "$HOME/Desktop"
if ! git clone "$REPO_URL"; then
    echo -e "${RED}Error: git clone failed. Check your network and repository URL.${NC}"
    exit 1
fi
echo -e "${GREEN}Repository cloned successfully.${NC}"

# -----------------------------------------------------------------------------
# Step 4: Prepare for virtual environment creation
# -----------------------------------------------------------------------------
echo -e "${YELLOW}[5/6] Preparing virtual environment...${NC}"
if [ ! -d "$INSTALL_DIR" ]; then
    echo -e "${RED}Error: expected directory $INSTALL_DIR not found after clone.${NC}"
    exit 1
fi

cd "$INSTALL_DIR"

# Confirm python3 exists
if ! command -v python3 >/dev/null 2>&1; then
    echo -e "${RED}Error: python3 is not installed.${NC}"
    exit 1
fi

# Confirm venv support is available
if ! python3 -c "import venv" >/dev/null 2>&1; then
    echo -e "${RED}python3 venv module not available. Please install python3-venv:${NC}"
    echo "  sudo apt update && sudo apt install -y python3-venv"
    exit 1
fi

# Create virtual environment and check for errors
echo "Creating virtual environment in $INSTALL_DIR/$VENV_NAME ..."
if ! python3 -m venv "$VENV_NAME"; then
    echo -e "${RED}Error: failed to create virtual environment.${NC}"
    echo "Run the following manually to see the error:"
    echo "  python3 -m venv '$VENV_NAME'"
    exit 1
fi

# Activate virtual environment
# shellcheck disable=SC1091
source "$VENV_NAME/bin/activate"

# Upgrade pip and install dependencies
pip install --upgrade pip
if [ -f requirements.txt ]; then
    echo "Installing Python dependencies from requirements.txt..."
    pip install -r requirements.txt
else
    echo "No requirements.txt found in $INSTALL_DIR"
fi

# Optional: Install audio support packages
echo "Installing optional audio support packages (sounddevice numpy)..."
pip install sounddevice numpy || echo "Note: sounddevice/numpy installation may fail due to missing system dependencies"

echo -e "${GREEN}Python dependencies installed successfully.${NC}"

# Deactivate virtual environment
deactivate

# -----------------------------------------------------------------------------
# Done
# -----------------------------------------------------------------------------
echo ""
echo -e "${GREEN}=== Setup Complete! ===${NC}"
echo ""
echo "To run the SIA application:"
echo "  1. cd $INSTALL_DIR"
echo "  2. source $VENV_NAME/bin/activate"
echo "  3. python ui.py  (or the appropriate entry point)"
echo ""
