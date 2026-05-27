"""Internationalization (i18n) helper for Typr."""

import locale
from typing import Any, Optional

try:
    from PyQt6.QtCore import QLocale
    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False


# Determine system language: 'ru' if Russian, else 'en'
lang = 'en'

if PYQT_AVAILABLE:
    try:
        sys_locale = QLocale.system().name()
        if sys_locale.lower().startswith('ru'):
            lang = 'ru'
    except Exception:
        pass

if lang == 'en':
    try:
        default_locale, _ = locale.getdefaultlocale()
        if default_locale and default_locale.lower().startswith('ru'):
            lang = 'ru'
    except Exception:
        pass


# Translation dictionaries
TRANSLATIONS: dict[str, dict[str, str]] = {
    "en": {
        # Tray Icon
        "tray.ready": "Ready - Hold {hotkey} to record",
        "tray.recording": "Recording... Release to stop",
        "tray.transcribing": "Transcribing...",
        "tray.error": "Error - Right-click for options",
        "tray.status_ready": "Status: Ready",
        "tray.status_recording": "Status: Recording",
        "tray.status_transcribing": "Status: Transcribing",
        "tray.status_error": "Status: Error",
        "tray.start_recording": "Start Recording",
        "tray.stop_recording": "Stop Recording",
        "tray.menu.history": "History...",
        "tray.menu.settings": "Settings...",
        "tray.menu.quit": "Quit",
        "tray.status.ready": "Ready",
        "tray.status.recording": "Recording",
        "tray.status.transcribing": "Transcribing",
        "tray.status.error": "Error",
        "tray.status.unknown": "Unknown",
        "tray.notification.error.title": "Typr Error",
        
        # Notifications in App
        "app.notify.text_injection_unavailable": "Text injection unavailable. Check /dev/uinput access and clipboard tools.",
        "app.notify.hotkey_register_failed": "Could not register hotkey. Check Settings for manual configuration.",
        "app.notify.started.title": "Typr Started",
        "app.notify.started.msg": "Hold {hotkey} to record",
        "app.notify.recording_start_failed": "Failed to start recording",
        "app.notify.no_audio": "No audio recorded",
        "app.notify.transcription_complete": "Transcription Complete",
        "app.notify.type_failed": "Failed to type text",
        "app.notify.hotkey_error_title": "Hotkey Error",
        "app.notify.error_title": "Typr Error",

        # History Dialog
        "history.title": "Typr History",
        "history.search": "Search:",
        "history.search_placeholder": "Filter by text...",
        "history.preview_placeholder": "Select an entry to view the full transcription",
        "history.copy_preview": "Copy full text",
        "history.clear_all": "Clear All...",
        "history.close": "Close",
        "history.no_matches": "No entries match.",
        "history.no_history": "No history yet.",
        "history.row.copy": "Copy",
        "history.row.copy_tooltip": "Copy this transcription to the clipboard",
        "history.row.copied": "Copied!",
        "history.row.delete": "Delete",
        "history.row.delete_tooltip": "Delete this transcription from history",
        "history.row.empty": "(empty)",
        "history.delete_confirm.title": "Delete entry",
        "history.delete_confirm.msg": "Delete this transcription from history?",
        "history.clear_confirm.title": "Clear history",
        "history.clear_confirm.msg": "Permanently delete all transcription history?",

        # Settings Dialog
        "settings.title": "Typr Settings",
        "settings.tabs.general": "General",
        "settings.tabs.api": "API",
        "settings.tabs.hotkeys": "Hotkeys",
        "settings.tabs.audio": "Audio",
        "settings.tabs.history": "History",
        "settings.tabs.about": "About",
        "settings.general.transcription": "Transcription",
        "settings.general.model": "Model:",
        "settings.general.fetch": "Fetch",
        "settings.general.fetch_tooltip": "Fetch available models from API endpoint",
        "settings.general.language": "Language:",
        "settings.general.context": "Context:",
        "settings.general.context_placeholder": "Optional context to improve accuracy (e.g., technical terms, names)",
        "settings.general.ui": "User Interface",
        "settings.general.show_notifications": "Show notifications",
        "settings.general.notification_duration": "Notification duration:",
        "settings.api.group": "OpenAI API",
        "settings.api.key": "API Key:",
        "settings.api.key_placeholder": "sk-...",
        "settings.api.key_show": "Show",
        "settings.api.key_hide": "Hide",
        "settings.api.base_url": "Base URL:",
        "settings.api.base_url_placeholder": "https://api.openai.com/v1",
        "settings.api.test_connection": "Test Connection",
        "settings.api.info": "Get your API key from <a href='https://platform.openai.com/api-keys'>OpenAI Platform</a>",
        "settings.hotkeys.group": "Keyboard Shortcuts",
        "settings.hotkeys.ptt": "Push-to-Talk:",
        "settings.hotkeys.cancel": "Cancel Recording:",
        "settings.hotkeys.info": "Note: Hotkeys are registered directly with your input devices via evdev.",
        "settings.audio.group": "Audio Input",
        "settings.audio.device": "Input Device:",
        "settings.audio.device_default": "Default",
        "settings.audio.refresh": "Refresh Devices",
        "settings.audio.sample_rate": "Sample Rate:",
        "settings.audio.sample_rate_val": "16000 Hz (optimal for Whisper)",
        "settings.audio.test_group": "Test Recording",
        "settings.audio.test_btn": "Test Microphone",
        "settings.audio.test_status_recording": "Recording for 2 seconds...",
        "settings.audio.test_status_success": "Success! Recorded {bytes} bytes",
        "settings.audio.test_status_fail": "Recording too short or empty",
        "settings.audio.test_status_error": "Error: {error}",
        "settings.history.group": "Transcription History",
        "settings.history.enabled": "Save transcription history",
        "settings.history.max": "Max entries:",
        "settings.history.entries_suffix": "entries",
        "settings.history.info": "History is stored locally at <code>~/.local/share/typr/history.json</code>. Open the History window from the tray icon to browse and copy past transcriptions.",
        "settings.about.desc": "Speech-to-text for Linux using OpenAI and Parakeet-compatible APIs",
        "settings.about.version": "Version 0.1.0",
        
        # Test Connection Outputs
        "settings.api.test.checking": "Checking connection...",
        "settings.api.test.valid": "Settings are valid.",
        "settings.api.test.valid_transcribe": "Settings are valid: transcription endpoint is available.",
        "settings.api.test.err_401": "Error 401: API key is missing or invalid.",
        "settings.api.test.err_403": "Error 403: access denied (check API key and permissions).",
        "settings.api.test.err_404": "Error 404: endpoint not found (check Base URL).",
        "settings.api.test.err_429": "Error 429: rate limit exceeded.",
        "settings.api.test.err_5xx": "Server error (5xx): issue on API side.",
        "settings.api.test.err_generic": "API error {status}.",
        "settings.api.test.timeout": "Timeout: server did not respond in time.",
        "settings.api.test.network_err": "Network error: {error}",
        "settings.api.test.conn_err": "Connection error: {error}",
        
        # Fetch Models Outputs
        "settings.fetch.no_models.title": "No Models",
        "settings.fetch.no_models.msg": "No models found at this endpoint",
        "settings.fetch.success.title": "Models Loaded",
        "settings.fetch.success.msg": "Found {count} model(s)",
        "settings.fetch.err.title": "Error",
        "settings.fetch.err_404": "Model list endpoint not found. Check Base URL in API settings.",
        "settings.fetch.err_api": "API error: {status}\n{text}",
        "settings.fetch.err_generic": "Failed to fetch models: {error}",
    },
    "ru": {
        # Tray Icon
        "tray.ready": "Готов - Зажмите {hotkey} для записи",
        "tray.recording": "Запись... Отпустите для остановки",
        "tray.transcribing": "Распознавание...",
        "tray.error": "Ошибка - Нажмите правой кнопкой для меню",
        "tray.status_ready": "Статус: Готов",
        "tray.status_recording": "Статус: Запись",
        "tray.status_transcribing": "Статус: Распознавание",
        "tray.status_error": "Статус: Ошибка",
        "tray.start_recording": "Начать запись",
        "tray.stop_recording": "Остановить запись",
        "tray.menu.history": "История...",
        "tray.menu.settings": "Настройки...",
        "tray.menu.quit": "Выход",
        "tray.status.ready": "Готов",
        "tray.status.recording": "Запись",
        "tray.status.transcribing": "Распознавание",
        "tray.status.error": "Ошибка",
        "tray.status.unknown": "Неизвестно",
        "tray.notification.error.title": "Ошибка Typr",
        
        # Notifications in App
        "app.notify.text_injection_unavailable": "Вставка текста недоступна. Проверьте доступ к /dev/uinput и наличие утилит буфера.",
        "app.notify.hotkey_register_failed": "Не удалось зарегистрировать горячую клавишу. Проверьте настройки для ручной конфигурации.",
        "app.notify.started.title": "Typr запущен",
        "app.notify.started.msg": "Зажмите {hotkey} для записи",
        "app.notify.recording_start_failed": "Не удалось начать запись",
        "app.notify.no_audio": "Аудио не записано",
        "app.notify.transcription_complete": "Распознавание завершено",
        "app.notify.type_failed": "Не удалось вставить текст",
        "app.notify.hotkey_error_title": "Ошибка горячей клавиши",
        "app.notify.error_title": "Ошибка Typr",

        # History Dialog
        "history.title": "История Typr",
        "history.search": "Поиск:",
        "history.search_placeholder": "Фильтр по тексту...",
        "history.preview_placeholder": "Выберите запись для просмотра полного текста",
        "history.copy_preview": "Копировать весь текст",
        "history.clear_all": "Очистить всё...",
        "history.close": "Закрыть",
        "history.no_matches": "Нет совпадений.",
        "history.no_history": "История пуста.",
        "history.row.copy": "Копировать",
        "history.row.copy_tooltip": "Копировать эту транскрипцию в буфер обмена",
        "history.row.copied": "Скопировано!",
        "history.row.delete": "Удалить",
        "history.row.delete_tooltip": "Удалить эту транскрипцию из истории",
        "history.row.empty": "(пусто)",
        "history.delete_confirm.title": "Удалить запись",
        "history.delete_confirm.msg": "Удалить эту запись из истории?",
        "history.clear_confirm.title": "Очистить историю",
        "history.clear_confirm.msg": "Безвозвратно удалить всю историю транскрипций?",

        # Settings Dialog
        "settings.title": "Настройки Typr",
        "settings.tabs.general": "Основные",
        "settings.tabs.api": "API",
        "settings.tabs.hotkeys": "Горячие клавиши",
        "settings.tabs.audio": "Аудио",
        "settings.tabs.history": "История",
        "settings.tabs.about": "О программе",
        "settings.general.transcription": "Распознавание речи",
        "settings.general.model": "Модель:",
        "settings.general.fetch": "Получить",
        "settings.general.fetch_tooltip": "Получить доступные модели из эндпоинта API",
        "settings.general.language": "Язык:",
        "settings.general.context": "Контекст:",
        "settings.general.context_placeholder": "Необязательный контекст для улучшения точности (например, термины, имена)",
        "settings.general.ui": "Интерфейс пользователя",
        "settings.general.show_notifications": "Показывать уведомления",
        "settings.general.notification_duration": "Длительность уведомлений:",
        "settings.api.group": "OpenAI API",
        "settings.api.key": "API ключ:",
        "settings.api.key_placeholder": "sk-...",
        "settings.api.key_show": "Показать",
        "settings.api.key_hide": "Скрыть",
        "settings.api.base_url": "Базовый URL:",
        "settings.api.base_url_placeholder": "https://api.openai.com/v1",
        "settings.api.test_connection": "Проверить соединение",
        "settings.api.info": "Получите API-ключ на <a href='https://platform.openai.com/api-keys'>платформе OpenAI</a>",
        "settings.hotkeys.group": "Сочетания клавиш",
        "settings.hotkeys.ptt": "Запись (удержание):",
        "settings.hotkeys.cancel": "Отмена записи:",
        "settings.hotkeys.info": "Примечание: Горячие клавиши регистрируются в системе напрямую через evdev.",
        "settings.audio.group": "Вход звука",
        "settings.audio.device": "Устройство ввода:",
        "settings.audio.device_default": "По умолчанию",
        "settings.audio.refresh": "Обновить список",
        "settings.audio.sample_rate": "Частота дискретизации:",
        "settings.audio.sample_rate_val": "16000 Гц (оптимально для Whisper)",
        "settings.audio.test_group": "Проверка микрофона",
        "settings.audio.test_btn": "Проверить микрофон",
        "settings.audio.test_status_recording": "Запись в течение 2 секунд...",
        "settings.audio.test_status_success": "Успешно! Записано {bytes} байт",
        "settings.audio.test_status_fail": "Запись слишком короткая или пустая",
        "settings.audio.test_status_error": "Ошибка: {error}",
        "settings.history.group": "История транскрипций",
        "settings.history.enabled": "Сохранять историю транскрипций",
        "settings.history.max": "Макс. записей:",
        "settings.history.entries_suffix": "записей",
        "settings.history.info": "История хранится локально в файле <code>~/.local/share/typr/history.json</code>. Откройте окно истории из трея, чтобы просмотреть и скопировать прошлые записи.",
        "settings.about.desc": "Голосовой ввод для Linux с использованием OpenAI и Parakeet-совместимых API",
        "settings.about.version": "Версия 0.1.0",
        
        # Test Connection Outputs
        "settings.api.test.checking": "Проверка соединения...",
        "settings.api.test.valid": "Настройки корректны.",
        "settings.api.test.valid_transcribe": "Настройки корректны: эндпоинт транскрипции доступен.",
        "settings.api.test.err_401": "Ошибка 401: API ключ отсутствует или неверен.",
        "settings.api.test.err_403": "Ошибка 403: доступ запрещен (проверьте ключ и права).",
        "settings.api.test.err_404": "Ошибка 404: эндпоинт не найден (проверьте Базовый URL).",
        "settings.api.test.err_429": "Ошибка 429: превышен лимит запросов.",
        "settings.api.test.err_5xx": "Ошибка сервера (5xx): проблема на стороне API.",
        "settings.api.test.err_generic": "Ошибка API {status}.",
        "settings.api.test.timeout": "Таймаут: сервер не ответил вовремя.",
        "settings.api.test.network_err": "Сетевая ошибка: {error}",
        "settings.api.test.conn_err": "Ошибка подключения: {error}",
        
        # Fetch Models Outputs
        "settings.fetch.no_models.title": "Нет моделей",
        "settings.fetch.no_models.msg": "Модели не найдены на этом эндпоинте",
        "settings.fetch.success.title": "Модели загружены",
        "settings.fetch.success.msg": "Найдено моделей: {count}",
        "settings.fetch.err.title": "Ошибка",
        "settings.fetch.err_404": "Эндпоинт списка моделей не найден. Проверьте Базовый URL.",
        "settings.fetch.err_api": "Ошибка API: {status}\n{text}",
        "settings.fetch.err_generic": "Не удалось получить список моделей: {error}",
    }
}


def tr(key: str, default: str = "") -> str:
    """Translate a key to system language. Falls back to default English text."""
    return TRANSLATIONS.get(lang, {}).get(key, default)
