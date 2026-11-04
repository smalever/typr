# План реализации поддержки Windows 11

## Статус и правила исполнения

**Текущий статус (2026-11-04): этапы 1–5 реализованы; автоматизированные/package/import
gates 1–7 этапа 5 успешны, native gate 8 остается OPEN.** Миграция с PyAudio на
sounddevice завершена по утвержденному lifecycle. Независимое read-only general-deep
review не обнаружило подтвержденных дефектов; независимый targeted suite — 67 passed.
Финальный full applicable suite — **256 passed, 2 skipped**; clean full install,
`pip check` и installed imports успешны на существующем CPython 3.15.2 Windows x64.
Новый Python не устанавливался; GUI и native audio не запускались.
Результаты этапов 1–4 ниже — **исторические срезы**, включая 232 passed / 2 skipped
и прежний blocker PyAudio этапа 4; они не являются sounddevice evidence.
Blocker packaging/import на 3.15.2 снят этапом 5, но это не полная релизная квалификация minor.
Поддержка Windows приложения еще **не готова**. Действующая архитектура
описана в [ARCHITECTURE.md](ARCHITECTURE.md), правила документации — в [DOCUMENTATION_POLICY.md](DOCUMENTATION_POLICY.md).
- Агент выполняет только явно порученный этап; наличие плана не разрешает произвольные изменения системы, запуск GUI или commit.
- Координатор утверждает архитектуру, контракты и зависимости; исполнитель выбирает локальную реализацию в утвержденных границах.
- У каждого файла один писатель. Этапы выполняются строго последовательно с приемкой; review — в режиме read-only.
- Отчет исполнителя содержит результат, измененные пути, принятые решения, команды и результаты проверок, непроверенное и блокеры.

## Цель и non-goals

Цель: нативная работа tray-first клиента Typr на **Windows 11 x64** для существующей целевой minor версии Python (**CPython 3.15.2 x64**, packaging/import verified, native/release acceptance pending; установка Python 3.12 не требуется) с сохранением стабильности Linux (Wayland/X11). Формат поставки первого релиза: сборка wheel, чистая установка в `.venv` без `--no-deps` и заглушек, запуск через `typr-gui` (или `python -m typr`).
Non-goals (требуют отдельного решения при необходимости): freezer (PyInstaller/one-dir), инсталлятор (Inno Setup/WiX), генерация `.ico`, PE metadata, цифровая подпись Authenticode / SmartScreen reputation, автозапуск, новый CI, WSL/Docker, локальный STT сервер, эмуляция ввода текста посимвольно, обход UIPI, сложный ACL framework, автомиграция данных и изменение Linux shell-скриптов (за исключением узкой адаптации проверок audio-зависимостей и импортов в `install.sh` под sounddevice).

## 1. Исторический baseline до этапов 1–5 и исходные пробелы

Срез кодовой базы: версия `0.4.0`.

| Область | Фактическое состояние (0.4.0) | Следствие и пробелы для Windows |
| --- | --- | --- |
| **Lifecycle** | `app.py` управляет состояниями `IDLE/RECORDING/TRANSCRIBING/TYPING/ERROR`. В `app.py:334-340` `config.save()` вызывается до `cleanup()` без перехвата `OSError`. | Выбор backend через узкий селектор. Гарантировать `cleanup()` в блоке `finally` при ошибках save/quit; чистый повторный старт backend внутри процесса. |
| **Hotkeys** | `hotkey_manager.py`: evdev на Linux. В `pyproject.toml:31` evdev указан как безусловная зависимость. Default shortcut `Ctrl+Alt+Z` переносим. | Ограничить evdev маркером `sys_platform == 'linux'`. Windows PTT реализовать через `WH_KEYBOARD_LL` (ctypes). Разбор shortcut через `QKeySequence` PortableText (single chord). |
| **Injection** | `text_injector.py`: на Linux `UInput`, Shift+Insert, текстовый backup/restore по совпадению строк, синхронные sleep/subprocess. В `app.py:126` и `i18n.py:58,202` зашит Linux-текст `/dev/uinput`. | Windows эмуляция через `SendInput` (ctypes, Ctrl+V). Асинхронный контракт с operation token. Linux блокирующие sleep/helper I/O вынести из Qt path минимально без регрессий. Адаптировать строки в i18n. |
| **Audio/HTTP** | Исходный baseline: `audio_recorder.py` на PyAudio/PortAudio, PCM 16kHz mono; `transcriber.py` на httpx. На этапе 4 подтверждено отсутствие wheels PyAudio для CPython 3.15.2 x64. | Общий HTTP transcriber сохранить. Координатором утверждена миграция `PyAudio -> sounddevice` (0.5.6) с blocking `RawInputStream` в worker thread и явным управлением PortAudio lifecycle. Не блокировать Qt main thread; нефатальный overflow; clean full install без stubs. |
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

