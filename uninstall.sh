#!/bin/bash
# Typr Uninstall Script for Linux

set -euo pipefail

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
        ru:title) echo "  Удаление Typr для Linux" ;;
        en:title) echo "  Typr Uninstaller for Linux" ;;
        ru:running_on) echo "Операционная система: $2" ;;
        en:running_on) echo "Running on: $2" ;;
        ru:stopping_processes) echo "Останавливаю запущенные процессы Typr, если они есть..." ;;
        en:stopping_processes) echo "Stopping running Typr processes, if any..." ;;
        ru:removing_desktop) echo "Удаляю файлы интеграции с рабочим столом..." ;;
        en:removing_desktop) echo "Removing desktop integration files..." ;;
        ru:removing_user_data) echo "Удаляю настройки, кэш и историю Typr..." ;;
        en:removing_user_data) echo "Removing Typr user configuration, cache, and history..." ;;
        ru:removing_legacy) echo "Удаляю прежнюю пользовательскую Python-установку, если она есть..." ;;
        en:removing_legacy) echo "Removing legacy user-level Python install, if present..." ;;
        ru:removing_venv) echo "Удаляю virtual environment..." ;;
        en:removing_venv) echo "Removing virtual environment..." ;;
        ru:venv_removed) echo "Виртуальное окружение удалено." ;;
        en:venv_removed) echo "Virtual environment removed." ;;
        ru:keep_stt_prompt) echo "Оставить локальный контейнер Parakeet и модели для будущей переустановки Typr? [Y/n]: " ;;
        en:keep_stt_prompt) echo "Keep the local Parakeet container and models for a future Typr reinstall? [Y/n]: " ;;
        ru:stopping_stt) echo "Останавливаю и удаляю контейнер Parakeet..." ;;
        en:stopping_stt) echo "Stopping and removing Parakeet container..." ;;
        ru:docker_sudo) echo "Для доступа к Docker могут требоваться права sudo. Повторяю через sudo..." ;;
        en:docker_sudo) echo "Docker access may require sudo. Retrying with sudo..." ;;
        ru:compose_missing) echo "Docker Compose не найден, остановка контейнера пропущена." ;;
        en:compose_missing) echo "Docker Compose not found, skipping container shutdown." ;;
        ru:stt_cleanup_failed) echo "Контейнер Parakeet не удалось удалить. Каталог и модели сохранены для безопасного повторного удаления: $2" ;;
        en:stt_cleanup_failed) echo "Failed to remove the Parakeet container. The directory and models were kept for a safe retry: $2" ;;
        ru:stt_removed) echo "Файлы контейнера Parakeet и модели удалены: $2" ;;
        en:stt_removed) echo "Removed Parakeet container files and models: $2" ;;
        ru:stt_kept) echo "Файлы контейнера Parakeet и модели сохранены: $2" ;;
        en:stt_kept) echo "Kept Parakeet container files and models: $2" ;;
        ru:udev_prompt) echo "Удалить правило udev для доступа к /dev/uinput ($2)? [y/N]: " ;;
        en:udev_prompt) echo "Remove the custom udev rule for /dev/uinput access ($2)? [y/N]: " ;;
        ru:removing_udev) echo "Удаляю правило udev, могут потребоваться права sudo..." ;;
        en:removing_udev) echo "Removing udev rule, sudo may be required..." ;;
        ru:reloading_udev) echo "Перезагружаю правила udev..." ;;
        en:reloading_udev) echo "Reloading udev rules..." ;;
        ru:udev_updated) echo "Правила udev обновлены." ;;
        en:udev_updated) echo "udev rules updated." ;;
        ru:complete) echo "  Удаление завершено!" ;;
        en:complete) echo "  Uninstall Complete!" ;;
        ru:kept_intact) echo "Сохранено без изменений:" ;;
        en:kept_intact) echo "Kept intact:" ;;
        ru:project_dir) echo "- Каталог репозитория проекта: $2" ;;
        en:project_dir) echo "- Project repository directory: $2" ;;
        ru:input_group_note) echo "Примечание: пользователь по-прежнему состоит в группе 'input'." ;;
        en:input_group_note) echo "Note: Your user is still a member of the 'input' group." ;;
        ru:input_group_remove) echo "Чтобы удалить пользователя из этой группы, выполните:" ;;
        en:input_group_remove) echo "To remove your user from this group, run:" ;;
    esac
}

