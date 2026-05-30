#!/bin/bash
# Typr Installation Script for Multi-Distribution Linux

set -e

echo "========================================="
echo "  Typr Installer for Linux"
echo "========================================="
echo

# 1. Detect Operating System
OS_ID="unknown"
OS_LIKE="unknown"
OS_NAME="Unknown Linux"
OS_VERSION=""

if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS_ID=${ID:-unknown}
    OS_LIKE=${ID_LIKE:-unknown}
    OS_NAME=${NAME:-"Unknown Linux"}
    OS_VERSION=${VERSION:-""}
fi

OS_ID=$(echo "$OS_ID" | tr '[:upper:]' '[:lower:]')
OS_LIKE=$(echo "$OS_LIKE" | tr '[:upper:]' '[:lower:]')

DISTRO=""
if [[ "$OS_ID" == "arch" || "$OS_LIKE" =~ "arch" ]]; then
    DISTRO="arch"
elif [[ "$OS_ID" == "ubuntu" || "$OS_ID" == "debian" || "$OS_ID" == "linuxmint" || "$OS_ID" == "pop" || "$OS_LIKE" =~ "ubuntu" || "$OS_LIKE" =~ "debian" ]]; then
    DISTRO="debian"
elif [[ "$OS_ID" == "fedora" || "$OS_LIKE" =~ "fedora" || "$OS_LIKE" =~ "rhel" || "$OS_LIKE" =~ "centos" ]]; then
    DISTRO="fedora"
fi

echo "Detected OS: $OS_NAME $OS_VERSION"

if [ -z "$DISTRO" ]; then
    echo "Error: Operating system '$OS_NAME' is not supported."
    echo "Currently Typr supports Arch-based, Debian/Ubuntu-based, and Fedora-based distributions."
    exit 1
fi

# 2. Detect Desktop Environment
DE=""
DE_NAME="Unknown"
CURRENT_DE=$(echo "${XDG_CURRENT_DESKTOP:-}" | tr '[:upper:]' '[:lower:]')
SESSION_DE=$(echo "${DESKTOP_SESSION:-}" | tr '[:upper:]' '[:lower:]')
GDM_DE=$(echo "${GDMSESSION:-}" | tr '[:upper:]' '[:lower:]')

if [[ "$CURRENT_DE" =~ "kde" || "$CURRENT_DE" =~ "plasma" || "$SESSION_DE" =~ "kde" || "$SESSION_DE" =~ "plasma" ]]; then
    DE="kde"
    DE_NAME="KDE Plasma"
elif [[ "$CURRENT_DE" =~ "gnome" || "$SESSION_DE" =~ "gnome" || "$GDM_DE" =~ "gnome" ]]; then
    DE="gnome"
    DE_NAME="GNOME"
elif [[ "$CURRENT_DE" =~ "xfce" || "$SESSION_DE" =~ "xfce" ]]; then
    DE="xfce"
    DE_NAME="XFCE"
elif [[ "$CURRENT_DE" =~ "cinnamon" || "$SESSION_DE" =~ "cinnamon" ]]; then
    DE="cinnamon"
    DE_NAME="Cinnamon"
elif [[ "$CURRENT_DE" =~ "mate" || "$SESSION_DE" =~ "mate" ]]; then
    DE="mate"
    DE_NAME="MATE"
elif [[ "$CURRENT_DE" =~ "lxqt" || "$SESSION_DE" =~ "lxqt" ]]; then
    DE="lxqt"
    DE_NAME="LXQt"
elif [[ "$CURRENT_DE" =~ "lxde" || "$SESSION_DE" =~ "lxde" ]]; then
    DE="lxde"
    DE_NAME="LXDE"
elif [[ "$CURRENT_DE" =~ "budgie" || "$SESSION_DE" =~ "budgie" ]]; then
    DE="budgie"
    DE_NAME="Budgie"
elif [[ "$CURRENT_DE" =~ "sway" || "$SESSION_DE" =~ "sway" ]]; then
    DE="sway"
    DE_NAME="Sway (Window Manager)"
elif [[ "$CURRENT_DE" =~ "hyprland" || "$SESSION_DE" =~ "hyprland" ]]; then
    DE="hyprland"
    DE_NAME="Hyprland (Window Manager)"
elif [[ "$CURRENT_DE" =~ "i3" || "$SESSION_DE" =~ "i3" ]]; then
    DE="i3"
    DE_NAME="i3 (Window Manager)"
elif [[ "$CURRENT_DE" =~ "awesome" || "$SESSION_DE" =~ "awesome" ]]; then
    DE="awesome"
    DE_NAME="AwesomeWM"
elif [[ "$CURRENT_DE" =~ "openbox" || "$SESSION_DE" =~ "openbox" ]]; then
    DE="openbox"
    DE_NAME="Openbox"
fi

echo "Detected Desktop Environment: $DE_NAME"

if [ -z "$DE" ]; then
    echo "Error: Could not detect a supported desktop environment."
    echo "Currently supported: KDE Plasma, GNOME, XFCE, Cinnamon, MATE, LXQt, LXDE, Budgie, and window managers (i3, Sway, Hyprland, AwesomeWM, Openbox)."
    exit 1