### 2.5. Audio и Single-Instance (Архитектурный контракт sounddevice)
- **Исторический контекст PyAudio и новое решение:** исходно планировался `PyAudio`, однако отсутствие бинарных wheels под CPython 3.15.2 Windows x64 заблокировало package gates. Утверждена миграция на `sounddevice` с зависимостью `cffi`. Общий HTTP transcriber (`transcriber.py`) сохраняется без изменений.
- **Потоковая модель и stream type:** использование исключительно блокирующего `RawInputStream` строго внутри существующего worker рекордера (без добавления сторонних классов потоков). В первой миграции отказ от callbacks в пользу детерминированного blocking read в цикле worker.
- **Формат данных и отсутствие NumPy:** сохраняются текущий асинхронный фасад `AudioRecorder` и формирование PCM 16-bit WAV стандартными библиотеками Python (`wave`, `struct`). Параметры `sample_rate` и `channels` берутся из `config` (значения 16 kHz и mono являются defaults конфигурации, а не жестким форматом). Вызов `RawInputStream.read(...)` возвращает кортеж `(buffer, overflowed)`; аудио-данные преобразуются через `bytes(buffer)` без требования предварительного выделения буфера; зависимость от `numpy` не добавляется.
- **Селекция устройств и defaults:** snapshot конфигурации при старте, сопоставление по имени устройства (`exact device name`); детерминированный fallback на системный default применяется исключительно при ненайденном выбранном имени устройства с информативным логированием. Любые ошибки перечисления/запроса (`query_devices`) или открытия потока (`RawInputStream`) возвращаются как явные асинхронные ошибки (сигналы `devices_error`, `recording_error`), без произвольного fallback на default при сбоях обращения к оборудованию.
- **Политика переполнения (overflow):** флаг `overflowed`, возвращаемый `RawInputStream.read(...)`, обрабатывается нефатально — логируется предупреждение, накопление сэмпла продолжается.
- **Сериализация PortAudio в процессе:** строгая process-global worker-only сериализация ВСЕХ вызовов PortAudio API (перечисление устройств, инициализация, open, read, stop, close, termination) под общим локом. Никакие PortAudio операции не выполняются в Qt main thread.
- **Утвержденное владение init/terminate/error/atexit:** единственный `SoundDeviceOwner` в `_sounddevice_backend.py` загружает модуль через importlib только в worker под общим lock. Ссылка на module сохраняется локально до `exec_module`, включая failed import; зарегистрированный `_exit_handler` снимается через `atexit.unregister` в `finally`, в том числе при ошибке импорта. Успешно загруженный module сохраняется owner для следующих сессий; failed import удаляется из `sys.modules` только если там тот же module. Повторная сессия вызывает `_initialize()`, каждая попытка завершается vetted `_exit_handler()` в worker, включая hidden init success перед ошибкой восстановления stderr. При finalization failure owner помечается broken (poison), дальнейшие операции запрещены до перезапуска. Unmanaged import и main-thread session отвергаются. Top-level `import sounddevice`, monkeypatch `_initialized` и native atexit teardown запрещены.
- **Диагностика ошибок:** вызовы `stop()`, `abort()`, `close()` обязаны явно диагностировать и логировать возникающие исключения; запрещено использовать silent `ignore_errors` defaults.
- **Expert API и версии:** утверждены `sounddevice==0.5.6` (проверенный private finalizer), `cffi>=2.1.1,<3` (binary floor целевого cp315 Windows), PortAudio `>=19.6.0,<20` с runtime version check. Проверены distribution/module version и failure paths; собственный init counter не вводится. Изменение pin требует повторной проверки source lifecycle.
- **Cleanup predicates и shutdown barrier:** сохранение предикатов фактического завершения потоков (`is_cleanup_complete() -> bool`) и общего неблокирующего shutdown barrier в `TyprApp` (основной audio worker + отставленные worker-потоки Settings + text injector).
- **Неизменность контракта вставки текста:** token identity, acceptance semantics и подавление late results остаются неизменными; функциональных изменений в `src/typr/core/text_injector.py` и `src/typr/app.py` не планируется.
- **Локальные state tests:** no-device, privacy, default, device removal/recovery, shutdown во время recording/transcribing/typing; тесты быстрого press/release во время открытия stream, delayed stop/close/error/shutdown.
- **Single-instance:** запуск нескольких экземпляров приложения регламентируется пользовательской инструкцией (системный mutex отложен); изоляция contention между основным рекордером и временными экземплярами микрофонного теста Settings.

## 3. Последовательные этапы реализации

### Этап 1 — Платформенные границы, пути, persistence и изоляция тестов

**Статус (2026-11-03): реализация завершена; приемка Linux остается открытой.**
Добавлен узкий read-only `platforms/windows_security.py` для owner/DACL, без
изменения системных ACL. Уникальные private tmp и backup заменяются атомарно;
ошибки чтения config/history блокируют последующую запись. Обновлены paths,
UTF-8, consoleless logger, ранняя изоляция tests и skip shell tests.
После независимого review исправлены два дефекта: JSON сериализуется с
`ensure_ascii=True` и явным UTF-8 для безопасного round-trip lone surrogates;
`RecursionError` при чтении глубоко вложенного JSON переводит config/history
в `_load_failed` без последующей перезаписи. Четыре regression-теста сначала
воспроизвели ошибки, затем прошли после исправления (config load/save,
history load/save/add и сохранность оригиналов при глубине 100000 массивов).

Проверено на Windows x64 / доступном Python 3.15.2: чистый импорт платформенных
модулей/config/history без evdev; targeted persistence/paths/logger suite
(`27 passed, 2 skipped`: shell modules skipped до чтения ресурсов);
нативная проверка DACL временного каталога и отказ вне профиля; scoped ruff;
sdist и wheel (`build --no-isolation`, без установки приложения).
Это не gate импорта `typr.app`/GUI: он зависит от следующих этапов.
Проектная `.venv` оказалась Linux-only с недоступным здесь interpreter, поэтому
проверки выполнялись отдельным временным Windows venv вне репозитория.
Toolchain: `C:\Users\smale\AppData\Local\Temp\kilo\typr-stage1-venv\Scripts\python.exe`
(ruff в том же `Scripts`); повторные targeted pytest, scoped ruff и build
актуального исправления прошли. Сборки находятся в
`C:\Users\smale\AppData\Local\Temp\kilo\typr-stage1-dist`.

Открытые gates: Linux persistence/permissions и shell regressions на Linux;
выбранная релизная minor Python (3.12 / согласованная), чистая установка wheel
и `pip check` полного приложения. Этапы 3–4, полный applicable pytest обеих ОС
и все desktop/hardware smoke не выполнялись и не объявляются готовыми.

- Область записи: `pyproject.toml`, `src/typr/platforms/__init__.py`, `src/typr/platforms/paths.py`.
- Область записи (core): `src/typr/config.py`, `src/typr/core/history.py`, `src/typr/utils/logger.py`.
- Область записи (tests): `tests/conftest.py`, `tests/test_paths.py`, `tests/test_config.py`, `tests/test_history.py`, `tests/test_installer.py`, `tests/test_uninstaller.py`.
- Документация: `docs/ARCHITECTURE.md`, этот план (companions по `docs/DOCUMENTATION_POLICY.md`).
- Задачи: ограничить evdev маркером `sys_platform == 'linux'`; единый `paths.py` (прежние пути для Linux, `%LOCALAPPDATA%\Typr` для Windows).
- Задачи: проверка прав каталога до записи секрета; явный `encoding="utf-8"` при `open()`; guard истории после ЛЮБОЙ ошибки чтения.
- Задачи: consoleless fallback в `logger.py`; изоляция путей в тестах ДО импорта модулей; ранний skip shell-тестов на Windows (чтение в UTF-8).
- Критерии проверки (Gate): чистый импорт без evdev на Windows; прохождение тестов persistence, путей и logger в изолированном окружении.

