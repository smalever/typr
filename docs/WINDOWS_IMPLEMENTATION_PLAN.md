# План реализации поддержки Windows 11

## Статус и правила исполнения

Это **план будущих изменений**. Поддержка Windows еще **не реализована**. Действующая архитектура описана в [ARCHITECTURE.md](ARCHITECTURE.md), правила документации — в [DOCUMENTATION_POLICY.md](DOCUMENTATION_POLICY.md).
- Агент выполняет только явно порученный этап; наличие плана не разрешает произвольные изменения системы, запуск GUI или commit.
- Координатор утверждает архитектуру, контракты и зависимости; исполнитель выбирает локальную реализацию в утвержденных границах.
- У каждого файла один писатель. Этапы выполняются строго последовательно с приемкой; review — в режиме read-only.
- Отчет исполнителя содержит результат, измененные пути, принятые решения, команды и результаты проверок, непроверенное и блокеры.

## Цель и non-goals

Цель: нативная работа tray-first клиента Typr на **Windows 11 x64** для проверенной minor версии Python (3.12 / поддерживаемая) с сохранением стабильности Linux (Wayland/X11). Формат поставки первого релиза: сборка wheel, чистая установка в `.venv` и запуск через `typr-gui` (или `python -m typr`).
Non-goals (требуют отдельного решения при необходимости): freezer (PyInstaller/one-dir), инсталлятор (Inno Setup/WiX), генерация `.ico`, PE metadata, цифровая подпись Authenticode / SmartScreen reputation, автозапуск, новый CI, WSL/Docker, локальный STT сервер, эмуляция ввода текста посимвольно, обход UIPI, сложный ACL framework, автомиграция данных и изменение Linux shell-скриптов.

## 1. Фактический baseline и подтвержденные пробелы

Срез кодовой базы: версия `0.4.0`.

| Область | Фактическое состояние (0.4.0) | Следствие и пробелы для Windows |
| --- | --- | --- |
| **Lifecycle** | `app.py` управляет состояниями `IDLE/RECORDING/TRANSCRIBING/TYPING/ERROR`. В `app.py:334-340` `config.save()` вызывается до `cleanup()` без перехвата `OSError`. | Выбор backend через узкий селектор. Гарантировать `cleanup()` в блоке `finally` при ошибках save/quit; чистый повторный старт backend внутри процесса. |
| **Hotkeys** | `hotkey_manager.py`: evdev на Linux. В `pyproject.toml:31` evdev указан как безусловная зависимость. Default shortcut `Ctrl+Alt+Z` переносим. | Ограничить evdev маркером `sys_platform == 'linux'`. Windows PTT реализовать через `WH_KEYBOARD_LL` (ctypes). Разбор shortcut через `QKeySequence` PortableText (single chord). |
| **Injection** | `text_injector.py`: на Linux `UInput`, Shift+Insert, текстовый backup/restore по совпадению строк, синхронные sleep/subprocess. В `app.py:126` и `i18n.py:58,202` зашит Linux-текст `/dev/uinput`. | Windows эмуляция через `SendInput` (ctypes, Ctrl+V). Асинхронный контракт с operation token. Linux блокирующие sleep/helper I/O вынести из Qt path минимально без регрессий. Адаптировать строки в i18n. |
| **Audio/HTTP** | `audio_recorder.py`: PyAudio/PortAudio, defaults PCM 16kHz mono. `transcriber.py`: общий httpx worker `QThread`. | Общий HTTP transcriber сохранить. Проверить доступность PyAudio wheels для выбранной minor Windows x64. Не блокировать Qt main thread при старте/остановке stream; обработать ошибки микрофона. |
| **Persistence** | `config.py` (`~/.config/typr`), `history.py` (`~/.local/share/typr`). Вызовы `open()` без `encoding="utf-8"` (`config.py:110,158`, `history.py:94,117`). `chmod(0600)` не эквивалентен DACL. | Сохранить Linux ТОЧНО прежние пути. На Windows использовать `%LOCALAPPDATA%\Typr`. Явный `encoding="utf-8"` везде. Guard истории после ЛЮБОЙ ошибки чтения от перезаписи. Проверка прав каталога до записи секрета. |
| **UI/Logs/Tests** | Поле Cancel UI (`settings_dialog.py:426-430`) не подключено к backend. В `settings_dialog.py:438,544` Linux-строки. `logger.py:28-44` пишет HOME при импорте; при consoleless `sys.stdout` может быть `None`. Shell-тесты читают скрипты без UTF-8. | Скрыть/отключить неработающий Cancel UI. Адаптировать Linux-строки. Изолировать пути в тестах ДО импорта модулей; скипать shell-тесты на Windows до чтения ресурсов; fallback логгера при `sys.stdout is None`. |

