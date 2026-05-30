#!/bin/bash
# Typr Installation Script for Multi-Distribution Linux

set -e

UI_LANG="en"
for locale_var in "${LC_ALL:-}" "${LC_MESSAGES:-}" "${LANG:-}"; do
    locale_val=$(echo "$locale_var" | tr '[:upper:]' '[:lower:]')
    if [[ "$locale_val" == ru* ]]; then
        UI_LANG="ru"
        break
    fi
done

msg() {
    local key="$1"
    case "$UI_LANG:$key" in
        ru:title) echo "  Установщик Typr для Linux" ;;
        en:title) echo "  Typr Installer for Linux" ;;
        ru:stt_prompt) echo "Нужно настроить локальное распознавание речи через Docker контейнер Parakeet? [y/N]: " ;;
        en:stt_prompt) echo "Do you want to set up local speech recognition using the Parakeet Docker container? [y/N]: " ;;
        ru:stt_dryrun_yes) echo "Режим dry-run: контейнер локального распознавания был бы установлен." ;;
        en:stt_dryrun_yes) echo "Dry-run mode: local speech recognition container would be installed." ;;
        ru:stt_dryrun_no) echo "Режим dry-run: шаг локального распознавания пропущен." ;;
        en:stt_dryrun_no) echo "Dry-run mode: local speech recognition step skipped." ;;
        ru:stt_skip) echo "Шаг локального распознавания пропущен по выбору пользователя." ;;
        en:stt_skip) echo "Local speech recognition step skipped by user choice." ;;
        ru:stt_setup_start) echo "Настраиваю локальный контейнер распознавания речи..." ;;
        en:stt_setup_start) echo "Setting up local speech recognition container..." ;;
        ru:stt_repo_missing) echo "Локальный каталог контейнера не найден, клонирую репозиторий..." ;;
        en:stt_repo_missing) echo "Local container directory not found, cloning repository..." ;;
        ru:stt_repo_clone) echo "Клонирую $2 в $3" ;;
        en:stt_repo_clone) echo "Cloning $2 into $3" ;;
        ru:stt_repo_clone_failed) echo "Ошибка: не удалось клонировать репозиторий контейнера." ;;
        en:stt_repo_clone_failed) echo "Error: failed to clone container repository." ;;
        ru:stt_repo_dir) echo "Каталог STT контейнера: $2" ;;
        en:stt_repo_dir) echo "STT container directory: $2" ;;
        ru:docker_missing) echo "Ошибка: Docker не найден. Установите Docker и повторите запуск." ;;
        en:docker_missing) echo "Error: Docker is not installed. Install Docker and rerun." ;;
        ru:git_missing) echo "Ошибка: Git не найден. Установите Git и повторите запуск." ;;
        en:git_missing) echo "Error: Git is not installed. Install Git and rerun." ;;
        ru:stt_starting) echo "Запускаю контейнер (docker compose up -d)..." ;;
        en:stt_starting) echo "Starting container (docker compose up -d)..." ;;
        ru:stt_need_sudo) echo "Для Docker требуются повышенные права. Запустить через sudo? [Y/n]: " ;;
        en:stt_need_sudo) echo "Docker needs elevated privileges. Run via sudo? [Y/n]: " ;;
        ru:stt_sudo_start) echo "Запускаю контейнер через sudo..." ;;
        en:stt_sudo_start) echo "Starting container via sudo..." ;;
        ru:stt_failed) echo "Ошибка: не удалось запустить контейнер Parakeet." ;;
        en:stt_failed) echo "Error: failed to start Parakeet container." ;;
        ru:stt_ready) echo "Локальное распознавание готово." ;;
        en:stt_ready) echo "Local speech recognition is ready." ;;
        ru:stt_endpoint) echo "OpenAI Base URL для настроек: http://127.0.0.1:5092/v1" ;;
        en:stt_endpoint) echo "OpenAI Base URL for settings: http://127.0.0.1:5092/v1" ;;
        ru:unknown_option) echo "Неизвестная опция: $2" ;;
        en:unknown_option) echo "Unknown option: $2" ;;
        ru:usage) echo "Использование: $0 [--dry-run|--check]" ;;
        en:usage) echo "Usage: $0 [--dry-run|--check]" ;;
        ru:detected_os) echo "Обнаружена ОС: $2 $3" ;;
        en:detected_os) echo "Detected OS: $2 $3" ;;
        ru:unsupported_os) echo "Ошибка: операционная система '$2' не поддерживается." ;;
        en:unsupported_os) echo "Error: Operating system '$2' is not supported." ;;
        ru:supported_distros) echo "Сейчас Typr поддерживает Arch-based, Debian/Ubuntu-based и Fedora-based дистрибутивы." ;;
        en:supported_distros) echo "Currently Typr supports Arch-based, Debian/Ubuntu-based, and Fedora-based distributions." ;;
        ru:detected_de) echo "Обнаружено окружение рабочего стола: $2" ;;
        en:detected_de) echo "Detected Desktop Environment: $2" ;;
        ru:unsupported_de) echo "Ошибка: не удалось определить поддерживаемое окружение рабочего стола." ;;
        en:unsupported_de) echo "Error: Could not detect a supported desktop environment." ;;
        ru:supported_de_list) echo "Сейчас поддерживаются: KDE Plasma, GNOME, XFCE, Cinnamon, MATE, LXQt, LXDE, Budgie, и оконные менеджеры (i3, Sway, Hyprland, AwesomeWM, Openbox)." ;;
        en:supported_de_list) echo "Currently supported: KDE Plasma, GNOME, XFCE, Cinnamon, MATE, LXQt, LXDE, Budgie, and window managers (i3, Sway, Hyprland, AwesomeWM, Openbox)." ;;
        ru:gnome_warn1) echo "ПРЕДУПРЕЖДЕНИЕ: в GNOME по умолчанию нет поддержки system tray icons." ;;
        en:gnome_warn1) echo "WARNING: Under GNOME, system tray icons are not supported by default." ;;
        ru:gnome_warn2) echo "Чтобы открыть настройки Typr или историю транскрипций, установите" ;;
        en:gnome_warn2) echo "To access Typr settings or transcription history, you must install" ;;
        ru:gnome_warn3) echo "GNOME extension, например 'AppIndicator and KStatusNotifierItem Support'." ;;
        en:gnome_warn3) echo "a GNOME extension such as 'AppIndicator and KStatusNotifierItem Support'." ;;
        ru:wm_note1) echo "ПРИМЕЧАНИЕ: вы используете standalone window manager ($2)." ;;
        en:wm_note1) echo "NOTE: You are using a standalone window manager ($2)." ;;
        ru:wm_note2) echo "Убедитесь, что запущены system tray monitor или status bar" ;;
        en:wm_note2) echo "Make sure you have a system tray monitor or status bar running" ;;
        ru:wm_note3) echo "(например, waybar, polybar, tint2), чтобы видеть и нажимать иконку Typr в трее." ;;
        en:wm_note3) echo "(e.g., waybar, polybar, tint2) to view and click the Typr tray icon." ;;
        ru:session_clipboard) echo "Определен тип сессии: ${2:-unknown}. Выбран clipboard package: $3" ;;
        en:session_clipboard) echo "Detected session type: ${2:-unknown}. Clipboard package target: $3" ;;
        ru:installing_missing) echo "Устанавливаю недостающие зависимости..." ;;
        en:installing_missing) echo "Installing missing dependencies..." ;;
        ru:requesting_sudo) echo "Запрашиваю sudo-права для установки пакетов..." ;;
        en:requesting_sudo) echo "Requesting sudo privileges for package installation..." ;;
        ru:checking_deps) echo "Проверка системных зависимостей..." ;;
        en:checking_deps) echo "Checking system dependencies..." ;;
        ru:pkg_installed) echo "  [✓] $2 уже установлен." ;;
        en:pkg_installed) echo "  [✓] $2 is already installed." ;;
        ru:pkg_missing) echo "  [✗] $2 отсутствует." ;;
        en:pkg_missing) echo "  [✗] $2 is missing." ;;
        ru:missing_list) echo "Отсутствующие пакеты ($2):" ;;
        en:missing_list) echo "Missing packages ($2):" ;;
        ru:dry_done) echo "Режим dry-run: проверка зависимостей завершена. Пакеты не устанавливались." ;;
        en:dry_done) echo "Dry-run mode: dependency check completed. No packages were installed." ;;
        ru:install_prompt) echo "Установить все отсутствующие пакеты сейчас? [Y/n]: " ;;
        en:install_prompt) echo "Install all missing packages now? [Y/n]: " ;;
        ru:aborted) echo "Установка отменена пользователем." ;;
        en:aborted) echo "Installation aborted by user." ;;
        ru:deps_ok) echo "Все системные зависимости установлены." ;;
        en:deps_ok) echo "All system dependencies are met." ;;
        ru:dry_no_action) echo "Режим dry-run: действий не требуется." ;;
        en:dry_no_action) echo "Dry-run mode: no action needed." ;;
        ru:create_venv) echo "Создаю virtual environment в $2..." ;;
        en:create_venv) echo "Creating virtual environment in $2..." ;;
        ru:install_py) echo "Устанавливаю Typr Python package и зависимости в $2..." ;;
        en:install_py) echo "Installing Typr Python package and dependencies into $2..." ;;
        ru:install_desktop) echo "Устанавливаю desktop entries..." ;;
        en:install_desktop) echo "Installing desktop entries..." ;;
        ru:install_icons) echo "Устанавливаю иконки..." ;;
        en:install_icons) echo "Installing icons..." ;;
        ru:configure_uinput) echo "Настраиваю права для /dev/uinput и группы input..." ;;
        en:configure_uinput) echo "Configuring permissions for /dev/uinput and input group..." ;;
        ru:add_input_group) echo "Добавляю $2 в группу 'input'..." ;;
        en:add_input_group) echo "Adding $2 to the 'input' group..." ;;
        ru:group_note) echo "ПРИМЕЧАНИЕ: возможно, потребуется выйти и войти в систему снова, чтобы изменения группы вступили в силу." ;;
        en:group_note) echo "NOTE: You may need to log out and log back in for group changes to take effect." ;;
        ru:create_udev) echo "Создаю udev rule для доступа к /dev/uinput..." ;;
        en:create_udev) echo "Creating udev rule for /dev/uinput access..." ;;
        ru:reload_udev) echo "Перезагружаю udev rules..." ;;
        en:reload_udev) echo "Reloading udev rules..." ;;
        ru:udev_updated) echo "udev rules обновлены." ;;
        en:udev_updated) echo "udev rules updated." ;;
        ru:complete) echo "  Установка завершена!" ;;
        en:complete) echo "  Installation Complete!" ;;
        ru:next_steps) echo "Дальше:" ;;
        en:next_steps) echo "Next steps:" ;;
        ru:step1) echo "1. Запустите Typr из меню приложений или выполните '$2/bin/typr'" ;;
        en:step1) echo "1. Launch Typr from your application menu or run '$2/bin/typr' to start the application" ;;
        ru:step2) echo "2. Настройте OpenAI API key в Settings" ;;
        en:step2) echo "2. Configure your OpenAI API key in Settings" ;;
        ru:step3) echo "3. Используйте Meta+Shift+Space (по умолчанию) для записи" ;;
        en:step3) echo "3. Use Meta+Shift+Space (default) to record" ;;
        ru:autostart_on) echo "Приложение будет автоматически запускаться при входе в систему." ;;
        en:autostart_on) echo "The application will auto-start on login." ;;
        ru:autostart_off) echo "Чтобы отключить, удалите ~/.config/autostart/typr.desktop" ;;
        en:autostart_off) echo "To disable, remove ~/.config/autostart/typr.desktop" ;;
    esac
}