### Этап 2 — Windows PTT backend (ctypes WH_KEYBOARD_LL)

**Статус (2026-11-03): реализация и mocked unit gates завершены; desktop и
нативный Linux regression остаются открытыми.**

Добавлены lazy selector, QObject facade, общий strict single-chord PortableText
parser и Windows worker с pointer-sized ctypes ABI, native message queue,
WH_KEYBOARD_LL и скрытым окном WTS session notifications. Start/stop/reset,
left/right, duplicate down, injected/AltGr и WM_SYSKEYDOWN/UP проверены без
настоящих hooks/session registration. Update/reset/quit передаются worker
private messages; Qt relay фильтрует worker registration и shortcut generation. Callback всегда пересылает
событие дальше, references удерживаются до unhook/выхода потока. Silent hook
removal detection не обещается. Initialize ожидает readiness максимум 100 мс;
timeout отменяет startup и возвращает False с ошибкой. Cleanup не делает join;
restart допускается после фактического завершения предыдущего worker.

Linux evdev read/select/hotplug перенесен в узкий backend без замены механизма
ввода; update/reset выполняются через worker control queue, закрытие devices —
в worker finally, без прежнего секундного join UI. Fake evdev тест проверяет
PTT/repeat/update/reset/hotplug; это не замена нативного Linux gate.
Settings PTT load/save использует PortableText и общий parser до изменения
config; invalid input не сохраняется и не закрывает диалог (RU/EN diagnostic).
Другие UI/audio/injection изменения этапов 3–4 не выполнялись.

Проверено Windows x64 / временный Python 3.15.2 toolchain этапа 1:
`57 passed, 2 skipped` для новых hotkey tests и полного targeted stage-1 suite
(paths/config/history/logger/installer/uninstaller; shell modules skipped).
Scoped ruff всех измененных Python-файлов прошел. `python -m build --no-isolation`
создал sdist/wheel 0.4.0 в Temp `typr-stage2-dist`, без установки приложения.
В toolchain добавлен httpx 0.28.1 для no-GUI Settings import/test.
Из-за WinError32 при scandir корня pytest запущен из Temp с absolute PYTHONPATH,
`--rootdir=<repo>/tests --confcutdir=<repo>/tests --import-mode=importlib
-p no:cacheprovider`; Git status/diff в этом окружении заблокированы directory
access error. Проверки не устанавливают реальный hook и не меняют desktop.
Открыты все Linux gates этапа 1, нативный evdev regression, Windows desktop smoke,
релизная minor Python, clean install/pip check и этапы 3–4.

После независимого review исправлены три подтвержденных дефекта: потеря fatal
GetMessageW error между post и consumption WM_UPDATE, phantom queued события
предыдущего worker после restart и принятие `Ctrl+Z, ` из-за lossy Qt parser.
Worker registration теперь отделена от shortcut generation; ошибки текущей
registration (включая unhook/WTS/window/class cleanup) не фильтруются shortcut
generation, старые PTT по-прежнему отбрасываются. Новый worker инвалидирует все
queued события прошлого; initialize живой регистрации остается идемпотентным.
Два deterministic FakeWin32/QCoreApplication race tests управляют порядком через
threading.Event/очередь, без sleep/GUI/native registration; также проверены final
cleanup errors после cleanup generation change, trailing/empty chords и comma
target как явно unsupported OEM key (не как разделитель). Проверка допустимых
non-letter keys выявила canonical PortableText `Del`/`Ins`: key map исправлен
для ранее заявленных Delete/Insert. Scoped ruff и build повторены после правок.

- Область записи: файлы Windows hotkey в `src/typr/platforms/` (например, `windows_hotkeys.py`), селектор платформ, `src/typr/core/hotkey_manager.py`.
- Область записи (tests): `tests/test_windows_hotkeys.py`, `tests/test_hotkey_manager.py`.
- Документация: `docs/ARCHITECTURE.md`, этот план.
- Задачи: хук `WH_KEYBOARD_LL` с message loop в worker thread через ctypes; структуры ABI с pointer-sized типами.
- Задачи: логика PTT (start по down, stop по up, pressed set для duplicate down, игнорирование всех injected, физические left/right).
- Задачи: тесты AltGr и системных сообщений; сброс при смене shortcut или session reset; разбор single-chord PortableText; идемпотентный cleanup.
- Критерии проверки (Gate): unit-тесты с моками Win32 API (keydown/keyup, left/right, duplicate down, injected, unhook); отсутствие регрессий Linux evdev.

### Этап 3 — Неблокирующая вставка и clipboard-политика (SendInput)

**Статус (2026-11-03): реализация, автоматизированные проверки и независимое
ревью завершены; Linux native regression и desktop smoke открыты.**

QObject facade использует `request_injection(text, token) -> bool`,
`injection_completed(token)` / `injection_failed(token, reason)`. Token — уникальный
caller-generated object, сравнение по identity; app устанавливает его до request.
Bool — acceptance; busy дает queued failure, shutdown terminal и подавляет все callbacks.
Kickoff async, backend result queued, внутренний serial отбрасывает late completion.
History фиксируется до injection, TYPING — до отправки/ошибки. Quit инвалидирует
injection до config.save и защищает остальной cleanup через finally.

Windows: полная INPUT union / explicit ctypes signatures, bounded paste-key timer,
main Qt thread clipboard, точный SendInput count и prefix-based synthetic keyup cleanup.
Никаких clear/restore, даже error/shutdown. README clipboard policy добавлена сейчас;
**Settings/i18n подсказка и адаптация Linux-строк остаются этапу 4**.
Linux: один worker владеет initialization/uinput/helpers/restore deadline и cleanup;
Qt не выполняет sleep/helper I/O/join. Сохранены Shift+Insert, backend selection,
text comparison restore и helper ownership; bounded pipe/read/cleanup, cancellation
между шагами и диагностика ошибок. Подробный контракт — в ARCHITECTURE.md.

