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
        ru:remove_stt_data_prompt) echo "Удалить также сохраненные модели и файлы обоих STT-серверов? [y/N]: " ;;
        en:remove_stt_data_prompt) echo "Also remove saved models and files for both STT servers? [y/N]: " ;;
        ru:stopping_parakeet) echo "Останавливаю и удаляю контейнер Parakeet..." ;;
        en:stopping_parakeet) echo "Stopping and removing the Parakeet container..." ;;
        ru:stopping_gigastt) echo "Останавливаю и удаляю контейнер GigaSTT..." ;;
        en:stopping_gigastt) echo "Stopping and removing the GigaSTT container..." ;;
        ru:docker_sudo) echo "Для доступа к Docker могут требоваться права sudo. Повторяю через sudo..." ;;
        en:docker_sudo) echo "Docker access may require sudo. Retrying with sudo..." ;;
        ru:compose_missing) echo "Docker Compose не найден, остановка контейнера пропущена." ;;
        en:compose_missing) echo "Docker Compose not found, skipping container shutdown." ;;
        ru:stt_cleanup_failed) echo "Не удалось удалить контейнер $2. Его модели сохранены для безопасной повторной попытки." ;;
        en:stt_cleanup_failed) echo "Failed to remove the $2 container. Its models were kept for a safe retry." ;;
        ru:stt_container_conflict) echo "Контейнер '$2' не похож на установленный Typr STT-сервер и оставлен без изменений (image: $3)." ;;
        en:stt_container_conflict) echo "Container '$2' does not look like a Typr STT server and was left unchanged (image: $3)." ;;
        ru:stt_containers_removed) echo "Локальные контейнеры Parakeet и GigaSTT удалены, если они были установлены." ;;
        en:stt_containers_removed) echo "Local Parakeet and GigaSTT containers were removed if installed." ;;
        ru:stt_data_removed) echo "Сохраненные модели и файлы STT удалены." ;;
        en:stt_data_removed) echo "Saved STT models and files were removed." ;;
        ru:stt_data_partial) echo "Часть STT-данных не удалось удалить; она сохранена для безопасной повторной попытки." ;;
        en:stt_data_partial) echo "Some STT data could not be removed and was kept for a safe retry." ;;
        ru:stt_data_kept) echo "Сохраненные модели STT оставлены для быстрой переустановки." ;;
        en:stt_data_kept) echo "Saved STT models were kept for a faster reinstall." ;;
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

# Remove both supported STT containers. Model data is kept by default.
PARAKEET_DIR="${HOME:-$(getent passwd "$USER" | cut -d: -f6)}/docker/parakeet-tdt"
GIGASTT_CONTAINER="gigastt"
GIGASTT_VOLUME="gigastt-models"
DOCKER_CMD=()
if command -v docker >/dev/null 2>&1; then
    if docker info >/dev/null 2>&1; then
        DOCKER_CMD=(docker)
    elif sudo -n docker info >/dev/null 2>&1; then
        DOCKER_CMD=(sudo docker)
    else
        msg docker_sudo
        if sudo -v && sudo docker info >/dev/null 2>&1; then
            DOCKER_CMD=(sudo docker)
        fi
    fi
fi

parakeet_removed=true
gigastt_removed=true

if [ ${#DOCKER_CMD[@]} -gt 0 ]; then
    for parakeet_container in parakeet-tdt parakeet-cpu; do
        if ! "${DOCKER_CMD[@]}" container inspect "$parakeet_container" >/dev/null 2>&1; then
            continue
        fi
        parakeet_image=$("${DOCKER_CMD[@]}" container inspect --format '{{.Config.Image}}' "$parakeet_container")
        parakeet_service=$("${DOCKER_CMD[@]}" container inspect --format '{{index .Config.Labels "com.docker.compose.service"}}' "$parakeet_container")
        parakeet_label=$("${DOCKER_CMD[@]}" container inspect --format '{{index .Config.Labels "io.typr.stt"}}' "$parakeet_container")
        if [ "$parakeet_image" = "parakeet-tdt:cpu" ] \
            || [ "$parakeet_service" = "parakeet" ] \
            || [ "$parakeet_service" = "parakeet-cpu" ] \
            || [ "$parakeet_label" = "parakeet" ]; then
            msg stopping_parakeet
            if ! "${DOCKER_CMD[@]}" rm -f "$parakeet_container" >/dev/null; then
                parakeet_removed=false
                msg stt_cleanup_failed "Parakeet"
            fi
        else
            parakeet_removed=false
            msg stt_container_conflict "$parakeet_container" "$parakeet_image"
        fi
    done

    if "${DOCKER_CMD[@]}" container inspect "$GIGASTT_CONTAINER" >/dev/null 2>&1; then
        gigastt_image=$("${DOCKER_CMD[@]}" container inspect --format '{{.Config.Image}}' "$GIGASTT_CONTAINER")
        gigastt_label=$("${DOCKER_CMD[@]}" container inspect --format '{{index .Config.Labels "io.typr.stt"}}' "$GIGASTT_CONTAINER")
        if [ "$gigastt_image" = "ghcr.io/ekhodzitsky/gigastt:latest" ] || [ "$gigastt_label" = "gigastt" ]; then
            msg stopping_gigastt
            if ! "${DOCKER_CMD[@]}" rm -f "$GIGASTT_CONTAINER" >/dev/null; then
                gigastt_removed=false
                msg stt_cleanup_failed "GigaSTT"
            fi
        else
            gigastt_removed=false
            msg stt_container_conflict "$GIGASTT_CONTAINER" "$gigastt_image"
        fi
    fi
else
    parakeet_removed=false
    gigastt_removed=false
fi

if [ "$parakeet_removed" = true ] && [ "$gigastt_removed" = true ]; then
    msg stt_containers_removed
fi

echo
read -rp "$(msg remove_stt_data_prompt)" remove_stt_data
remove_stt_data=${remove_stt_data:-n}
if [[ "$remove_stt_data" =~ ^[YyДд]$ ]]; then
    stt_data_removed=true
    if [ "$parakeet_removed" = true ]; then
        rm -rf "$PARAKEET_DIR"
    elif [ -d "$PARAKEET_DIR" ]; then
        stt_data_removed=false
    fi
    if [ "$gigastt_removed" = true ] && [ ${#DOCKER_CMD[@]} -gt 0 ]; then
        if "${DOCKER_CMD[@]}" volume inspect "$GIGASTT_VOLUME" >/dev/null 2>&1 \
            && ! "${DOCKER_CMD[@]}" volume rm "$GIGASTT_VOLUME" >/dev/null; then
            stt_data_removed=false
        fi
    elif [ "$gigastt_removed" = false ]; then
        stt_data_removed=false
    fi
    if [ "$stt_data_removed" = true ]; then
        msg stt_data_removed
    else
        msg stt_data_partial
    fi
else
    msg stt_data_kept
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
