#!/bin/bash
# Typr Uninstall Script for Arch/CachyOS

set -euo pipefail

echo "========================================="
echo "  Typr Uninstaller"
echo "========================================="
echo

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

echo "Stopping running Typr processes (if any)..."
pkill -f "$VENV_DIR/bin/typr" 2>/dev/null || true
pkill -x typr 2>/dev/null || true
pkill -x typr-gui 2>/dev/null || true
sleep 1

# Force stop only if still running.
pkill -9 -f "$VENV_DIR/bin/typr" 2>/dev/null || true
pkill -9 -x typr 2>/dev/null || true
pkill -9 -x typr-gui 2>/dev/null || true

echo "Removing desktop integration files..."
rm -f ~/.local/share/applications/org.typr.desktop
rm -f ~/.config/autostart/typr.desktop
rm -f ~/.local/share/icons/hicolor/scalable/apps/typr.svg
rm -f ~/.local/share/icons/hicolor/22x22/apps/typr.svg

if command -v gtk-update-icon-cache &> /dev/null; then
    gtk-update-icon-cache -f ~/.local/share/icons/hicolor 2>/dev/null || true
fi

echo "Removing Typr user configuration and data..."
rm -rf ~/.config/typr
rm -rf ~/.cache/typr
rm -rf ~/.local/state/typr

echo "Removing legacy user-level Python install (if present)..."
python3 -m pip uninstall -y typr 2>/dev/null || true
rm -f ~/.local/bin/typr
rm -f ~/.local/bin/typr-gui

echo
echo "========================================="
echo "  Uninstall Complete"
echo "========================================="
echo
echo "Kept intact:"
echo "- Project directory: $SCRIPT_DIR"
echo "- Virtual environment: $VENV_DIR"
echo