Независимое review выявило и исправлено: (P2) удерживаемая физическая V не входила
в ожидание — теперь V проверяется вместе с modifiers до публикации, без принудительного
keyup; (P2) xclip/xsel отделяли owner от Popen — добавлены -quiet/--nodetach по upstream
man pages, точные commands и cleanup current/restored owner покрыты тестами. Xclip clear
без backup использует managed foreground owner пустой строки.
Архитектурная доработка: `is_cleanup_complete() -> bool` у facade/backend и неблокирующий
QTimer barrier в app. Quit после save/finally ждет фактического завершения Linux worker
после session.close, даже при save failure. Windows/no backend immediate; повторный quit
идемпотентен. Нет UI join или принудительного timeout: непрерываемый device syscall может
задержать выход. Event regression удерживает worker close и проверяет responsive Qt,
отсутствие раннего quit и ровно один окончательный quit.

Финальный full applicable suite на Windows — **157 passed, 2 skipped** (shell
modules skipped); targeted mocked QCoreApplication tests — **46 passed**, также
повторены три раза без ошибок. Использован временный toolchain этапа 1
(Python 3.15.2 / Qt и PyQt 6.12.0), без GUI, native clipboard, SendInput и hardware.
Scoped ruff и `git diff --check` прошли; `python -m build --no-isolation` создал
sdist/wheel 0.4.0 в Temp `typr-stage3-dist`. Проверено включение исправленных
backends и cleanup barrier в wheel, чистый Windows import без evdev.
Повторное независимое read-only ревью исправлений: подтвержденных дефектов нет,
оба P2 закрыты; shutdown barrier принят. Установка wheel и `pip check` не выполнялись.
Linux native gates, релизная minor Python и stage-4 audio/UI/package не выполнялись.

- Область записи: файлы Windows text injector в `src/typr/platforms/` (например, `windows_injector.py`), селектор платформ, `src/typr/core/text_injector.py`, `src/typr/app.py`.
- Область записи (tests): `tests/test_windows_text_injector.py`, `tests/test_text_injector.py`, `tests/test_app.py`.
- Документация: `docs/ARCHITECTURE.md`, этот план.
- Задачи: асинхронный контракт с operation token (`request_injection`, `injection_completed`, `injection_failed`).
- Задачи: эмуляция Ctrl+V через `SendInput` (ctypes, INPUT 40 байт); публикация текста в Qt main thread.
- Задачи: bounded таймер ожидания отпускания модификаторов до публикации; cleanup синтетических keyup при частичной отправке; отказ от restore буфера.
- Задачи: вынос блокирующих вызовов Linux sleep/helper I/O из Qt main thread минимально необходимым образом без изменения поведения.
- Критерии проверки (Gate): тесты контракта, таймаута модификаторов, partial SendInput cleanup, late callback cancellation, регресс Linux helper.

### Этап 4 — Audio lifecycle, UI адаптация, запуск из venv и метаданные пакета (Историческая реализация PyAudio)

**Статус (2026-11-03): историческая реализация на базе PyAudio завершена, independent review пройдено;
доступная автоматизация завершена (232 passed, 2 skipped), однако clean full install/import gates
заблокированы отсутствием wheels PyAudio для Python 3.15.2.**
*Примечание координатора:* Данные проверки, таблицы и команды ниже относятся строго
к исторической реализации на базе библиотеки PyAudio. Они сохраняются в неизменном виде как
историческое свидетельство и НЕ являются проверкой или доказательством работоспособности sounddevice.
Принятый AudioRecorder использует worker-owned PortAudio с общей для процесса
сериализацией lifecycle PortAudio, async stop/results/device enumeration и terminal
nonblocking cleanup с actual-exit predicates. Settings refresh и microphone test
переведены на эти API; выбранное устройство фиксируется snapshot config. References
временных recorder удерживаются до actual exit; hide/reopen/shutdown отменяют timer
и результаты. Lazy Settings включён в общий audio+injection shutdown barrier.
Entry point finally использует тот же controller barrier при ошибках start/exec.
Cancel UI скрыт; добавлены RU/EN Windows notification/clipboard/hotkey/history
подсказки, crossplatform About/description и Windows classifier без version bump.
README/Development содержат инструкции venv/consoleless launcher/Unicode cwd.

Независимое review и повторное review исправления завершены: P1 process-global
PortAudio fix принят; предшествующий targeted результат — **125 passed** (данные
завершенной приемки, не новый запуск этой verification). Unit tests используют
fake widgets/method isolation/QCoreApplication без QApplication, GUI, hooks,
clipboard, microphone или endpoint. Production-заглушки зависимостей не добавлялись.

#### Финальная verification этапа 4 (2026-11-03)

Среда: Windows 11 x64 (`10.0.26300`, AMD64), CPython **3.15.2**, MSC v.1951;
Qt/PyQt **6.12.0**, pytest **9.2.0**, ruff **0.17.3**, build **1.6.1**,
hatchling **1.33.0**. Проектная `.venv` Linux-only: `.venv/Scripts/python.exe`
отсутствует. Использован существующий внешний toolchain:
`C:\Users\smale\AppData\Local\Temp\kilo\typr-stage1-venv\Scripts\python.exe`.
Он не содержит pip и не изменялся. `py --list-paths` недоступен (`py` не найден);
`uv python list --only-installed` показывает только 3.15.2. Python 3.12 не найден,
новый interpreter не скачивался. Релизная minor остается не принятой: наличие
cp312 wheel ниже не заменяет полный clean install и native smoke на Python 3.12.

Для воспроизведения PowerShell-команд ниже:

```powershell
$repo = 'D:\@home\sma\programming\typr'
$tool = 'C:\Users\smale\AppData\Local\Temp\kilo\typr-stage1-venv\Scripts\python.exe'
$dist = 'C:\Users\smale\AppData\Local\Temp\kilo\typr-stage4-verification-dist'
$verify = 'C:\Users\smale\AppData\Local\Temp\kilo\typr-stage4-verify-2kn0uv11'
$clean = "$verify\clean-venv\Scripts\python.exe"
$env:PYTHONDONTWRITEBYTECODE = '1'
```

