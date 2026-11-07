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
        ru:stt_intro) echo "Выберите локальный STT-контейнер и модель:" ;;
        en:stt_intro) echo "Choose a local STT container and model:" ;;
        ru:stt_parakeet_desc) echo "1. Parakeet TDT 0.6B v3 INT8 — очень быстрый CPU STT, автоопределение 25 языков." ;;
        en:stt_parakeet_desc) echo "1. Parakeet TDT 0.6B v3 INT8 — very fast CPU STT with automatic detection of 25 languages." ;;
        ru:stt_gigastt_desc) echo "2. GigaSTT / GigaAM v3 RNNT INT8 — специализирован для русского, компактная модель и хорошая точность русской речи." ;;
        en:stt_gigastt_desc) echo "2. GigaSTT / GigaAM v3 RNNT INT8 — Russian-focused, compact, and accurate for Russian speech." ;;
        ru:stt_both_desc) echo "3. Установить оба контейнера." ;;
        en:stt_both_desc) echo "3. Install both containers." ;;
        ru:stt_none_desc) echo "4. Не устанавливать локальный STT." ;;
        en:stt_none_desc) echo "4. Do not install local STT." ;;
        ru:stt_choice_prompt) echo "Ваш выбор [1]: " ;;
        en:stt_choice_prompt) echo "Your choice [1]: " ;;
        ru:stt_invalid_choice) echo "Ошибка: выберите 1, 2, 3 или 4." ;;
        en:stt_invalid_choice) echo "Error: choose 1, 2, 3, or 4." ;;
        ru:stt_dryrun_parakeet) echo "Режим dry-run: был бы установлен Parakeet TDT 0.6B v3 INT8." ;;
        en:stt_dryrun_parakeet) echo "Dry-run mode: Parakeet TDT 0.6B v3 INT8 would be installed." ;;
        ru:stt_dryrun_gigastt) echo "Режим dry-run: был бы установлен GigaSTT с GigaAM v3 RNNT INT8." ;;
        en:stt_dryrun_gigastt) echo "Dry-run mode: GigaSTT with GigaAM v3 RNNT INT8 would be installed." ;;
        ru:stt_dryrun_no) echo "Режим dry-run: шаг локального распознавания пропущен." ;;
        en:stt_dryrun_no) echo "Dry-run mode: local speech recognition step skipped." ;;
        ru:stt_skip) echo "Шаг локального распознавания пропущен по выбору пользователя." ;;
        en:stt_skip) echo "Local speech recognition step skipped by user choice." ;;
        ru:parakeet_setup_start) echo "Настраиваю контейнер Parakeet..." ;;
        en:parakeet_setup_start) echo "Setting up the Parakeet container..." ;;
        ru:gigastt_setup_start) echo "Настраиваю контейнер GigaSTT..." ;;
        en:gigastt_setup_start) echo "Setting up the GigaSTT container..." ;;
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
        ru:parakeet_starting) echo "Собираю и запускаю CPU-контейнер Parakeet..." ;;
        en:parakeet_starting) echo "Building and starting the Parakeet CPU container..." ;;
        ru:parakeet_name_conflict) echo "Ошибка: контейнер '$2' уже существует, но использует другой image: $3" ;;
        en:parakeet_name_conflict) echo "Error: container '$2' already exists but uses a different image: $3" ;;
        ru:gigastt_starting) echo "Запускаю официальный CPU image GigaSTT..." ;;
        en:gigastt_starting) echo "Starting the official GigaSTT CPU image..." ;;
        ru:gigastt_pulling) echo "Загружаю актуальный Docker image GigaSTT..." ;;
        en:gigastt_pulling) echo "Pulling the current GigaSTT Docker image..." ;;
        ru:gigastt_waiting) echo "Ожидаю готовности GigaSTT (это может занять несколько минут при первой загрузке модели)..." ;;
        en:gigastt_waiting) echo "Waiting for GigaSTT readiness (the first model download may take several minutes)..." ;;
        ru:gigastt_not_ready) echo "Ошибка: GigaSTT не стал готов за $2 секунд. Последние строки логов:" ;;
        en:gigastt_not_ready) echo "Error: GigaSTT did not become ready within $2 seconds. Recent logs:" ;;
        ru:gigastt_configured) echo "Создана новая конфигурация Typr для GigaSTT: http://127.0.0.1:9876/v1, gigaam-v3-rnnt." ;;
        en:gigastt_configured) echo "Created a new Typr configuration for GigaSTT: http://127.0.0.1:9876/v1, gigaam-v3-rnnt." ;;
        ru:gigastt_name_conflict) echo "Ошибка: контейнер '$2' уже существует, но использует другой image: $3" ;;
        en:gigastt_name_conflict) echo "Error: container '$2' already exists but uses a different image: $3" ;;
        ru:stt_need_sudo) echo "Для Docker требуются повышенные права. Запустить через sudo? [Y/n]: " ;;
        en:stt_need_sudo) echo "Docker needs elevated privileges. Run via sudo? [Y/n]: " ;;
        ru:stt_sudo_start) echo "Запускаю контейнер через sudo..." ;;
        en:stt_sudo_start) echo "Starting container via sudo..." ;;
        ru:parakeet_failed) echo "Ошибка: не удалось запустить контейнер Parakeet." ;;
        en:parakeet_failed) echo "Error: failed to start Parakeet container." ;;
        ru:gigastt_failed) echo "Ошибка: не удалось запустить контейнер GigaSTT." ;;
        en:gigastt_failed) echo "Error: failed to start GigaSTT container." ;;
        ru:stt_ready) echo "Локальное распознавание готово." ;;
        en:stt_ready) echo "Local speech recognition is ready." ;;
        ru:parakeet_endpoint) echo "Parakeet: Base URL http://127.0.0.1:5092/v1, модель parakeet-tdt-0.6b-v3" ;;
        en:parakeet_endpoint) echo "Parakeet: Base URL http://127.0.0.1:5092/v1, model parakeet-tdt-0.6b-v3" ;;
        ru:gigastt_endpoint) echo "GigaSTT: Base URL http://127.0.0.1:$2/v1, модель gigaam-v3-rnnt" ;;
        en:gigastt_endpoint) echo "GigaSTT: Base URL http://127.0.0.1:$2/v1, model gigaam-v3-rnnt" ;;
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
        ru:install_prompt) echo "Установить все отсутствующие пакеты и разрешить sudo для сервисов/прав устройств? [Y/n]: " ;;
        en:install_prompt) echo "Install all missing packages and allow sudo for service/device permission setup? [Y/n]: " ;;
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
        ru:step2) echo "2. Проверьте endpoint и модель в Settings; локальному STT API key не нужен. Для внешнего API укажите его параметры." ;;
        en:step2) echo "2. Check the endpoint and model in Settings; local STT needs no API key. Configure provider settings for an external API." ;;
        ru:step3) echo "3. Используйте Ctrl+Alt+Z (по умолчанию) для записи" ;;
        en:step3) echo "3. Use Ctrl+Alt+Z (default) to record" ;;
        ru:autostart_on) echo "Приложение будет автоматически запускаться при входе в систему." ;;
        en:autostart_on) echo "The application will auto-start on login." ;;
        ru:autostart_off) echo "Чтобы отключить, удалите ~/.config/autostart/typr.desktop" ;;
        en:autostart_off) echo "To disable, remove ~/.config/autostart/typr.desktop" ;;
    esac
}