setup_local_stt() {
    local stt_repo_url="https://github.com/groxaxo/parakeet-tdt-0.6b-v3-fastapi-openai"
    local stt_base_dir="${HOME:-$(getent passwd "$USER" | cut -d: -f6)}/docker"
    local stt_dir="$stt_base_dir/parakeet-tdt"
    local compose_cmd=()

    msg stt_setup_start
    msg stt_repo_dir "$stt_dir"

    if [ ! -d "$stt_dir" ]; then
        msg stt_repo_missing
        if ! command -v git >/dev/null 2>&1; then
            msg git_missing
            exit 1
        fi
        mkdir -p "$stt_base_dir"
        msg stt_repo_clone "$stt_repo_url" "$stt_dir"
        if ! git clone "$stt_repo_url" "$stt_dir"; then
            msg stt_repo_clone_failed
            exit 1
        fi
    fi

    if ! command -v docker >/dev/null 2>&1; then
        msg docker_missing
        exit 1
    fi

    if docker compose version >/dev/null 2>&1; then
        compose_cmd=(docker compose)
    elif command -v docker-compose >/dev/null 2>&1; then
        compose_cmd=(docker-compose)
    else
        msg docker_missing
        exit 1
    fi

    msg stt_starting
    if (cd "$stt_dir" && "${compose_cmd[@]}" up -d); then
        msg stt_ready
        msg stt_endpoint
        return
    fi

    read -rp "$(msg stt_need_sudo)" stt_sudo_yn
    stt_sudo_yn=${stt_sudo_yn:-y}
    if [[ ! "$stt_sudo_yn" =~ ^[Yy]$ ]]; then
        msg stt_failed
        exit 1
    fi

    msg stt_sudo_start
    sudo -v
    if (cd "$stt_dir" && sudo "${compose_cmd[@]}" up -d); then
        msg stt_ready
        msg stt_endpoint
    else
        msg stt_failed
        exit 1
    fi
}