fi

# Print warnings for GNOME/Standalone WMs
if [ "$DE" = "gnome" ]; then
    echo
    echo "------------------------------------------------------------"
    echo "WARNING: Under GNOME, system tray icons are not supported by default."
    echo "To access Typr settings or transcription history, you must install"
    echo "a GNOME extension such as 'AppIndicator and KStatusNotifierItem Support'."
    echo "------------------------------------------------------------"
    echo
elif [[ "$DE" =~ ^(sway|hyprland|i3|awesome|openbox)$ ]]; then
    echo
    echo "------------------------------------------------------------"
    echo "NOTE: You are using a standalone window manager ($DE_NAME)."
    echo "Make sure you have a system tray monitor or status bar running"
    echo "(e.g., waybar, polybar, tint2) to view and click the Typr tray icon."
    echo "------------------------------------------------------------"
    echo
fi

# 3. Define and map system packages
PACKAGES=()
case "$DISTRO" in
    arch)
        PACKAGES=(
            "python"
            "python-pip"
            "python-pyqt6"
            "python-pyaudio"
            "wl-clipboard"
            "xclip"
            "xsel"
            "portaudio"
        )
        ;;
    debian)
        PACKAGES=(
            "python3"
            "python3-pip"
            "python3-venv"
            "wl-clipboard"
            "xclip"
            "xsel"
            "portaudio19-dev"
            "libportaudio2"
            "build-essential"
            "python3-dev"
        )
        ;;
    fedora)
        PACKAGES=(
            "python3"
            "python3-pip"
            "wl-clipboard"
            "xclip"
            "xsel"
            "portaudio"
            "portaudio-devel"
            "gcc"
            "python3-devel"
        )
        ;;
esac

# 4. Helper functions to check and install packages
check_package() {
    local pkg="$1"
    case "$DISTRO" in
        arch)
            pacman -Qq "$pkg" &>/dev/null
            ;;
        debian)
            dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null | grep -q "ok installed"
            ;;
        fedora)
            rpm -q "$pkg" &>/dev/null
            ;;
    esac
}

install_packages() {
    local pkgs=("$@")
    echo "Installing missing dependencies..."
    case "$DISTRO" in
        arch)
            sudo pacman -S --needed --noconfirm "${pkgs[@]}"
            ;;
        debian)
            sudo apt-get update
            sudo apt-get install -y "${pkgs[@]}"
            ;;
        fedora)
            sudo dnf install -y "${pkgs[@]}"
            ;;
    esac
}

# 5. Check dependencies interactively
echo "Checking system dependencies..."
MISSING_PACKAGES=()
for pkg in "${PACKAGES[@]}"; do
    if check_package "$pkg"; then
        echo "  [✓] $pkg is already installed."
    else
        echo "  [✗] $pkg is missing."
        read -rp "Package '$pkg' is required. Would you like to install it? [Y/n]: " yr
        yr=${yr:-y}
        if [[ "$yr" =~ ^[Yy]$ ]]; then
            MISSING_PACKAGES+=("$pkg")
        else
            echo "Error: Package '$pkg' is required for Typr. Installation aborted."
            exit 1
        fi
    fi
done

if [ ${#MISSING_PACKAGES[@]} -gt 0 ]; then
    install_packages "${MISSING_PACKAGES[@]}"
else
    echo "All system dependencies are met."
fi

echo

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
VENV_PIP="$VENV_DIR/bin/pip"

# Ensure virtual environment exists
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment in $VENV_DIR..."
    python3 -m venv "$VENV_DIR"
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

# Add udev rules for /dev/uinput and add user to input group
echo "Configuring permissions for /dev/uinput and input group..."
# Add user to input group if not already there
if ! groups | grep -q "\binput\b"; then
    echo "Adding $USER to the 'input' group..."
    sudo usermod -aG input "$USER"
    echo "NOTE: You may need to log out and log back in for group changes to take effect."
fi

# Install udev rule for uinput if not already there
UDEV_RULE_FILE="/etc/udev/rules.d/99-uinput.rules"
if [ ! -f "$UDEV_RULE_FILE" ]; then
    echo "Creating udev rule for /dev/uinput access..."
    echo 'KERNEL=="uinput", GROUP="input", MODE="0660"' | sudo tee "$UDEV_RULE_FILE" > /dev/null
    echo "Reloading udev rules..."
    sudo udevadm control --reload-rules && sudo udevadm trigger
    echo "udev rules updated."
fi

echo
echo "========================================="
echo "  Installation Complete!"
echo "========================================="

echo
echo "Next steps:"
echo "1. Launch Typr from your application menu or run '$VENV_DIR/bin/typr' to start the application"
echo "2. Configure your OpenAI API key in Settings"
echo "3. Use Meta+Shift+Space (default) to record"
echo
echo "The application will auto-start on login."
echo "To disable, remove ~/.config/autostart/typr.desktop"
echo