# Installer diagnostics which do not belong to the original message catalogue.
notice() {
    if [ "$UI_LANG" = ru ]; then printf '%s\n' "$1"; else printf '%s\n' "$2"; fi
}

authorize_system_changes() {
    if [ "${SYSTEM_AUTHORIZED:-false}" = true ]; then return; fi
    local answer
    read -rp "$(notice 'Разрешить sudo для настройки сервисов и прав устройств? [Y/n]: ' 'Allow sudo for service and device permission setup? [Y/n]: ')" answer
    if [[ ! "${answer:-y}" =~ ^[YyДд]$ ]]; then msg aborted; exit 1; fi
    sudo -v
    SYSTEM_AUTHORIZED=true
}

docker_cmd=(docker)
# Resolve context metadata without invoking Docker (also used by dry-run).
resolve_docker_endpoint() {
    # Bootstrap simple selections without Python; defer JSON metadata until preflight.
    if [ "${DOCKER_CONTEXT:-}" = default ]; then
        printf '%s\n' unix:///var/run/docker.sock
        return
    fi
    if [ -z "${DOCKER_CONTEXT:-}" ]; then
        if [ -n "${DOCKER_HOST:-}" ]; then
            printf '%s\n' "$DOCKER_HOST"
            return
        fi
        if [ ! -f "${DOCKER_CONFIG:-$HOME/.docker}/config.json" ]; then
            printf '%s\n' unix:///var/run/docker.sock
            return
        fi
    fi
    if ! command -v python3 >/dev/null 2>&1; then
        notice 'Проверка Docker context отложена до установки Python; зависимости engine показаны консервативно.' 'Docker context validation deferred until Python is installed; engine dependencies are reported conservatively.' >&2
        printf '%s\n' deferred
        return
    fi
    python3 - "$UI_LANG" <<'PY'
import json, os, pathlib, sys
root = pathlib.Path(os.environ.get("DOCKER_CONFIG", str(pathlib.Path.home() / ".docker")))
context = os.environ.get("DOCKER_CONTEXT", "")
host = os.environ.get("DOCKER_HOST", "")
try:
    if not context and host:
        print(host)
    else:
        if not context:
            config = root / "config.json"
            context = json.loads(config.read_text()).get("currentContext", "default") if config.exists() else "default"
        if context == "default":
            print("unix:///var/run/docker.sock")
        else:
            for file in (root / "contexts/meta").glob("*/meta.json"):
                data = json.loads(file.read_text())
                if data.get("Name") == context:
                    print(data["Endpoints"]["docker"]["Host"])
                    break
            else:
                raise ValueError("Unknown Docker context")
except (OSError, ValueError, KeyError, TypeError):
    raise SystemExit("Не удалось прочитать Docker context metadata; проверьте настройку context."
                     if sys.argv[1] == "ru" else
                     "Cannot resolve Docker context metadata; check Docker context configuration.")
PY
}