Все outputs/новый venv находятся вне repo; перед созданием проверено существование
родителя `Test-Path -LiteralPath 'C:\Users\smale\AppData\Local\Temp\kilo'`.
`$verify` получен через `tempfile.mkdtemp(prefix='typr-stage4-verify-', dir=...)`,
venv создан `$tool` через `venv.create(root/'clean-venv', with_pip=True)`;
новый pip — **26.2.2**. Existing venv/system dependencies не менялись.

| Проверка | Актуальный результат |
| --- | --- |
| Full applicable pytest, один запуск | **232 passed, 2 skipped**, 1.74 s. Shell modules skipped на Windows; не Linux gate. |
| Scoped ruff всех измененных Python, включая untracked tests | **All checks passed**. |
| `git diff --check` | Успех; только предупреждения Git о будущей LF→CRLF конвертации. |
| `& $tool -m build --outdir $dist` | Успех **с isolation**: sdist и wheel 0.4.0, wheel построен из sdist; оба isolated env использовали hatchling 1.33.0. No-isolation fallback не требовался. |
| PyAudio binary cp312/win_amd64 download | **Успех**: `PyAudio-0.2.14-cp312-cp312-win_amd64.whl` (164 kB), без установки. |
| PyAudio binary cp315/win_amd64 download | **Нет wheel**: `No matching distribution found for PyAudio`. |
| Full wheel install в новом `$verify\clean-venv` | **Заблокирован** отсутствием PyAudio wheel для 3.15.2; source build не выполнялся. |
| Диагностическая неполная установка wheel | Установлен `typr==0.4.0` с `--no-deps`, затем все non-Linux runtime dependencies кроме PyAudio; это **не** успешный full install. |
| `& $clean -m pip check` | **FAIL**: `typr 0.4.0 requires pyaudio, which is not installed.` Не объявляется успешной проверкой полного package. |
| Installed imports `typr.app`, `typr.__main__` | Обе попытки **FAIL / blocked**: `ModuleNotFoundError: No module named 'pyaudio'`; без подмены PyAudio/evdev. |
| Installed metadata/launcher | Успех: версия 0.4.0, `console_scripts: typr`, `gui_scripts: typr-gui`, оба → `typr.__main__:main`; Windows 11 classifier; evdev с Linux-only marker и отсутствует в venv; `$verify\clean-venv\Scripts\typr-gui.exe` существует. Launcher не запускался. |

Точные команды основных проверок (pytest выполнялся из внешнего Temp cwd;
ruff/Git/build — из repo):

```powershell
$env:PYTHONPATH = "$repo\src"
& $tool -m pytest -q "$repo\tests" --rootdir="$repo\tests" --confcutdir="$repo\tests" --import-mode=importlib -p no:cacheprovider
& $tool -m ruff check src/typr/__main__.py src/typr/app.py src/typr/core/audio_recorder.py src/typr/ui/settings_dialog.py src/typr/utils/i18n.py tests/test_app.py tests/test_settings_dialog.py tests/test_audio_recorder.py tests/test_main.py
git diff --check
& $tool -m build --outdir $dist
& $clean -m pip download --only-binary=:all: --platform win_amd64 --python-version 312 --implementation cp --abi cp312 --no-deps PyAudio --dest "$verify\pyaudio-cp312"
& $clean -m pip download --only-binary=:all: --platform win_amd64 --python-version 315 --implementation cp --abi cp315 --no-deps PyAudio --dest "$verify\pyaudio-cp315"
& $clean -m pip install --only-binary=pyaudio "$dist\typr-0.4.0-py3-none-any.whl"
# Только диагностика после неуспешного full install, без PyAudio stub/build:
& $clean -m pip install --no-deps "$dist\typr-0.4.0-py3-none-any.whl"
& $clean -m pip install 'PyQt6>=6.5.0' 'httpx>=0.25.0' 'websockets>=12.0'
& $clean -m pip check
```

Диагностически установлены PyQt6/Qt6 6.12.0, PyQt6-sip 13.13.0, httpx 0.28.1,
websockets 17.4, anyio 4.16.0, certifi 2026.10.23, httpcore 1.0.9, h11 0.16.0,
idna 3.20. Проверки installed package выполнялись новым `$clean` после удаления
`PYTHONPATH`, из `$verify\Unicode пробелы cwd`. До обоих imports `HOME`,
`USERPROFILE`, `LOCALAPPDATA` направлены в `$verify\isolated-profile`.
Проверены `importlib.metadata.distribution('typr')`, entry_points, classifiers,
Requires-Dist, `find_spec('evdev') is None`, наличие launcher и отдельно вызваны
`importlib.import_module('typr.app')` / `importlib.import_module('typr.__main__')`.
`main`, QApplication и entrypoints не запускались, real config/logs не читались.

**Открытые gates:** полный clean install/pip check и оба installed imports на
выбранной релизной minor Python с настоящим PyAudio; applicable suite на Linux,
Linux permissions/persistence/shell/evdev/uinput и Wayland/X11 clipboard regression;
нативные Windows hooks/session reset/SendInput/clipboard/ACL-positive acceptance,
audio devices/privacy/removal/recovery и shutdown с реальными устройствами;
Windows 11 GUI/consoleless launch из Unicode+spaces cwd, tray/settings/history,
настоящая транскрипция с тестовым endpoint. Скачанный cp312 wheel не проверялся
исполнением. GUI/hardware/network transcription запрещены в этой verification;
поддержка Windows **не объявляется готовой**. Версия metadata осталась 0.4.0,
SemVer bump/commit/push и install.sh не выполнялись.