DRY_RUN=false
for arg in "$@"; do
    case "$arg" in
        --dry-run|--check)
            DRY_RUN=true
            ;;
        *)
            msg unknown_option "$arg"
            msg usage
            exit 1
            ;;
    esac
done

echo "========================================="
msg title
echo "========================================="
echo

read -rp "$(msg stt_prompt)" want_local_stt
want_local_stt=${want_local_stt:-n}
if [[ "$want_local_stt" =~ ^[Yy]$ ]]; then
    if [ "$DRY_RUN" = true ]; then
        msg stt_dryrun_yes
    else
        setup_local_stt
    fi
else
    if [ "$DRY_RUN" = true ]; then
        msg stt_dryrun_no
    else
        msg stt_skip
    fi
fi
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

msg detected_os "$OS_NAME" "$OS_VERSION"

if [ -z "$DISTRO" ]; then
    msg unsupported_os "$OS_NAME"
    msg supported_distros
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

msg detected_de "$DE_NAME"

if [ -z "$DE" ]; then
    msg unsupported_de
    msg supported_de_list
    exit 1
fi

# Print warnings for GNOME/Standalone WMs
if [ "$DE" = "gnome" ]; then
    echo
    echo "------------------------------------------------------------"
    msg gnome_warn1
    msg gnome_warn2
    msg gnome_warn3
    echo "------------------------------------------------------------"
    echo