validate_local_endpoint() {
    if [[ "$1" != unix:///* ]]; then
        notice 'Локальный STT требует локальный Docker unix endpoint: удалённый daemon публикует loopback на другом хосте. Выберите локальный context.' 'Local STT requires a local Docker unix endpoint: a remote daemon publishes loopback on another host. Select a local context.' >&2
        return 1
    fi
}

prepare_docker() {
    local error endpoint available=false
    endpoint=$(resolve_docker_endpoint)
    validate_local_endpoint "$endpoint"
    docker_cmd=(env -u DOCKER_CONTEXT -u DOCKER_HOST docker --host "$endpoint")
    if error=$("${docker_cmd[@]}" info 2>&1); then available=true; fi
    # Never elevate or start the system daemon for a custom/rootless endpoint.
    if [[ "$endpoint" != unix:///var/run/docker.sock && "$endpoint" != unix:///run/docker.sock ]]; then
        if [ "$available" = true ]; then return; fi
        printf '%s\n' "$error" >&2
        notice 'Docker endpoint недоступен. Запустите/исправьте выбранный Docker самостоятельно.' 'Docker endpoint unavailable. Start/repair the selected Docker endpoint yourself.' >&2
        exit 1
    fi
    # Only connection/permission failures warrant system-daemon preparation.
    if [ "$available" != true ] && ! [[ "$error" =~ [Pp]ermission\ denied|[Cc]annot\ connect|[Cc]onnection\ refused|[Nn]o\ such\ file ]]; then
        printf '%s\n' "$error" >&2
        exit 1
    fi
    if ! command -v systemctl >/dev/null || ! systemctl show --property=Version --value >/dev/null 2>&1; then
        notice 'Нет работающего systemd. Запустите Docker вручную, проверьте docker info и повторите установку.' 'No running systemd. Start Docker manually, verify docker info, then rerun the installer.' >&2
        exit 1
    fi
    if ! systemctl is-enabled --quiet docker.service || ! systemctl is-active --quiet docker.service; then
        authorize_system_changes
        sudo systemctl enable --now docker.service
    fi
    if "${docker_cmd[@]}" info >/dev/null 2>&1; then return; fi
    # sudo is only a permissions fallback, not a fallback for daemon errors.
    if error=$("${docker_cmd[@]}" info 2>&1); then return; fi
    if [[ "$error" =~ [Pp]ermission\ denied ]]; then
        docker_cmd=(sudo env -u DOCKER_CONTEXT -u DOCKER_HOST docker --host "$endpoint")
        "${docker_cmd[@]}" info >/dev/null
    else
        printf '%s\n' "$error" >&2
        exit 1
    fi
}

wait_for_stt() {
    local container="$1" url="$2" timeout=600
    local deadline=$((SECONDS + timeout))
    notice "Ожидаю готовности $container (до $timeout секунд)..." "Waiting for $container readiness (up to $timeout seconds)..."
    while [ "$SECONDS" -lt "$deadline" ]; do
        if [ "$("${docker_cmd[@]}" container inspect --format '{{.State.Running}}' "$container")" != true ]; then break; fi
        if "${docker_cmd[@]}" exec "$container" python -c \
            'import sys, urllib.request; urllib.request.urlopen(sys.argv[1], timeout=2).close()' "$url" >/dev/null 2>&1; then
            return
        fi
        sleep 2
    done
    notice "Ошибка: $container не готов. Последние строки логов:" "Error: $container is not ready. Recent logs:" >&2
    "${docker_cmd[@]}" logs --tail 50 "$container" >&2 || true
    exit 1
}

verify_parakeet_model() {
    "${docker_cmd[@]}" exec "$1" python -c '
import json, urllib.request
with urllib.request.urlopen("http://localhost:5092/health", timeout=5) as response:
    health = json.load(response)
model = "parakeet-tdt-0.6b-v3"
runtime = health.get("runtime", {}).get(model, {})
if not (health.get("ready") is True and health.get("default_model") == model
        and model in health.get("loaded", []) and model in health.get("models", [])
        and runtime.get("backend") == "cpu" and runtime.get("encoder_precision") == "int8"):
    raise SystemExit("Parakeet must have the default CPU INT8 model loaded; check /health")
' || {
        notice 'Ошибка: Parakeet не подтвердил загруженную CPU INT8 модель.' 'Error: Parakeet did not confirm the loaded CPU INT8 model.' >&2
        return 1
    }
}

setup_parakeet() {
    local stt_repo_url="https://github.com/groxaxo/parakeet-tdt-0.6b-v3-fastapi-openai"
    local stt_base_dir="${HOME:-$(getent passwd "$USER" | cut -d: -f6)}/docker"
    local stt_dir="$stt_base_dir/parakeet-tdt"
    local parakeet_image="parakeet-tdt:cpu"
    local parakeet_container="parakeet-tdt"
    local expected_binding="127.0.0.1:5092"

    msg parakeet_setup_start
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

    mkdir -p "$stt_dir/models"
    msg parakeet_starting
    if ! "${docker_cmd[@]}" build -f "$stt_dir/Dockerfile.cpu" -t "$parakeet_image" "$stt_dir"; then
        msg parakeet_failed
        exit 1
    fi

    if "${docker_cmd[@]}" container inspect "$parakeet_container" >/dev/null 2>&1; then
        local existing_image
        local existing_binding
        local expected_image_id existing_image_id existing_env existing_mount
        existing_image=$("${docker_cmd[@]}" container inspect --format '{{.Config.Image}}' "$parakeet_container")
        if [ "$existing_image" != "$parakeet_image" ]; then
            msg parakeet_name_conflict "$parakeet_container" "$existing_image"
            exit 1
        fi
        existing_binding=$("${docker_cmd[@]}" port "$parakeet_container" 5092/tcp 2>/dev/null)
        expected_image_id=$("${docker_cmd[@]}" image inspect --format '{{.Id}}' "$parakeet_image")
        existing_image_id=$("${docker_cmd[@]}" container inspect --format '{{.Image}}' "$parakeet_container")
        existing_env=$("${docker_cmd[@]}" container inspect --format '{{range .Config.Env}}{{println .}}{{end}}' "$parakeet_container")
        if [ "$existing_binding" != "$expected_binding" ] \
            || [ "$existing_image_id" != "$expected_image_id" ] \
            || ! grep -qx 'PARAKEET_USE_GPU=false' <<< "$existing_env" \
            || ! grep -qx 'PARAKEET_DEFAULT_MODEL=parakeet-tdt-0.6b-v3' <<< "$existing_env" \
            || ! grep -qx 'PARAKEET_BATCHED=0' <<< "$existing_env"; then
            if [ "$("${docker_cmd[@]}" container inspect --format '{{index .Config.Labels "io.typr.stt"}}' "$parakeet_container")" != parakeet ]; then
                msg parakeet_name_conflict "$parakeet_container" "$existing_image (configuration/image mismatch; not owned by Typr)"
                exit 1
            fi
            existing_mount=$("${docker_cmd[@]}" container inspect --format '{{range .Mounts}}{{if eq .Destination "/app/models"}}{{.Type}}:{{.Source}}:{{.RW}}{{end}}{{end}}' "$parakeet_container")
            if [ "$existing_mount" != "bind:$stt_dir/models:true" ]; then
                notice 'Конфликт models mount: контейнер сохранён; требуется ручная проверка.' 'Models mount conflict: container preserved; manual inspection required.' >&2
                exit 1
            fi
            if ! "${docker_cmd[@]}" rm -f "$parakeet_container" >/dev/null; then
                msg parakeet_failed
                exit 1
            fi
        else
            if ! "${docker_cmd[@]}" start "$parakeet_container" >/dev/null; then
                msg parakeet_failed
                exit 1
            fi
        fi
    fi

    if ! "${docker_cmd[@]}" container inspect "$parakeet_container" >/dev/null 2>&1; then
        if ! "${docker_cmd[@]}" run -d \
            --name "$parakeet_container" \
            --restart unless-stopped \
            --label io.typr.stt=parakeet \
            -e PARAKEET_USE_GPU=false \
            -e PARAKEET_DEFAULT_MODEL=parakeet-tdt-0.6b-v3 \
            -e PARAKEET_BATCHED=0 \
            -p 127.0.0.1:5092:5092 \
            -v "$stt_dir/models:/app/models" \
            "$parakeet_image" >/dev/null; then
            msg parakeet_failed
            exit 1
        fi
    fi

    if [ "$("${docker_cmd[@]}" port "$parakeet_container" 5092/tcp 2>/dev/null)" != "$expected_binding" ]; then
        msg parakeet_failed
        exit 1
    fi

    wait_for_stt "$parakeet_container" http://localhost:5092/healthz
    verify_parakeet_model "$parakeet_container"
    msg stt_ready
    msg parakeet_endpoint
}

setup_gigastt() {
    local gigastt_image="ghcr.io/ekhodzitsky/gigastt:latest"
    local gigastt_container="gigastt"
    local gigastt_volume="gigastt-models"
    local expected_binding="127.0.0.1:9876"
    local expected_cmd='["serve","--port","9876","--host","0.0.0.0","--bind-all","--pool-size","1"]'

    msg gigastt_setup_start
    if ! command -v docker >/dev/null 2>&1; then
        msg docker_missing
        exit 1
    fi

    msg gigastt_pulling
    if ! "${docker_cmd[@]}" pull "$gigastt_image"; then
        msg gigastt_failed
        exit 1
    fi

    local latest_image_id
    latest_image_id=$("${docker_cmd[@]}" image inspect --format '{{.Id}}' "$gigastt_image")

    if "${docker_cmd[@]}" container inspect "$gigastt_container" >/dev/null 2>&1; then
        local existing_image
        local existing_label
        local existing_binding
        local existing_image_id
        local existing_cmd
        local existing_variant
        existing_image=$("${docker_cmd[@]}" container inspect --format '{{.Config.Image}}' "$gigastt_container")
        existing_label=$("${docker_cmd[@]}" container inspect --format '{{index .Config.Labels "io.typr.stt"}}' "$gigastt_container")
        if [ "$existing_label" != "gigastt" ]; then
            msg gigastt_name_conflict "$gigastt_container" "$existing_image"
            exit 1
        fi
        existing_image_id=$("${docker_cmd[@]}" container inspect --format '{{.Image}}' "$gigastt_container")
        existing_binding=$("${docker_cmd[@]}" port "$gigastt_container" 9876/tcp 2>/dev/null)
        existing_cmd=$("${docker_cmd[@]}" container inspect --format '{{json .Config.Cmd}}' "$gigastt_container")
        existing_variant=$("${docker_cmd[@]}" container inspect --format '{{range .Config.Env}}{{println .}}{{end}}' "$gigastt_container" | grep -F 'GIGASTT_MODEL_VARIANT=rnnt' || true)
        if [ "$existing_binding" != "$expected_binding" ] \
            || [ "$existing_image_id" != "$latest_image_id" ] \
            || [ "$existing_cmd" != "$expected_cmd" ] \
            || [ -z "$existing_variant" ]; then
            if ! "${docker_cmd[@]}" rm -f "$gigastt_container" >/dev/null; then
                msg gigastt_failed
                exit 1
            fi
        else
            msg gigastt_starting
            if ! "${docker_cmd[@]}" start "$gigastt_container" >/dev/null; then
                msg gigastt_failed
                exit 1
            fi
        fi
    fi

    if ! "${docker_cmd[@]}" container inspect "$gigastt_container" >/dev/null 2>&1; then
        msg gigastt_starting
        "${docker_cmd[@]}" volume create "$gigastt_volume" >/dev/null
        if ! "${docker_cmd[@]}" run -d \
            --name "$gigastt_container" \
            --restart unless-stopped \
            --label io.typr.stt=gigastt \
            -e GIGASTT_MODEL_VARIANT=rnnt \
            -p 127.0.0.1:9876:9876 \
            -v "$gigastt_volume:/home/gigastt/.gigastt/models" \
            "$gigastt_image" \
            serve --port 9876 --host 0.0.0.0 --bind-all --pool-size 1 >/dev/null; then
            msg gigastt_failed
            exit 1
        fi
    fi

    if [ "$("${docker_cmd[@]}" port "$gigastt_container" 9876/tcp 2>/dev/null)" != "$expected_binding" ]; then
        msg gigastt_failed
        exit 1
    fi

    msg gigastt_waiting
    local deadline=$((SECONDS + 600))
    while [ "$SECONDS" -lt "$deadline" ]; do
        if "${docker_cmd[@]}" exec "$gigastt_container" \
            curl --max-time 2 -fsS http://localhost:9876/ready >/dev/null 2>&1; then
            msg stt_ready
            msg gigastt_endpoint "9876"
            return
        fi
        if [ "$("${docker_cmd[@]}" container inspect --format '{{.State.Running}}' "$gigastt_container")" != "true" ]; then
            break
        fi
        sleep 2
    done

    msg gigastt_not_ready 600
    "${docker_cmd[@]}" logs --tail 50 "$gigastt_container" >&2 || true
    exit 1
}

configure_new_gigastt_config() {
    local config_file="${HOME:-$(getent passwd "$USER" | cut -d: -f6)}/.config/typr/config.json"
    if [ "$stt_choice" != "2" ] || [ -e "$config_file" ]; then
        return
    fi

    "$VENV_DIR/bin/python" -c '
from typr.config import AppConfig

config = AppConfig()
config.api_base_url = "http://127.0.0.1:9876/v1"
config.transcription.model = "gigaam-v3-rnnt"
config.save()
'
    msg gigastt_configured
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

if [ "$(id -u)" -eq 0 ]; then
    notice 'Ошибка: запускайте установщик от пользователя без sudo, не от root.' 'Error: run the installer as a regular user without sudo, not as root.' >&2
    exit 1
fi

echo "========================================="
msg title
echo "========================================="
echo

msg stt_intro
msg stt_parakeet_desc
msg stt_gigastt_desc
msg stt_both_desc
msg stt_none_desc
read -rp "$(msg stt_choice_prompt)" stt_choice
stt_choice=${stt_choice:-1}
case "$stt_choice" in
    1)
        [ "$DRY_RUN" != true ] || msg stt_dryrun_parakeet
        ;;
    2)
        [ "$DRY_RUN" != true ] || msg stt_dryrun_gigastt
        ;;
    3)
        if [ "$DRY_RUN" = true ]; then
            msg stt_dryrun_parakeet
            msg stt_dryrun_gigastt
        fi
        ;;
    4)
        if [ "$DRY_RUN" = true ]; then
            msg stt_dryrun_no
        else
            msg stt_skip
        fi
        ;;
    *)
        msg stt_invalid_choice
        exit 1
        ;;