- Область записи: `src/typr/core/audio_recorder.py`, `src/typr/app.py`, `src/typr/__main__.py`, `src/typr/ui/settings_dialog.py`, `src/typr/utils/i18n.py`, `pyproject.toml`.
- Область записи (tests): `tests/test_audio_recorder.py`, `tests/test_app.py`, `tests/test_settings_dialog.py`.
- Документация: `README.md`, `docs/DEVELOPMENT.md`, `docs/ARCHITECTURE.md`, этот план.
- Задачи: неблокирующий audio lifecycle (устранить open/stop/join из Qt main thread); тесты быстрого press/release при открытии, delayed stop/close/error/shutdown.
- Задачи: адаптация Linux-строк в `settings_dialog.py:438,544` и `app.py:126` через i18n; скрытие/отключение Cancel UI без нового workflow.
- Задачи: подсказка о буфере обмена в Settings; гарантированный `cleanup()` в `finally` при выходе из `app.py`; Windows classifier в `pyproject.toml` (без bump).
- Критерии проверки (Gate): тесты UI, audio и app; чистая сборка wheel (`python -m build`), `pip check`, установка в `.venv` и запуск `typr-gui` без консоли из cwd с Unicode.

### Этап 5 — Миграция аудио-подсистемы на sounddevice (PortAudio lifecycle, metadata и clean install gates)

**Статус (2026-11-04): реализован, independent review и gates 1–7 пройдены;
native gate 8 OPEN.** PyAudio заменен sounddevice, сохранены async facade, общий
worker-only lock и shutdown barrier. Реализованы blocking RawInputStream, явные
start/stop/abort/close с диагностикой, bytes(buffer), нефатальный overflow и WAV
с параметрами config без NumPy. Контракт injection не менялся. Сборка и полная
чистая установка под существующий **CPython 3.15.2 x64** разблокированы без нового Python.

