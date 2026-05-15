#!/bin/bash
# Typr Installation Script for Arch/CachyOS

set -e

echo "========================================="
echo "  Typr Installer for CachyOS/Arch Linux"
echo "========================================="
echo

# Check for pacman
if ! command -v pacman &> /dev/null; then
    echo "Error: This script is designed for Arch-based distributions."
    exit 1
fi

# Install system dependencies
echo "Installing system dependencies..."
sudo pacman -S --needed --noconfirm \
    python \
    python-pip \
    python-pyqt6 \
    python-pyaudio \
    python-dbus \
    wl-clipboard \
    xclip \
    xsel \
    portaudio

echo

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
VENV_PIP="$VENV_DIR/bin/pip"

# Ensure virtual environment exists
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment in $VENV_DIR..."
    python -m venv "$VENV_DIR"
fi

# Install Python package
echo "Installing Typr Python package and dependencies into $VENV_DIR..."
"$VENV_PIP" install --upgrade pip
"$VENV_PIP" install -e "$SCRIPT_DIR"

echo

# Install desktop entries
echo "Installing desktop entries..."
mkdir -p ~/.local/share/applications
cp "$SCRIPT_DIR/resources/org.typr.desktop" ~/.local/share/applications/
sed -i "s|^Exec=.*|Exec=$VENV_DIR/bin/typr|" ~/.local/share/applications/org.typr.desktop

# Install autostart entry
mkdir -p ~/.config/autostart
cp "$SCRIPT_DIR/resources/typr.desktop" ~/.config/autostart/
sed -i "s|^Exec=.*|Exec=$VENV_DIR/bin/typr|" ~/.config/autostart/typr.desktop

# Install icons
echo "Installing icons..."
mkdir -p ~/.local/share/icons/hicolor/scalable/apps
mkdir -p ~/.local/share/icons/hicolor/22x22/apps

cp "$SCRIPT_DIR/resources/icons/typr.svg" ~/.local/share/icons/hicolor/scalable/apps/
cp "$SCRIPT_DIR/resources/icons/typr-idle.svg" ~/.local/share/icons/hicolor/22x22/apps/typr.svg

# Update icon cache if gtk-update-icon-cache is available
if command -v gtk-update-icon-cache &> /dev/null; then
    gtk-update-icon-cache -f ~/.local/share/icons/hicolor 2>/dev/null || true
fi

echo
echo "========================================="
echo "  Installation Complete!"
echo "========================================="
echo
echo "Next steps:"
echo "1. Run '$VENV_DIR/bin/typr' to start the application"
echo "2. Configure your OpenAI API key in Settings"
echo "3. Use Meta+Shift+Space (default) to record"
echo
echo "The application will auto-start on login."
echo "To disable, remove ~/.config/autostart/typr.desktop"
echo