elif [[ "$DE" =~ ^(sway|hyprland|i3|awesome|openbox)$ ]]; then
    echo
    echo "------------------------------------------------------------"
    msg wm_note1 "$DE_NAME"
    msg wm_note2
    msg wm_note3
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
            "portaudio"
        )
        ;;
    debian)
        PACKAGES=(
            "python3"
            "python3-pip"
            "python3-venv"
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
            "portaudio"
            "portaudio-devel"
            "gcc"
            "python3-devel"
        )
        ;;
esac

# Select clipboard package by session type and available tools.
SESSION_TYPE=$(echo "${XDG_SESSION_TYPE:-}" | tr '[:upper:]' '[:lower:]')
CLIPBOARD_PACKAGES=()
if [ "$SESSION_TYPE" = "wayland" ]; then
    CLIPBOARD_PACKAGES=("wl-clipboard")
else
    # For X11 (or unknown session), prefer xclip; xsel is fallback.
    if command -v xclip >/dev/null 2>&1; then
        CLIPBOARD_PACKAGES=("xclip")
    elif command -v xsel >/dev/null 2>&1; then
        CLIPBOARD_PACKAGES=("xsel")
    else
        CLIPBOARD_PACKAGES=("xclip")
    fi
fi

PACKAGES+=("${CLIPBOARD_PACKAGES[@]}")
msg session_clipboard "$SESSION_TYPE" "${CLIPBOARD_PACKAGES[*]}"

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
    msg installing_missing
    msg requesting_sudo
    sudo -v
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