esac
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
            "portaudio"
            "base-devel"
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
# Docker/git are conditional: external STT must not require a local daemon.
DOCKER_ENGINE_PKG=""
if [ "$stt_choice" != 4 ]; then
    DOCKER_ENDPOINT=$(resolve_docker_endpoint)
    if [ "$DOCKER_ENDPOINT" != deferred ] && ! validate_local_endpoint "$DOCKER_ENDPOINT"; then
        # Report all packages in dry-run, but never install or start on this endpoint.
        if [ "$DRY_RUN" != true ]; then exit 1; fi
        ENDPOINT_BLOCKED=true
    fi
    if [[ "$DOCKER_ENDPOINT" = deferred || "$DOCKER_ENDPOINT" = unix:///var/run/docker.sock || "$DOCKER_ENDPOINT" = unix:///run/docker.sock ]]; then
        # Accept alternative engine packaging only if a daemon unit actually exists.
        if [ "$DRY_RUN" = true ] || ! systemctl cat docker.service >/dev/null 2>&1; then
            case "$DISTRO" in
                arch) DOCKER_ENGINE_PKG="docker" ;;
                debian) DOCKER_ENGINE_PKG="docker.io" ;;
                fedora) DOCKER_ENGINE_PKG="moby-engine" ;;
            esac
            PACKAGES+=("$DOCKER_ENGINE_PKG")
            if [ "$DISTRO" = fedora ]; then
                PACKAGES+=(docker-cli)
            fi
        fi
    elif ! command -v docker >/dev/null 2>&1; then
        msg docker_missing
        if [ "$DRY_RUN" != true ]; then exit 1; fi
    fi