echo "========================================="
msg title
echo "========================================="
echo

# 1. Detect Operating System for informational output
OS_NAME="Unknown Linux"
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS_NAME=${NAME:-"Unknown Linux"}
fi
msg running_on "$OS_NAME"
echo

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

msg stopping_processes
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

msg removing_desktop
rm -f ~/.local/share/applications/org.typr.desktop
rm -f ~/.config/autostart/typr.desktop
rm -f ~/.local/share/icons/hicolor/scalable/apps/typr.svg
rm -f ~/.local/share/icons/hicolor/22x22/apps/typr.svg

if command -v gtk-update-icon-cache &> /dev/null; then
    gtk-update-icon-cache -f ~/.local/share/icons/hicolor 2>/dev/null || true
fi

msg removing_user_data
rm -rf ~/.config/typr
rm -rf ~/.cache/typr
rm -rf ~/.local/state/typr
rm -rf ~/.local/share/typr

msg removing_legacy
python3 -m pip uninstall -y typr 2>/dev/null || true
rm -f ~/.local/bin/typr
rm -f ~/.local/bin/typr-gui

msg removing_venv
if [ -d "$VENV_DIR" ]; then
    rm -rf "$VENV_DIR"
    msg venv_removed
fi

# Keep the optional local STT installation by default for faster reinstall.
PARAKEET_DIR="${HOME:-$(getent passwd "$USER" | cut -d: -f6)}/docker/parakeet-tdt"
if [ -d "$PARAKEET_DIR" ]; then
    echo
    read -rp "$(msg keep_stt_prompt)" keep_stt
    keep_stt=${keep_stt:-y}
    if [[ "$keep_stt" =~ ^[NnНн]$ ]]; then
        COMPOSE_CMD=()
        stt_shutdown_ok=false
        if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
            COMPOSE_CMD=(docker compose)
        elif command -v docker-compose >/dev/null 2>&1; then
            COMPOSE_CMD=(docker-compose)
        fi

        if [ ${#COMPOSE_CMD[@]} -gt 0 ]; then
            msg stopping_stt
            if (cd "$PARAKEET_DIR" && "${COMPOSE_CMD[@]}" down); then
                stt_shutdown_ok=true
            else
                msg docker_sudo
                if sudo -v && (cd "$PARAKEET_DIR" && sudo "${COMPOSE_CMD[@]}" down); then
                    stt_shutdown_ok=true
                fi
            fi
        else
            msg compose_missing
        fi

        if [ "$stt_shutdown_ok" = true ]; then
            rm -rf "$PARAKEET_DIR"
            msg stt_removed "$PARAKEET_DIR"
        else
            msg stt_cleanup_failed "$PARAKEET_DIR"
        fi
    else
        msg stt_kept "$PARAKEET_DIR"
    fi
fi

# Clean up udev rules interactively
UDEV_RULE_FILE="/etc/udev/rules.d/99-uinput.rules"
if [ -f "$UDEV_RULE_FILE" ]; then
    echo
    read -rp "$(msg udev_prompt "$UDEV_RULE_FILE")" yr
    yr=${yr:-n}
    if [[ "$yr" =~ ^[YyДд]$ ]]; then
        msg removing_udev
        sudo rm -f "$UDEV_RULE_FILE"
        msg reloading_udev
        if command -v udevadm &>/dev/null; then
            sudo udevadm control --reload-rules && sudo udevadm trigger
        fi
        msg udev_updated
    fi
fi

echo
echo "========================================="
msg complete
echo "========================================="
echo
msg kept_intact
msg project_dir "$SCRIPT_DIR"
echo

# Inform about group membership
if groups | grep -q "\binput\b"; then
    msg input_group_note
    msg input_group_remove
    echo "  sudo gpasswd -d $USER input"
    echo
fi