#### Обоснование и первоначальная read-only проверка метаданных (исторический preflight)
Проверена доступность готовых бинарных wheels на PyPI (источники: PyPI [sounddevice 0.5.6](https://pypi.org/project/sounddevice/0.5.6/), [cffi 2.1.1](https://pypi.org/project/cffi/2.1.1/), а также официальная документация [sounddevice 0.5.6 installation](https://python-sounddevice.readthedocs.io/en/0.5.6/installation.html), [raw streams](https://python-sounddevice.readthedocs.io/en/0.5.6/api/raw-streams.html) и [expert mode](https://python-sounddevice.readthedocs.io/en/0.5.6/api/expert-mode.html)):
- `sounddevice 0.5.6`: доступен wheel `sounddevice-0.5.6-py3-none-win_amd64.whl` (Requires-Python: `>=3.7`), включающий предкомпилированную DLL PortAudio для Windows x64;
- `cffi 2.1.1`: доступен wheel `cffi-2.1.1-cp315-cp315-win_amd64.whl` (Requires-Python: `>=3.10`) под целевую архитектуру CPython 3.15 Windows x64.
*Ограничение проверки:* Проверка метаданных на PyPI подтверждает наличие пакетов, но **НЕ является runtime proof** (фактическая загрузка DLL, совместимость с CRT и корректность работы с аудиоустройствами требуют проверки исполнением в окружении).

#### Архитектурный контракт и правила реализации
Реализация этапа 5 строго следует утвержденному контракту подраздела [2.5](#25-audio-и-single-instance-архитектурный-контракт-sounddevice):
- Изоляция жизненного цикла sounddevice реализована утвержденным owner из 2.5: retained importlib module, unregister handler даже после failed import, worker-only vetted finalizer и poison после cleanup failure; без monkeypatching `_initialized` и main-thread teardown.
- Потоковая модель: только существующий worker, блокирующий `RawInputStream.read(...)` возвращает `(buffer, overflowed)`, данные берутся через `bytes(buffer)`, нефатальная обработка `overflowed`, без callbacks в первой миграции.
- Формат: PCM 16-bit, `sample_rate` и `channels` из `config` (16 kHz mono только defaults), запись без `numpy`.
- Устройства и ошибки: snapshot config, exact device name, детерминированный fallback на default только при ненайденном имени; ошибки query/open возвращаются как явные асинхронные ошибки (`devices_error`, `recording_error`).
- Синхронизация и барьеры: process-global worker-only lock для всех PortAudio вызовов; сохранение фактических сигналов фасада (`audio_ready`, `audio_chunk`, `recording_error`, `level_changed`, `devices_ready`, `devices_error`), предикатов `is_cleanup_complete()` и общего shutdown barrier (main audio + Settings retired workers + injector).
- Неизменность контракта вставки: token identity, acceptance semantics, late result filtering без функциональных правок `text_injector.py` и `app.py`.

#### Область выполненной реализации
- Код: `src/typr/core/audio_recorder.py`, новый узкий owner `src/typr/core/_sounddevice_backend.py`. Функциональных изменений `src/typr/app.py`, `src/typr/ui/settings_dialog.py`, `src/typr/core/text_injector.py` на этапе 5 нет.
- Метаданные и зависимости: `pyproject.toml` — удалены `pyaudio` и `types-pyaudio`; добавлены `sounddevice==0.5.6`, `cffi>=2.1.1,<3` после source/API проверки.
- Инсталлятор Linux: `install.sh` (узкая адаптация проверок зависимостей и импортов под `sounddevice` с сохранением системных библиотек PortAudio `libportaudio2` для Linux; запуск инсталлятора запрещен).
- Тесты: адаптированы `tests/test_audio_recorder.py`, `tests/test_app.py`, добавлен `tests/test_sounddevice_backend.py`; существующие Settings regressions включены в full suite без изменения файла.
- Документация: `README.md`, `docs/ARCHITECTURE.md`, `docs/DEVELOPMENT.md`, `docs/WINDOWS_IMPLEMENTATION_PLAN.md`.

#### Программа тестирования (Tests)
- First import/init/termination under lock: проверка первого импорта и инициализации/деинициализации PortAudio строго внутри существующего worker под блокировкой.
- Cross-instance contention: взаимное исключение операций PortAudio между основным `AudioRecorder` и экземпляром теста микрофона в `SettingsDialog`.
- Cancellation lifecycle: отмена записи до открытия стрима, во время `open`/`start` и во время ожидания `read`.
- Read / errors / overflow: обработка ошибок чтения устройства, нефатальное логирование флага переполнения (`overflowed`), валидность PCM 16-bit WAV данных под параметры из `config`.
- Device enumeration: перечисление устройств по умолчанию и при отключении/смене девайса без блокировки Qt main thread.
- Teardown failures & actual exit: обработка сбоев при `close()`/деинициализации, проверка предикатов `is_cleanup_complete()` и фактического завершения worker-потоков.
- Shutdown barrier regressions: регрессионные тесты ожидания завершения работы приложения с учетом отставленных потоков Settings и рекордера.
- Token regressions: проверка неизменности семантики operation token в `TextInjector` при изоляции audio lifecycle.

#### Критерии проверки и ворота готовности (Gates этапа 5)
1. **PASS — Full binary resolution:** загружен ВЕСЬ runtime graph binary-only на native CPython 3.15.2 Windows x64; evdev исключен native marker.
2. **PASS — Metadata verification:** `Requires-Dist` не содержит `pyaudio`/`types-pyaudio`, включая extras; Linux marker evdev и оба entrypoints сохранены.
3. **PASS — Isolated package build:** sdist и wheel через isolated `python -m build`.
4. **PASS — Clean external venv install:** полная установка wheel с настоящими dependencies, без `--no-deps`/stubs.
5. **PASS — Pip check:** exit 0, `No broken requirements found`.
6. **PASS — Installed imports:** `typr.app`, `typr.__main__` из site-packages, Unicode+spaces cwd, удаленный `PYTHONPATH`, изолированные HOME/USERPROFILE/LOCALAPPDATA.
7. **PASS — No hardware on import:** sounddevice/_sounddevice/_cffi_backend отсутствуют в `sys.modules`; import guard не вызван; `ctypes.dlopen` audit events отсутствуют. QApplication/entrypoints не запускались.
8. **OPEN — Native:** реальная загрузка/работа PortAudio DLL, физический микрофон и desktop smoke требуют отдельного разрешения; unit/package/import gates их не заменяют.

#### Финальная verification этапа 5 (2026-11-04)

Среда: `Windows-11-10.0.26300-SP0`, CPython **3.15.2 x64**, MSC v.1951
(build Oct 26 2026, 14:23:21). Проектная `.venv` Linux-only, Scripts/python.exe
отсутствует. Existing toolchain не менялся и не содержит pip. Все собственные
verification resources созданы только в новом уникальном внешнем Temp root после
проверки родителя `Test-Path -LiteralPath 'C:\Users\smale\AppData\Local\Temp\kilo'`.

```powershell
$repo = 'D:\@home\sma\programming\typr'
$tool = 'C:\Users\smale\AppData\Local\Temp\kilo\typr-stage1-venv\Scripts\python.exe'
$verify = 'C:\Users\smale\AppData\Local\Temp\kilo\typr-stage5-verify-30225342fbd746ee88fbf361606abdc2'
$tools = "$verify\tools\Scripts\python.exe"
$clean = "$verify\runtime\Scripts\python.exe"
$wheel = "$verify\dist\typr-0.4.0-py3-none-any.whl"
& $tool -B "$verify\run_verification.py"
```

Этот orchestrator выполнен из `$verify`; точные commands/cwd/exit codes сохранены
в `$verify\results.json`, outputs — в отдельных `$verify\*.log`. Scripts созданы
через apply_patch: `run_verification.py`, `verify_tests.py`, `installed_probe.py`.
HOME/USERPROFILE/LOCALAPPDATA направлены в `$verify\profile`, TEMP/TMP — в
`$verify\tmp`; bytecode и pip cache отключены. Реальные пользовательские config/секреты
не читались. Основные выполненные команды (переменные выше раскрыты в results.json):

```powershell
# Wrapper: import guard против настоящего sounddevice/_sounddevice/_cffi_backend,
# PYTEST_DISABLE_PLUGIN_AUTOLOAD=1, PYTHONPATH=<repo>\src, внешний cwd.
& $tool -B "$verify\verify_tests.py"
# Внутри wrapper ровно один pytest.main со следующими аргументами:
# -q -ra <repo>\tests --rootdir=<repo>\tests --confcutdir=<repo>\tests
# --import-mode=importlib -p no:cacheprovider --basetemp=<verify>\pytest-tmp
& $tool -B -m ruff check --no-cache "$repo\src\typr\core\audio_recorder.py" "$repo\src\typr\core\_sounddevice_backend.py" "$repo\tests\test_app.py" "$repo\tests\test_audio_recorder.py" "$repo\tests\test_sounddevice_backend.py"
& $tool -B -m venv "$verify\tools"
& $tool -B -m venv "$verify\runtime"
& $tools -B -m pip install --only-binary=:all: build
& $tools -B -m build --sdist --wheel --outdir "$verify\dist" $repo
& $clean -B -m pip download --only-binary=:all: --dest "$verify\downloads" $wheel
& $clean -B -m pip install --only-binary=:all: $wheel
& $clean -B -m pip check
# Orchestrator удаляет PYTHONPATH; cwd: <verify>\Рабочая папка Unicode
& $clean -B "$verify\installed_probe.py"
```

Результаты:
- **256 passed, 2 skipped за 4.61 s**, full applicable pytest один раз; пропущены
  Linux-only installer/uninstaller modules до чтения scripts. Scoped ruff — PASS.
- Изолированная сборка создала `$verify\dist\typr-0.4.0.tar.gz` и wheel выше;
  оба isolated build env — hatchling **1.33.0**. Build **1.6.1**, pip новых venv
  **26.2.2**, packaging **26.3**, pyproject_hooks **1.3.3**, colorama **0.4.6**.
- Native binary resolution без cross-target overrides загрузила весь runtime graph,
  включая `cffi-2.1.1-cp315-cp315-win_amd64.whl`,
  `websockets-17.4-cp315-cp315-win_amd64.whl`,
  `pyqt6_sip-13.13.0-cp315-cp315-win_amd64.whl`,
  `sounddevice-0.5.6-py3-none-win_amd64.whl`; все wheels — в `$verify\downloads`.
- Полная чистая установка и pip check — PASS. Runtime: typr **0.4.0**, sounddevice
  **0.5.6**, cffi **2.1.1**, pycparser **3.12**, PyQt6/Qt6 **6.12.0**,
  PyQt6-sip **13.13.0**, httpx **0.28.1**, httpcore **1.0.9**, h11 **0.16.0**,
  websockets **17.4**, anyio **4.16.0**, idna **3.20**, certifi **2026.10.23**.
  Test tooling: pytest **9.2.0**, ruff **0.17.3**, PyQt6/Qt6 **6.12.0**.
- Installed imports действительно из `$verify\runtime\Lib\site-packages\typr`;
  `QCoreApplication.instance() is None`. Metadata проверена вместе с extras;
  `typr` console / `typr-gui` GUI entrypoints → `typr.__main__:main`, оба exe
  существуют, но не исполнялись. Production-заглушек нет.
- Installed sounddevice source прочитан и разобран AST без импорта; сопоставлен с
  [официальным source 0.5.6](https://python-sounddevice.readthedocs.io/en/0.5.6/_modules/sounddevice.html).
  `_atexit.register(_exit_handler)` идет перед `_initialize()` (строки **2972/2973**);
  credit увеличивается после успешного Pa_Initialize до stderr restoration,
  уменьшается после успешного Pa_Terminate; finalizer исчерпывает credits циклом
  и содержит upstream `_last_callback` cleanup. SHA-256 source:
  `d77bf40ba945491538dd6a93b5fb8f45d051c10689f0e10c0b928ef89f172891`.
- Существующий `C:\Program Files\Git\bin\bash.exe`, GNU Bash **5.3.15(2)-release**
  (`x86_64-pc-cygwin`): отдельные `bash -n install.sh` и `bash -n uninstall.sh`
  завершились с exit 0. Первоначальная объединенная команда дополнена отдельными
  проверками обоих файлов. Это syntax check Git Bash, **не Linux native regression**.
  Scripts и `--dry-run` не запускались. `git diff --check` успешен; только Git
  предупреждения о будущей LF→CRLF конвертации.
- Предварительная диагностика: у existing toolchain нет pip; первая сводная команда
  версий дала PackageNotFoundError для отсутствовавшего websockets. Existing toolchain
  не исправлялся; версии доступных инструментов получены отдельно, настоящий websockets
  установлен в новый runtime venv и проверен в полном графе.

Независимое read-only **general-deep review**: подтвержденных bugs нет;
независимый targeted suite — **67 passed** (отдельное свидетельство review,
не повтор полного suite этой verification). Неблокирующие пробелы покрытия:
одновременные failed import + failed finalization, exact-name collisions / index 0,
соответствие stereo fake payload запрошенному размеру read frames. Это не подтвержденные
дефекты production и не закрывает native gate.

Сборки выше соответствуют реализованному коду/зависимостям **до финального docs-only
обновления статуса**; после него build/tests не перезапускались. Runtime/tests/version
не менялись этой документационной правкой. Новый Python, QApplication, hardware/native
sounddevice import, commit/push и изменение системных разрешений не выполнялись.

## 4. Чеклист верификации и критерий готовности

### 4.1. Автоматизированные проверки
- **PASS на Windows CPython 3.15.2 x64:** isolated sdist/wheel, full binary download, clean full install и pip check без `--no-deps`/stubs; gates 1–5 этапа 5.
- **PASS:** installed imports из Unicode+spaces cwd с изолированным профилем и удаленным PYTHONPATH, без audio module/native init; gates 6–7.
- **PASS на Windows:** полный applicable pytest 256 passed / 2 skipped и scoped ruff. **OPEN на Linux:** полный suite и native regressions; Git Bash syntax check их не заменяет.

### 4.2. Натурный Smoke Checklist (требует отдельного разрешения)
- Windows 11: старт `typr-gui` без консоли из cwd с Unicode/пробелами в пути; tray/settings/history; дефолтный `Ctrl+Alt+Z`.
- Windows 11: PTT запись через sounddevice (быстрый клик, длинное удержание, игнор duplicate down, lock/unlock, RU/EN раскладки, AltGr, release модификаторов).
- Windows 11: вставка Unicode через Ctrl+V в обычные приложения; текст в буфере, транскрипция в истории; корректный выход без зависших потоков/хуков.
- Linux: базовый нативный регресс Wayland и X11 (PTT через evdev, uinput вставка, восстановление через wl-copy/xclip, shell tests).

### 4.3. Критерий готовности и открытые ворота
- Поддержка принимается только если согласованные contracts реализованы, applicable automation и desktop smoke пройдены на обеих ОС без прав admin.
- Пользовательские данные и секреты сохранены, UI остается отзывчивым, непроверенное честно указано в отчете.
- Hardware/GUI проверки требуют отдельного разрешения, тестового endpoint и фиктивных секретов.
- Этап 5: gates **1–7 PASS**, gate **8 OPEN**. Packaging/import для существующего
  Python 3.15.2 подтверждены; полная native/release qualification minor открыта.
- Открыты на Linux: полный applicable suite, installer shell checks, native audio, evdev, uinput, Wayland/X11 clipboard regressions.
- Открыты на Windows: low-level keyboard hooks, session reset/lock/unlock, SendInput, clipboard policy, ACL positive acceptance.
- Открыты на Windows: audio devices enumeration/privacy/removal/recovery и shutdown с реальными устройствами.
- Открыты на Windows: Windows 11 GUI/consoleless launch из Unicode+spaces cwd, tray/settings/history, сквозная транскрипция с тестовым endpoint.
- Действуют строгие ограничения: запрещена установка новых версий Python без согласования, запрещены несанкционированные GUI и hardware тесты, запрещены git commit и git push.

## 5. Отложенные задачи (Deferred)

Следующие задачи не входят в минимальный объем первого релиза и требуют отдельного решения при необходимости:
- Standalone сборка через freezer (PyInstaller/one-dir bundle) и бандлинг нативных библиотек Qt/PortAudio.
- Windows per-user installer (Inno Setup / WiX) и автоматизация автозапуска в реестре/Startup.
- Иконка `.ico`, PE metadata (file/product version), подпись Authenticode и SmartScreen reputation.
- Полноценный snapshot и надежный restore сложных форматов буфера обмена (HTML/RTF/OLE) с учетом TOCTOU.
- Системный межпроцессный мьютекс (`CreateMutexW`) для блокировки повторного запуска.
- Полноценный workflow отмены записи (Cancel hotkey).
- Настройка матрицы Windows в GitHub Actions CI.