fi
if [[ "$stt_choice" = 1 || "$stt_choice" = 3 ]]; then PACKAGES+=(git); fi
case "$DISTRO" in
    arch) PACKAGES+=(kmod systemd) ;;
    debian) PACKAGES+=(kmod udev) ;;
    fedora) PACKAGES+=(kmod systemd-udev) ;;
esac
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

if [ "$DRY_RUN" = true ]; then
    if [ "$stt_choice" != 4 ]; then
        notice 'План: проверить выбранный Docker endpoint; при необходимости enable --now docker.service (только локальный systemd), затем STT с unless-stopped и проверкой готовности.' 'Plan: verify selected Docker endpoint; if needed enable --now docker.service (local systemd only), then STT with unless-stopped and readiness checks.'
    fi
    notice 'План: venv, pip install/check и imports, desktop/autostart, модуль uinput, группа input и udev; при необходимости /etc/modules-load.d/typr-uinput.conf. Никаких изменений.' 'Plan: venv, pip install/check and imports, desktop/autostart, uinput module, input group and udev; /etc/modules-load.d/typr-uinput.conf if needed. No changes.'
fi

if [ ${#MISSING_PACKAGES[@]} -gt 0 ]; then
    echo
    msg missing_list "${#MISSING_PACKAGES[@]}"
    for pkg in "${MISSING_PACKAGES[@]}"; do
        echo "  - $pkg"
    done
    echo

    if [ "$DRY_RUN" = true ]; then
        msg dry_done
        if [ "${ENDPOINT_BLOCKED:-false}" = true ]; then exit 1; fi
        exit 0
    fi

    read -rp "$(msg install_prompt)" yr
    yr=${yr:-y}
    if [[ "$yr" =~ ^[Yy]$ ]]; then
        install_packages "${MISSING_PACKAGES[@]}"
        SYSTEM_AUTHORIZED=true
    else
        msg aborted
        exit 1
    fi
else
    msg deps_ok
    if [ "$DRY_RUN" = true ]; then
        msg dry_no_action
        if [ "${ENDPOINT_BLOCKED:-false}" = true ]; then exit 1; fi
        exit 0
    fi
fi

authorize_system_changes
if [ "$stt_choice" != 4 ]; then
    prepare_docker
    case "$stt_choice" in
        1) setup_parakeet ;;
        2) setup_gigastt ;;
        3) setup_parakeet; setup_gigastt ;;
    esac
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

