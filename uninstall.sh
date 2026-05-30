#!/bin/bash
# Typr Uninstall Script for Linux

set -euo pipefail

echo "========================================="
echo "  Typr Uninstaller"
echo "========================================="
echo

# 1. Detect Operating System for informational output
OS_NAME="Unknown Linux"
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS_NAME=${NAME:-"Unknown Linux"}
fi
echo "Running on: $OS_NAME"
echo

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

echo "Stopping running Typr processes (if any)..."
pkill -f "$VENV_DIR/bin/typr" 2>/dev/null || true
pkill -x typr 2>/dev/null || true
pkill -x typr-gui 2>/dev/null || true
pkill -f "python.* -m typr" 2>/dev/null || true
pkill -f "python.*src/typr" 2>/dev/null || true
sleep 1

# Force stop only if still running.
pkill -9 -f "$VENV_DIR/bin/typr" 2>/dev/null || true
pkill -9 -x typr 2>/dev/null || true
pkill -9 -x typr-gui 2>/dev/null || true
pkill -9 -f "python.* -m typr" 2>/dev/null || true
pkill -9 -f "python.*src/typr" 2>/dev/null || true

echo "Removing desktop integration files..."
rm -f ~/.local/share/applications/org.typr.desktop
rm -f ~/.config/autostart/typr.desktop
rm -f ~/.local/share/icons/hicolor/scalable/apps/typr.svg
rm -f ~/.local/share/icons/hicolor/22x22/apps/typr.svg

if command -v gtk-update-icon-cache &> /dev/null; then
    gtk-update-icon-cache -f ~/.local/share/icons/hicolor 2>/dev/null || true
fi

echo "Removing Typr user configuration, cache, and history..."
rm -rf ~/.config/typr
rm -rf ~/.cache/typr
rm -rf ~/.local/state/typr
rm -rf ~/.local/share/typr

echo "Removing legacy user-level Python install (if present)..."
python3 -m pip uninstall -y typr 2>/dev/null || true
rm -f ~/.local/bin/typr
rm -f ~/.local/bin/typr-gui

echo "Removing virtual environment..."
if [ -d "$VENV_DIR" ]; then
    rm -rf "$VENV_DIR"
    echo "Virtual environment removed."
fi

# Optional cleanup for local STT container (Parakeet)
PARAKEET_DIR="${HOME:-$(getent passwd "$USER" | cut -d: -f6)}/docker/parakeet-tdt"
if [ -d "$PARAKEET_DIR" ]; then
    echo
    read -rp "Would you like to remove the local Parakeet STT Docker container? [y/N]: " stt_yr
    stt_yr=${stt_yr:-n}
    if [[ "$stt_yr" =~ ^[Yy]$ ]]; then
        COMPOSE_CMD=()
        if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
            COMPOSE_CMD=(docker compose)
        elif command -v docker-compose >/dev/null 2>&1; then
            COMPOSE_CMD=(docker-compose)
        fi

        if [ ${#COMPOSE_CMD[@]} -gt 0 ]; then
            echo "Stopping and removing Parakeet container..."
            if ! (cd "$PARAKEET_DIR" && "${COMPOSE_CMD[@]}" down); then
                echo "Docker access may require sudo. Retrying with sudo..."
                sudo -v
                (cd "$PARAKEET_DIR" && sudo "${COMPOSE_CMD[@]}" down) || true
            fi
        else
            echo "Docker compose not found, skipping container shutdown."
        fi

        read -rp "Also remove Parakeet repository directory '$PARAKEET_DIR' (including models)? [y/N]: " stt_rm_dir
        stt_rm_dir=${stt_rm_dir:-n}
        if [[ "$stt_rm_dir" =~ ^[Yy]$ ]]; then
            rm -rf "$PARAKEET_DIR"
            echo "Removed: $PARAKEET_DIR"
        fi
    fi
fi

# Clean up udev rules interactively
UDEV_RULE_FILE="/etc/udev/rules.d/99-uinput.rules"
if [ -f "$UDEV_RULE_FILE" ]; then
    echo
    read -rp "Would you like to remove the custom udev rule for /dev/uinput access ($UDEV_RULE_FILE)? [y/N]: " yr
    yr=${yr:-n}
    if [[ "$yr" =~ ^[Yy]$ ]]; then
        echo "Removing udev rule (may require sudo)..."
        sudo rm -f "$UDEV_RULE_FILE"
        echo "Reloading udev rules..."
        if command -v udevadm &>/dev/null; then
            sudo udevadm control --reload-rules && sudo udevadm trigger
        fi
        echo "udev rules updated."
    fi
fi

echo
echo "========================================="
echo "  Uninstall Complete"
echo "========================================="
echo
echo "Kept intact:"
echo "- Project repository directory: $SCRIPT_DIR"
echo

# Inform about group membership
if groups | grep -q "\binput\b"; then
    echo "Note: Your user is still a member of the 'input' group."
    echo "If you wish to remove yourself from this group, you can run:"
    echo "  sudo gpasswd -d $USER input"
    echo
fi