## 2. Архитектурные контракты и решения

### 2.1. Runtime и Win32 binding
- Вызовы Win32 через стандартную библиотеку `ctypes` (`user32.dll`, `kernel32.dll`) без сторонних библиотек и plugin framework.
- Компактный контроль ABI: pointer-sized типы (`LRESULT`, `WPARAM`, `LPARAM`, `HHOOK`, `ULONG_PTR`), `WINFUNCTYPE`, явные `argtypes` и `restype`.
- Размер полной структуры `INPUT` (40 байт, alignment 8 байт на Windows x64 по [SendInput docs](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput)).
- Централизованный выбор реализации через платформенный селектор и единый модуль `src/typr/platforms/paths.py`.

### 2.2. Global Hotkey (Windows PTT)
- Низкоуровневый хук `WH_KEYBOARD_LL` в worker thread с нативным message loop (`GetMessageW`/`DispatchMessageW`) по [LowLevelKeyboardProc docs](https://learn.microsoft.com/en-us/windows/win32/winmsg/lowlevelkeyboardproc).
- Хук передает queued сигналы в Qt main thread и немедленно вызывает `CallNextHookEx`; в callback запрещены I/O, sleep и блокировки.
- Autorepeat флага в хуке нет: duplicate keydown фильтруются через pressed set (не запуская повторную запись).
- Один start при target down + required modifiers, дополнительные modifiers допускаются; stop при target up или утрате любого required modifier.
- Игнорируются ВСЕ `LLKHF_INJECTED` события (минимальное решение и документированное ограничение).
- Раздельный физический учет left/right клавиш (не обещая Linux left/right как уже имеющееся в коде).
- Тесты обработки AltGr, системных сообщений (`WM_SYSKEYDOWN/WM_SYSKEYUP`) и известных ошибок хука.
- Сброс состояния PTT при смене shortcut или session reset останавливает/отменяет запись; silent hook removal со стороны ОС обнаружить не обещаем.
- Разбор комбинации клавиш через единый `QKeySequence` PortableText (single chord) для синхронизации между UI и backend; удержание ссылки на callback до корректного `UnhookWindowsHookEx` и завершения message loop.

### 2.3. Вставка текста и Clipboard Policy
- Асинхронный контракт вставки: `request_injection`, `injection_completed`, `injection_failed` с operation token; один active pipeline.
- Все обращения к Qt clipboard / QMimeData и их cleanup выполняются строго в Qt main thread.
- Отмена операции при shutdown и игнорирование late callbacks старых операций.
- Состояние `TYPING` активно до завершения `SendInput`; обязательна проверка фактически отправленного числа событий (count `SendInput`).
- Успех `SendInput` означает отправку событий, а не подтверждение вставки приложением; при успехе или ошибке вставки транскрипция сохраняется в history (если включена).
- Windows clipboard policy: Typr помещает текст в буфер обмена и отправляет Ctrl+V; текст остается в буфере (по аналогии с Copy).
- Typr не очищает и не восстанавливает буфер после ошибки/shutdown и не затирает последующее внешнее копирование пользователем.
- Гарантий race-free paste нет: внешнее копирование между публикацией и paste может изменить результат (restore race отсутствует из-за отказа от restore).
- До публикации выполняется ограниченное ожидание по таймеру освобождения модификаторов (таймаут -> ошибка без принудительного отпускания клавиш).
- При частичном сбое `SendInput` выполняется keyup cleanup собственных synthetic клавиш; неподдерживаемые цели: elevated target, secure desktop/UAC.
- Поведение буфера документируется в Settings и README; настройка restore для Windows не добавляется (на Linux прежнее поведение сохраняется).
- Существующую общую задержку уведомления не выдавать за гарантию restore.
- Вынос блокирующих вызовов Linux sleep/helper I/O из Qt main thread минимально необходимым образом без регрессий.

### 2.4. Персистентность и безопасность
- На Linux сохраняются ТОЧНО прежние пути (`~/.config/typr`, `~/.local/share/typr`), без обещаний нового XDG support.
- На Windows используется каталог `%LOCALAPPDATA%\Typr` (`config.json`, `history.json`, `logs\typr.log`).
- Сохраняются config tolerant loading, запрет overwrite после ошибки чтения, atomic replace и backup (`.json.bak`).
- Privacy: config, временные файлы и backup, содержащие API key, создаются с private permissions (не писать в shared/cwd; на Linux сохранить `0600`, на Windows `chmod` не эквивалентен DACL).
- Windows private profile ACL не гарантируется в нестандартном окружении: проверка доверенного каталога и наследуемых прав до записи API key (ошибка при небезопасной среде).
- При ошибке открытия logs или разрешении путей выдается понятная диагностика без silent fallback.
- Явный `encoding="utf-8"` для всех вызовов `open()` (конфигурация, история, тесты, чтение shell-ресурсов).
- Защита истории от перезаписи после ЛЮБОЙ ошибки чтения (persistence safety guard).
- Логирование: consoleless fallback при `sys.stdout is None` (`pythonw` / GUI launcher).
- Жизненный цикл: гарантированный вызов `cleanup()` в блоке `finally` при выходе из приложения даже при ошибках `config.save()` (`OSError`).

### 2.5. Audio и Single-Instance
- Сохраняются общий `PyAudio` pipeline (PCM 16kHz mono defaults, не жесткая характеристика config) и общий HTTP transcriber.
- Проверка доступности готовых wheels PyAudio для выбранной minor версии Windows x64.
- Неблокирующий lifecycle: устранить вызовы open/stop/join из Qt main thread.
- Локальные state tests: no-device, privacy, default, device removal/recovery, shutdown во время recording/transcribing/typing; cleanup queued work.
- Тесты быстрого press/release ВО ВРЕМЯ открытия stream, delayed stop/close/error/shutdown.
- Запуск нескольких экземпляров регламентируется пользовательской инструкцией (системный mutex отложен); чистый повторный запуск backend внутри процесса.

## 3. Последовательные этапы реализации

### Этап 1 — Платформенные границы, пути, persistence и изоляция тестов
- Область записи: `pyproject.toml`, `src/typr/platforms/__init__.py`, `src/typr/platforms/paths.py`.
- Область записи (core): `src/typr/config.py`, `src/typr/core/history.py`, `src/typr/utils/logger.py`.
- Область записи (tests): `tests/conftest.py`, `tests/test_paths.py`, `tests/test_config.py`, `tests/test_history.py`, `tests/test_installer.py`, `tests/test_uninstaller.py`.
- Документация: `docs/ARCHITECTURE.md`, этот план (companions по `docs/DOCUMENTATION_POLICY.md`).
- Задачи: ограничить evdev маркером `sys_platform == 'linux'`; единый `paths.py` (прежние пути для Linux, `%LOCALAPPDATA%\Typr` для Windows).
- Задачи: проверка прав каталога до записи секрета; явный `encoding="utf-8"` при `open()`; guard истории после ЛЮБОЙ ошибки чтения.
- Задачи: consoleless fallback в `logger.py`; изоляция путей в тестах ДО импорта модулей; ранний skip shell-тестов на Windows (чтение в UTF-8).
- Критерии проверки (Gate): чистый импорт без evdev на Windows; прохождение тестов persistence, путей и logger в изолированном окружении.

### Этап 2 — Windows PTT backend (ctypes WH_KEYBOARD_LL)
- Область записи: файлы Windows hotkey в `src/typr/platforms/` (например, `windows_hotkeys.py`), селектор платформ, `src/typr/core/hotkey_manager.py`.
- Область записи (tests): `tests/test_windows_hotkeys.py`, `tests/test_hotkey_manager.py`.
- Документация: `docs/ARCHITECTURE.md`, этот план.
- Задачи: хук `WH_KEYBOARD_LL` с message loop в worker thread через ctypes; структуры ABI с pointer-sized типами.
- Задачи: логика PTT (start по down, stop по up, pressed set для duplicate down, игнорирование всех injected, физические left/right).
- Задачи: тесты AltGr и системных сообщений; сброс при смене shortcut или session reset; разбор single-chord PortableText; идемпотентный cleanup.
- Критерии проверки (Gate): unit-тесты с моками Win32 API (keydown/keyup, left/right, duplicate down, injected, unhook); отсутствие регрессий Linux evdev.

### Этап 3 — Неблокирующая вставка и clipboard-политика (SendInput)
- Область записи: файлы Windows text injector в `src/typr/platforms/` (например, `windows_injector.py`), селектор платформ, `src/typr/core/text_injector.py`, `src/typr/app.py`.
- Область записи (tests): `tests/test_windows_text_injector.py`, `tests/test_text_injector.py`, `tests/test_app.py`.
- Документация: `docs/ARCHITECTURE.md`, этот план.
- Задачи: асинхронный контракт с operation token (`request_injection`, `injection_completed`, `injection_failed`).
- Задачи: эмуляция Ctrl+V через `SendInput` (ctypes, INPUT 40 байт); публикация текста в Qt main thread.
- Задачи: bounded таймер ожидания отпускания модификаторов до публикации; cleanup синтетических keyup при частичной отправке; отказ от restore буфера.
- Задачи: вынос блокирующих вызовов Linux sleep/helper I/O из Qt main thread минимально необходимым образом без изменения поведения.
- Критерии проверки (Gate): тесты контракта, таймаута модификаторов, partial SendInput cleanup, late callback cancellation, регресс Linux helper.

### Этап 4 — Audio lifecycle, UI адаптация, запуск из venv и метаданные пакета
- Область записи: `src/typr/core/audio_recorder.py`, `src/typr/app.py`, `src/typr/__main__.py`, `src/typr/ui/settings_dialog.py`, `src/typr/utils/i18n.py`, `pyproject.toml`.
- Область записи (tests): `tests/test_audio_recorder.py`, `tests/test_app.py`, `tests/test_settings_dialog.py`.
- Документация: `README.md`, `docs/DEVELOPMENT.md`, `docs/ARCHITECTURE.md`, этот план.
- Задачи: неблокирующий audio lifecycle (устранить open/stop/join из Qt main thread); тесты быстрого press/release при открытии, delayed stop/close/error/shutdown.
- Задачи: адаптация Linux-строк в `settings_dialog.py:438,544` и `app.py:126` через i18n; скрытие/отключение Cancel UI без нового workflow.
- Задачи: подсказка о буфере обмена в Settings; гарантированный `cleanup()` в `finally` при выходе из `app.py`; Windows classifier в `pyproject.toml` (без bump).
- Критерии проверки (Gate): тесты UI, audio и app; чистая сборка wheel (`python -m build`), `pip check`, установка в `.venv` и запуск `typr-gui` без консоли из cwd с Unicode.

## 4. Чеклист верификации и критерий готовности

### 4.1. Автоматизированные проверки
- Чистая сборка `python -m build`, чистая установка wheel в `.venv`, `pip check`.
- Полный applicable `pytest` на обеих ОС (с пропуском shell-тестов на Windows); `ruff check` для измененных файлов Python.

### 4.2. Натурный Smoke Checklist
- Windows 11: старт `typr-gui` без консоли из cwd с Unicode/пробелами в пути; tray/settings/history; дефолтный `Ctrl+Alt+Z`.
- Windows 11: PTT запись (быстрый клик, длинное удержание, игнор duplicate down, lock/unlock, RU/EN раскладки, AltGr, release модификаторов).
- Windows 11: вставка Unicode через Ctrl+V в обычные приложения; текст в буфере, транскрипция в истории; корректный выход без зависших потоков/хуков.
- Linux: базовый нативный регресс Wayland и X11 (PTT через evdev, uinput вставка, восстановление через wl-copy/xclip, shell tests).

### 4.3. Критерий готовности
- Поддержка принимается только если согласованные contracts реализованы, applicable automation и desktop smoke пройдены на обеих ОС без прав admin.
- Пользовательские данные и секреты сохранены, UI остается отзывчивым, непроверенное честно указано в отчете.
- Hardware/GUI проверки требуют отдельного разрешения, тестового endpoint и фиктивных секретов.

## 5. Отложенные задачи (Deferred)

Следующие задачи не входят в минимальный объем первого релиза и требуют отдельного решения при необходимости:
- Standalone сборка через freezer (PyInstaller/one-dir bundle) и бандлинг нативных библиотек Qt/PortAudio.
- Windows per-user installer (Inno Setup / WiX) и автоматизация автозапуска в реестре/Startup.
- Иконка `.ico`, PE metadata (file/product version), подпись Authenticode и SmartScreen reputation.
- Полноценный snapshot и надежный restore сложных форматов буфера обмена (HTML/RTF/OLE) с учетом TOCTOU.
- Системный межпроцессный мьютекс (`CreateMutexW`) для блокировки повторного запуска.
- Полноценный workflow отмены записи (Cancel hotkey).
- Настройка матрицы Windows в GitHub Actions CI.
