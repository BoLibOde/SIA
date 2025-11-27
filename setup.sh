#!/bin/bash
# =============================================================================
# SIA Raspberry Pi Setup Script
# =============================================================================
# This script performs the following:
# 1. Updates the system and installs required packages
# 2. Removes existing SIA directory from Desktop
# 3. Clones the SIA repository from GitHub
# 4. Creates a Python virtual environment
# 5. Installs all required dependencies
# =============================================================================

set -e  # Exit on any error

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
REPO_URL="https://github.com/BoLibOde/SIA.git"
INSTALL_DIR="$HOME/Desktop/SIA"
VENV_NAME=".venv"

echo -e "${GREEN}=== SIA Raspberry Pi Setup Script ===${NC}"
echo ""

# -----------------------------------------------------------------------------
# Step 1: Update System and Install Required Packages
# -----------------------------------------------------------------------------
echo -e "${YELLOW}[1/5] Updating system packages...${NC}"
sudo apt update
sudo apt upgrade -y

echo -e "${YELLOW}[2/5] Installing required packages...${NC}"
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
echo -e "${YELLOW}[3/5] Removing existing SIA directory (if exists)...${NC}"
if [ -d "$INSTALL_DIR" ]; then
    rm -rf "$INSTALL_DIR"
    echo -e "${GREEN}Removed existing SIA directory.${NC}"
else
    echo "No existing SIA directory found."
fi

# -----------------------------------------------------------------------------
# Step 3: Clone Repository
# -----------------------------------------------------------------------------
echo -e "${YELLOW}[4/5] Cloning SIA repository...${NC}"

# Ensure Desktop directory exists
mkdir -p "$HOME/Desktop"

cd "$HOME/Desktop"
git clone "$REPO_URL"
echo -e "${GREEN}Repository cloned successfully.${NC}"

# -----------------------------------------------------------------------------
# Step 4: Create Virtual Environment and Install Dependencies
# -----------------------------------------------------------------------------
echo -e "${YELLOW}[5/5] Setting up Python virtual environment...${NC}"
cd "$INSTALL_DIR"

# Create virtual environment
python3 -m venv "$VENV_NAME"

# Activate virtual environment
source "$VENV_NAME/bin/activate"

# Upgrade pip
pip install --upgrade pip

# Install dependencies from requirements.txt
echo "Installing Python dependencies..."
pip install pygame
pip install requests
pip install adafruit-blinka
pip install adafruit-circuitpython-ccs811
pip install git+https://github.com/pimoroni/scd4x-python.git
pip install adafruit-circuitpython-bme280
pip install adafruit-circuitpython-busdevice

# Optional: Install audio support packages
echo "Installing optional audio support packages..."
pip install sounddevice numpy || echo "Note: sounddevice/numpy installation may fail without audio hardware"

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
echo "To deactivate the virtual environment:"
echo "  deactivate"
echo ""