# 5. Full dependency preflight check
msg checking_deps
MISSING_PACKAGES=()
for pkg in "${PACKAGES[@]}"; do
    if check_package "$pkg"; then
        msg pkg_installed "$pkg"
    else
        msg pkg_missing "$pkg"
        MISSING_PACKAGES+=("$pkg")
    fi
done

if [ ${#MISSING_PACKAGES[@]} -gt 0 ]; then
    echo
    msg missing_list "${#MISSING_PACKAGES[@]}"
    for pkg in "${MISSING_PACKAGES[@]}"; do
        echo "  - $pkg"
    done
    echo

    if [ "$DRY_RUN" = true ]; then
        msg dry_done
        exit 0
    fi

    read -rp "$(msg install_prompt)" yr
    yr=${yr:-y}
    if [[ "$yr" =~ ^[Yy]$ ]]; then
        install_packages "${MISSING_PACKAGES[@]}"
    else
        msg aborted
        exit 1
    fi
else
    msg deps_ok
    if [ "$DRY_RUN" = true ]; then
        msg dry_no_action
        exit 0
    fi
fi

echo

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
VENV_PIP="$VENV_DIR/bin/pip"

# Ensure virtual environment exists
if [ ! -d "$VENV_DIR" ]; then
    msg create_venv "$VENV_DIR"
    python3 -m venv "$VENV_DIR"
fi

# Install Python package
msg install_py "$VENV_DIR"
"$VENV_PIP" install --upgrade pip
"$VENV_PIP" install -e "$SCRIPT_DIR"

echo

# Install desktop entries
msg install_desktop
mkdir -p ~/.local/share/applications
cp "$SCRIPT_DIR/resources/org.typr.desktop" ~/.local/share/applications/
sed -i "s|^Exec=.*|Exec=$VENV_DIR/bin/typr|" ~/.local/share/applications/org.typr.desktop

# Install autostart entry
mkdir -p ~/.config/autostart
cp "$SCRIPT_DIR/resources/typr.desktop" ~/.config/autostart/
sed -i "s|^Exec=.*|Exec=$VENV_DIR/bin/typr|" ~/.config/autostart/typr.desktop

# Install icons
msg install_icons
mkdir -p ~/.local/share/icons/hicolor/scalable/apps
mkdir -p ~/.local/share/icons/hicolor/22x22/apps

cp "$SCRIPT_DIR/resources/icons/typr.svg" ~/.local/share/icons/hicolor/scalable/apps/
cp "$SCRIPT_DIR/resources/icons/typr-idle.svg" ~/.local/share/icons/hicolor/22x22/apps/typr.svg

# Update icon cache if gtk-update-icon-cache is available
if command -v gtk-update-icon-cache &> /dev/null; then
    gtk-update-icon-cache -f ~/.local/share/icons/hicolor 2>/dev/null || true
fi

# Add udev rules for /dev/uinput and add user to input group
msg configure_uinput
# Add user to input group if not already there
if ! groups | grep -q "\binput\b"; then
    msg add_input_group "$USER"
    sudo usermod -aG input "$USER"
    msg group_note
fi

# Install udev rule for uinput if not already there
UDEV_RULE_FILE="/etc/udev/rules.d/99-uinput.rules"
if [ ! -f "$UDEV_RULE_FILE" ]; then
    msg create_udev
    echo 'KERNEL=="uinput", GROUP="input", MODE="0660"' | sudo tee "$UDEV_RULE_FILE" > /dev/null
    msg reload_udev
    sudo udevadm control --reload-rules && sudo udevadm trigger
    msg udev_updated
fi

echo
echo "========================================="
msg complete
echo "========================================="

echo
msg next_steps
msg step1 "$VENV_DIR"
msg step2
msg step3
echo
msg autostart_on
msg autostart_off
echo