# Fail explicitly rather than silently deleting an incompatible environment.
if ! "$VENV_DIR/bin/python" -c '
import os, sys
assert sys.prefix != sys.base_prefix, "Not a virtual environment"
assert sys.version_info >= (3, 10), "Python 3.10+ required"
assert os.path.realpath(sys.base_prefix) == os.path.realpath(sys.argv[1]), "Interpreter mismatch"
assert str(sys.version_info[:2]) == sys.argv[2], "Interpreter version mismatch"
' "$(python3 -c 'import sys; print(sys.base_prefix)')" "$(python3 -c 'import sys; print(sys.version_info[:2])')"; then
    notice 'Несовместимая .venv. Пересоздайте её выбранным python3 и повторите установку.' 'Incompatible .venv. Recreate it with the selected python3 and rerun the installer.' >&2
    exit 1
fi

# Install Python package
msg install_py "$VENV_DIR"
"$VENV_PIP" install --upgrade pip
"$VENV_PIP" install -e "$SCRIPT_DIR[dev]"
"$VENV_PIP" check
"$VENV_DIR/bin/python" -c 'from importlib.metadata import version; from PyQt6 import QtCore, QtGui, QtWidgets; import httpx, websockets, evdev; assert version("sounddevice") == "0.5.6"; import typr.__main__'
configure_new_gigastt_config

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
authorize_system_changes
sudo modprobe uinput
# Built-in modules need no persistent loading. Preserve all existing entries.
if [ "$(modinfo -F filename uinput)" != '(builtin)' ] \
    && ! grep -Eq '^[[:space:]]*uinput([[:space:]#]|$)' /etc/modules-load.d/*.conf /usr/lib/modules-load.d/*.conf /run/modules-load.d/*.conf 2>/dev/null; then
    MODULE_LOAD_FILE=/etc/modules-load.d/typr-uinput.conf
    if [ -e "$MODULE_LOAD_FILE" ] || [ -L "$MODULE_LOAD_FILE" ]; then
        notice "Конфликт: проверьте $MODULE_LOAD_FILE; файл не изменён." "Conflict: check $MODULE_LOAD_FILE; file left unchanged." >&2
        exit 1
    fi
    printf 'uinput\n' | sudo tee "$MODULE_LOAD_FILE" >/dev/null
fi
getent group input >/dev/null || sudo groupadd --system input
# Add user to input group if not already there
if ! groups | grep -q "\binput\b"; then
    msg add_input_group "$USER"
    sudo usermod -aG input "$USER"
    msg group_note
fi

# Install udev rule for uinput if not already there
UDEV_RULE_FILE="/etc/udev/rules.d/99-uinput.rules"
if [ ! -e "$UDEV_RULE_FILE" ] && [ ! -L "$UDEV_RULE_FILE" ]; then
    msg create_udev
    echo 'KERNEL=="uinput", GROUP="input", MODE="0660"' | sudo tee "$UDEV_RULE_FILE" > /dev/null
fi

msg reload_udev
sudo udevadm control --reload-rules
sudo udevadm trigger --action=add --sysname-match=uinput
sudo udevadm settle
msg udev_updated
if [ ! -c /dev/uinput ] || [ "$(stat -c '%G:%a' /dev/uinput)" != input:660 ]; then
    notice 'Ошибка прав /dev/uinput: ожидается input:0660. Проверьте существующие udev rules; чужие правила не перезаписаны.' 'Incorrect /dev/uinput permissions: expected input:0660. Check existing udev rules; existing rules were not overwritten.' >&2
    exit 1
fi

echo
echo "========================================="
msg complete
echo "========================================="

echo
msg next_steps
msg step1 "$VENV_DIR"
msg step2
case "$stt_choice" in
    1|3) msg parakeet_endpoint ;;&
    2|3) msg gigastt_endpoint 9876 ;;
esac
msg step3
echo
msg autostart_on
msg autostart_off
echo
