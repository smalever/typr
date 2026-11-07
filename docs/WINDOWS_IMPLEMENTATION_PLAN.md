# План реализации поддержки Windows 11

## Статус и правила исполнения

**Текущий статус (2026-11-07): этапы 1–5 реализованы (gates 1–7 PASS); выполнены частичная нативная верификация Windows (desktop smoke и launcher-ворота L/R/T), native gate 8 находится в статусе PARTIAL / OPEN; baseline тестов исходного кода — 280 passed, 2 skipped.**
По явному разрешению пользователя утверждено санкционированное расширение границ поставки Windows: автономный per-user инсталлятор для **Windows 11 x64** без требования предустановленного Python (ZIP-пакет `Install.bat` + `Uninstall.bat` + мастер установки `Install.ps1` на Windows PowerShell 5.1 + offline CPython 3.15.2 embeddable amd64 runtime с wheel-пакетами Typr и зависимостей в `%LOCALAPPDATA%\Programs\Typr`) и интеграция локального STT в Docker (выбор Parakeet / GigaSTT на loopback). Это новое утвержденное продолжение (этап 6), а не повтор этапов 1–5.
Реализация скриптов поставки в `scripts/windows` подготовлена (`Install.bat`, `Uninstall.bat`, `Install.ps1`, `TyprInstaller.ps1`, `Build-Payload.ps1`, `Verify-Runtime.py`, `Initialize-Config.py`). Независимое ревью выявило замечания (обработка потока stderr Docker CLI, транзакционное возобновление/откат установки и удаления с проверкой нативной идентичности каталога через Win32 handle, защита от оставшихся scratch-файлов JSON, ошибка сборщика ZIP-архивов `LastWriteTime` setter), которые полностью устранены; повторное независимое ревью подтвердило исправление всех замечаний (targeted pytest: 4 passed за 11.02 с); итоговый ZIP-пакет успешно собран. Статус релиза: в процессе квалификации (автоматизированная сборка снепшота проверена; натурная приемка на чистой ОС ожидает выполнения).
Актуальные доказательства верификации:
- Финальный полный pytest с тестами установщика: **284 passed, 2 skipped**; scoped Ruff и PowerShell parser — PASS. Все 4456 файлов итогового payload сверены по SHA-256. Установка во временный каталог, встроенный `pip check`, guarded imports, создание свежей конфигурации GigaSTT с private ACL и безопасное удаление с сохранением соседних данных — PASS. Реальные Start Menu/Startup и чистая Windows этим не проверены.
- Новый source wheel `typr-0.4.0-py3-none-any.whl` с исправлением барьера транскрибера пересобран и прошел полную чистую офлайн-установку полного набора бинарных зависимостей, `pip check` (exit 0) и guarded imports (`typr.app`, `typr.__main__`) в Unicode+spaces каталоге с изолированным профилем и проверкой отсутствия неконтролируемой загрузки sounddevice в `sys.modules`.
- Проведена сквозная верификация WhisperTranscriber на новом установленном рантайме через `QCoreApplication` с синтетическим in-memory WAV (тишина 1.5 с, 16 кГц, PCM16) против реального локального HTTP-сервиса GigaSTT: получен HTTP 200, транскрипция завершена (длина 0), нативный поток ОС подтвержден завершенным через `WaitForSingleObject` дескриптора потока Win32, дескриптор закрыт, `is_cleanup_complete() == True` (PASS). Это подтверждает работоспособность связки реального HTTP и нативного FLS exit probe без привлечения микрофона, GUI, хуков или буфера обмена.
- Развернут локальный сервис GigaSTT (pinned digest `sha256:ac7f7ccb7d5b9628d9e16cc361f29e61beedd8e1df8b0927b4a17921b7ec2f35`, v2.22.0): создан собственный контейнер `typr-win-<SID>-gigastt` с именованным Docker-томом моделей `typr-win-<SID>-gigastt-models` на loopback `127.0.0.1:9876`, подтверждена готовность `/ready` 200 и `/health` 200 (модель `gigaam-v3-rnnt`, вариант `rnnt`), повторный запуск переиспользует тот же контейнер без повторных скачиваний.
- Сборщик `Build-Payload.ps1`: автоматизированная сборка снепшота завершена успешно (**Gate 6.1 PASS**; сформирован итоговый архив `Typr-Windows-x64-20261107-final.zip` размером 105 245 862 байт, SHA-256 `9c5e3614a3e09da58b2411c09a8ad6830e972d58722041734f7bf79d7286aaef`): пересборка актуального wheel, развертывание embed-рантайма CPython 3.15.2, чистая офлайн-установка полного графа зависимостей wheelhouse, `pip check` и изоляция импортов `Verify-Runtime.py` пройдены.
- Локальный STT: скачивание архива исходников Parakeet по коммиту `06464cd06a0f75426ce46e94c2d04ee7e26f48c0` и хэшу `fa58716020a9a95d4b6695f6b0a5466f064d1b3719dd6db071f058fc3ffbbc90` верифицировано (только скачивание без сборки образа); для контейнеров STT действует политика `--restart no`, автозапуск Typr не запускает Docker/STT.
- Native Gate 8 PARTIAL/OPEN и все открытые hardware/production/Linux/release gates остаются неизменными.
По явному разрешению пользователя проведен санкционированный натурный smoke (реальный микрофон, GUI, хуки `WH_KEYBOARD_LL`, SendInput Unicode paste в собственный `QTextEdit` с focus guard) в изолированном профиле без сетевого endpoint на существующем установленном runtime этапа 5 (CPython 3.15.2 x64, wheel 0.4.0, sounddevice 0.5.6, cffi 2.1.1, PyQt6 6.12.0).
В обычном запуске получен полный PASS (exit 0): реальная нативная запись WAV в памяти (~2 с), регистрация/снятие хуков, зарегистрированный Ctrl+V-зонд не выдал PTT при синтетической вставке (доставка и фильтрация synthetic events непосредственно не наблюдались), успешная вставка в собственный экран и чистый выход всех воркеров.
В consoleless-запуске (`pythonw.exe`) зафиксирован таймаут ожидания фокуса окна вставки (`fg_own=false, pid_own=false, qtactive/focusOwn/visible=true`, exit 1); точная причина таймаута не установлена (ограничения Windows — возможная причина), injection не запускался (focus guard предотвратил SendInput), остальные компоненты и cleanup прошли штатно; production-дефект не подтвержден.
На том же СТАРОМ существующем установленном runtime этапа 5 (`typr-gui.exe`, wheel 0.4.0, без нового source fix) нативные ворота лаунчера **L/R/T завершились PASS (exit 0)** через изолированный child-only bootstrap (`PYTHONPATH`/`sitecustomize.py`), настоящий `main`/`start`/`quit`/`_cleanup` и `DETACHED_PROCESS` без перенаправления stdout/stderr (наблюдены `sys.stdout`/`sys.stderr is None` до импорта, во время работы и при выходе; штатный FileHandler изолирован, console handler отсутствует):
- **L (idle launcher):** штатный старт, трей видим, хук зарегистрирован, изолированный config сохранен, выход по сигналу трея -> чистый выход всех воркеров.
- **R (recording shutdown):** получен первый реальный непустой `audio_chunk` (`count: 1`) -> штатный quit во время активного `RECORDING` -> фактический выход worker. Это новый gate остановки записи, а не повтор микрофонного baseline.
- **T (typing timer shutdown):** фиктивное завершение транскрипции -> pending injection принят / таймер бекенда активен -> немедленный штатный quit ДО публикации в буфер и SendInput (`publication_attempts: 0, sendinput_attempts: 0`), без реальной вставки.
Во всех трех случаях (L, R, T) сетевые попытки, непредвиденные вызовы транскрибера, публикации и SendInput строго равны 0; штатный выход воркеров, хука и Qt cleanup подтверждены. Сценарий вставки в собственное окно (P) осознанно исключен для устранения focus race; таймаут фокуса в consoleless `pythonw.exe` из предыдущего smoke остается историческим результатом, а не production-дефектом. Launcher PASS подтвержден только для ограниченного тестового контура; приемка несконфигурированного продакшен-лаунчера без сдерживания и со сквозным endpoint остается **OPEN**.

Параллельно выявлен и устранен **НОВЫЙ подтвержденный дефект в исходном коде транскрибера** (не противоречит историческому smoke 'no defect', где сетевая транскрипция не вызывалась):
- Сигнал результата `WhisperTranscriber` испускался до закрытия HTTP-контекста (`httpx.Client`), а `TyprApp` не включал воркер транскрибера в барьер завершения (`_finish_quit_when_injection_closed`).
- Реальный нативный тест FLS (Fiber Local Storage) на Windows с Qt 6.12.0 опроверг достаточность `wait(0)`: вызов `worker.wait(0)` возвращал `True`, а `worker.isRunning()` — `False`, когда поток ОС все еще исполнял FLS/TLS-коллбеки (нативный `WaitForSingleObject` возвращал `258` / `WAIT_TIMEOUT`).
- Реализовано исправление: воркер до HTTP открывает собственный `SYNCHRONIZE` thread HANDLE через `OpenThread`; `TranscriberWorker` испускает раздельные worker-сигналы `result`/`error`, фасад удерживает outcome до закрытия клиента и выхода потока; таймер (10 мс) опрашивает OS-хэндл (`WaitForSingleObject == WAIT_OBJECT_0`) перед закрытием хэндла и публикацией наружу; добавлены защита от busy/reentrant, терминальный cleanup с подавлением поздних результатов и включение `self.transcriber.is_cleanup_complete()` в барьер выхода `TyprApp`.
- Для Linux задокументирован контракт `wait(0)`, но нативная приемка Linux остается **OPEN**. Ошибки `OpenThread` и probe приводят к fail-closed блокировке shutdown; сбой `CloseHandle` логирует утечку без срыва барьера. HTTP payload, endpoint и timeouts не менялись, принудительного kill нет.
- Актуальный набор тестов исходного кода через существующий изолированный `verify_tests.py` составляет **280 passed, 2 skipped** (Linux installer shell tests), scoped ruff и diff clean. Независимое general-deep review подтвердило отсутствие замечаний (targeted suite: **54 passed за 1.49 с**, включая реальные held FLS тесты обычного пути и cleanup). Предыдущий blocker `WinError 32` при сканировании корня снят запуском pytest из внешнего temp cwd с абсолютными флагами `--rootdir`, `--confcutdir`, `--import-mode=importlib`.
- **Критическая граница (историческая):** установленный wheel этапа 5 исходно не пересобирался сразу после исправления транскрибера. **Актуальный статус:** новый source wheel `typr-0.4.0-py3-none-any.whl` успешно пересобран и прошел полную чистую установку с 14 зависимостями, pip check и guarded imports; сквозной HTTP-вызов транскрибера на тишине подтвердил native thread exit probe. Пакетная сборка проверена, сквозная нативная приемка полного GUI-приложения остается **OPEN**.
- Исторические срезы: baseline этапа 4 (**232 passed, 2 skipped**), baseline этапа 5 (**256 passed, 2 skipped**) сохраняются как история и не переписываются.
- Blocker packaging/import на 3.15.2 снят этапом 5, но это не полная релизная квалификация minor.
- Поддержка Windows приложения еще **не готова**: сквозная транскрипция с endpoint в GUI, физический PTT, раскладки/AltGr, lock/unlock, privacy/unplug recovery, uninstrumented production launcher (`typr-gui.exe`), полная релизная квалификация Python, Linux gates, а также автономный инсталлятор и локальный Docker STT остаются открытыми. Действующая архитектура описана в [ARCHITECTURE.md](ARCHITECTURE.md), правила документации — в [DOCUMENTATION_POLICY.md](DOCUMENTATION_POLICY.md).
- Агент выполняет только явно порученный этап; наличие плана не разрешает произвольные изменения системы, запуск GUI или commit.
- Координатор утверждает архитектуру, контракты и зависимости; исполнитель выбирает локальную реализацию в утвержденных границах.
- У каждого файла один писатель. Этапы выполняются строго последовательно с приемкой; review — в режиме read-only.
- Отчет исполнителя содержит результат, измененные пути, принятые решения, команды и результаты проверок, непроверенное и блокеры.

## Цель и non-goals

Цель: нативная работа tray-first клиента Typr на **Windows 11 x64** для существующей целевой minor версии Python (**CPython 3.15.2 x64**, packaging/import verified, native/release acceptance pending; установка Python 3.12 не требуется) с сохранением стабильности Linux (Wayland/X11).
Формат поставки расширен по утвержденному решению: автономный per-user инсталлятор без требования наличия предустановленного Python (ZIP-пакет `Install.bat` + мастер установки Windows PowerShell 5.1 + offline embeddable runtime CPython 3.15.2 x64 с предсобранными wheels Typr и зависимостей с установкой в `%LOCALAPPDATA%\Programs\Typr` и сохранением данных в `%LOCALAPPDATA%\Typr`) и поддержка локального Docker STT (Parakeet / GigaSTT на loopback). Чистая установка wheel в `.venv` сохраняется как базовый пакетный контракт.

Обновленные Non-goals (переход в скоуп и остающиеся ограничения):
- Разрешено и переведено в утвержденный объем: автономный per-user инсталлятор (ZIP bundle `Install.bat` + PS 5.1 wizard) без зависимости от системного Python.
- Разрешено и переведено в утвержденный объем: опциональный автозапуск через ярлык в пользовательской папке Startup (строго с явного подтверждения пользователя, без записи в реестр).
- Разрешено и переведено в утвержденный объем: локальный STT в Docker (выбор Parakeet / GigaSTT, строго на loopback-интерфейсе `127.0.0.1`).
- Non-goal: сторонний freezer (PyInstaller/one-dir bundle) и внешние системы сборки инсталляторов (Inno Setup / WiX) — не требуются благодаря поставке официального embeddable runtime ZIP.
- Non-goal: автозапуск через реестр Windows (HKCU/HKLM Run keys).
- Non-goal: требование новой minor-версии Python (сохраняется CPython 3.15.2 x64).
- Non-goal: генерация `.ico`, PE metadata (file/product version), цифровая подпись Authenticode / SmartScreen reputation.
- Non-goal: новый CI.
- Non-goal: удаленный доступ к демону Docker (запрещен; разрешен только локальный Docker на `127.0.0.1`), перехват сторонних/конфликтующих контейнеров.
- Non-goal: скрытые изменения настроек WSL или Docker Engine без подтверждения.
- Non-goal: посимвольная эмуляция ввода текста, обход UIPI / ввод в privileged/elevated окна и Secure Desktop/UAC.
- Non-goal: сложный ACL framework (сохраняются существующие проверки DACL профиля).
- Non-goal: автомиграция данных и изменение Linux shell-скриптов (за исключением уже выполненной узкой адаптации проверок audio-зависимостей и импортов в `install.sh` под sounddevice).

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

### 2.6. Автономная per-user поставка Windows и интеграция локального Docker STT
- **Формат поставки и автономный рантайм:** ZIP-пакет содержит `Install.bat`, Uninstall.bat, вызывающий `Install.ps1 -Uninstall`, мастер установки `Install.ps1`, модуль `TyprInstaller.ps1` и официальный offline CPython 3.15.2 embeddable amd64 runtime (`python-3.15.2-embed-amd64.zip` / распакованный runtime) вместе с wheel-пакетами Typr и всех runtime-зависимостей (`sounddevice`, `cffi`, `PyQt6`, `httpx`, `websockets` и др.). Внешний freezer (PyInstaller) и сторонние установщики (Inno Setup / WiX) не требуются; смена minor-версии Python не требуется.
- **Роль сборщика (builder, `Build-Payload.ps1`):** сборщик пересобирает source wheel Typr из актуального дерева репозитория (включая исправление FLS-барьера транскрибера), принимает предварительно подготовленный wheelhouse с манифестом хэшей SHA-256 (`wheelhouse-manifest.json` / `Assert-TyprInventory`), верифицирует предоставленный официальный ZIP-архив CPython 3.15.2 embeddable amd64 по SHA-256 (`d012f3aa29cf07436dae8aea1fec0fd195c2612a0b059b1f915ae0afb9ad1f62`) и формирует автономный ZIP-пакет (автоматическое скачивание зависимостей сборщиком исключено, зависимости подаются в wheelhouse).
- **Разделение путей программы и данных:** программные файлы и embeddable runtime развертываются строго в каталог пользователя `%LOCALAPPDATA%\Programs\Typr` с изоляцией окружения (`._pth`, `sitecustomize.py`). Пользовательские конфигурации, история и логи изолированы в `%LOCALAPPDATA%\Typr` (`config.json`, `history.json`, `logs\typr.log`), сохраняются при обновлениях и не затираются.
- **Интеграция локального Docker STT:** мастер установки предлагает выбор бэкенда распознавания (Parakeet, GigaSTT либо внешний/облачный endpoint).
- **Собственные per-user ресурсы контейнеров:** используются собственные выделенные per-user имена контейнеров по схеме `typr-win-<SID>-<kind>` (например, `typr-win-<SID>-gigastt`) и именованные Docker-тома моделей `typr-win-<SID>-<kind>-models` (монтируются в `/home/gigastt/.gigastt/models` или `/app/models`). При обнаружении конфликта имен или занятости портов мастер выдает явный отказ (fail-fast), запрещая перехват или модификацию чужих/сторонних контейнеров.
- **Сетевая изоляция демона и сервиса:** привязка портов выполняется исключительно на loopback-интерфейс (`127.0.0.1:9876` для GigaSTT, `127.0.0.1:5092` для Parakeet); проброс во внешние сети и удаленный доступ к Docker daemon запрещены.
- **Хранение моделей в Docker-томах:** модели сохраняются в именованных Docker-томах `typr-win-<SID>-<kind>-models`, что предотвращает повторное скачивание многогигабайтных весов при перезапусках контейнера.
- **Интерактивные подтверждения и права:** обязательно явное интерактивное подтверждение пользователя на загрузку тяжелых ресурсов (установщика Docker Desktop, образов, исходников Parakeet по коммиту `06464cd...` с проверкой SHA-256), запуск инсталлятора Docker с повышением UAC (при необходимости; сам инсталлятор Typr выполняется без прав администратора) и создание ярлыка автозапуска в пользовательской папке Startup (без записи в реестр). Ярлык на рабочем столе не создается (только меню «Пуск» и опционально Startup).
- **Защита системной конфигурации WSL:** скрытые изменения настроек WSL, дистрибутивов или конфигурации демона Docker категорически запрещены.
- **Безопасная деинсталляция:** деинсталлятор (`Uninstall.bat` / `Install.ps1 -Uninstall`) удаляет файлы программы из `%LOCALAPPDATA%\Programs\Typr`, ярлыки меню «Пуск» (`Programs\Typr.lnk`, `Programs\Uninstall Typr.lnk`) и ярлык автозапуска в Startup; по умолчанию деинсталлятор строго сохраняет пользовательские конфигурации, историю (`%LOCALAPPDATA%\Typr`) и именованные тома моделей Docker (удаление томов моделей требует явного ключа `-RemoveModels`).

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

### Частичная нативная verification Windows (post-stage 5, 2026-11-04)

Пользователь явно санкционировал полный Windows smoke (нативный микрофон, видимый GUI, хуки `WH_KEYBOARD_LL`, clipboard SendInput) с изолированным профилем и без сетевого endpoint.
Проверка проведена на существующем установленном runtime этапа 5 без сборки нового окружения и без установки нового Python.

Среда исполнения:
- ОС: Windows 11 x64 (`Windows-11-10.0.26300-SP0`, AMD64);
- Runtime этапа 5: `C:\Users\smale\AppData\Local\Temp\kilo\typr-stage5-verify-30225342fbd746ee88fbf361606abdc2\runtime\Scripts\python.exe` (CPython 3.15.2 x64, установленный wheel `typr==0.4.0`, `sounddevice==0.5.6`, `cffi==2.1.1`, `PyQt6==6.12.0`);
- Harness (расположен вне репозитория): `C:\Users\smale\AppData\Local\Temp\kilo\typr-stage6-9df3f50e6c8549ed96fd3a8b62e6c8cd\smoke.py`.

Точные команды запуска (из любого каталога):

```powershell
$python = 'C:\Users\smale\AppData\Local\Temp\kilo\typr-stage5-verify-30225342fbd746ee88fbf361606abdc2\runtime\Scripts\python.exe'
$harness = 'C:\Users\smale\AppData\Local\Temp\kilo\typr-stage6-9df3f50e6c8549ed96fd3a8b62e6c8cd\smoke.py'
& $python -I -B $harness
# Запуск в consoleless-режиме (pythonw.exe):
& $python -I -B $harness --consoleless
```

#### Изоляция, безопасность и privacy
- Каждый запуск создавал изолированную директорию `run-<uuid>` под внешним корнем `typr-stage6-9df3f50e6c8549ed96fd3a8b62e6c8cd`.
- Каталоги окружения перенаправлены в подкаталоги запуска: `HOME`, `USERPROFILE`, `LOCALAPPDATA`, `APPDATA` направлены в `<run>\profile`; `TEMP`, `TMP` — в `<run>\tmp`; рабочий каталог (`cwd`) — `<run>\Рабочая папка Unicode`.
- Сброшены переменные `PYTHONPATH`, `PYTHONHOME`, `QT_QPA_PLATFORM`, `QT_PLUGIN_PATH`, `QT_QPA_PLATFORM_PLUGIN_PATH`, `PYQTGRAPH_QT_LIB`; установлены `PYTHONDONTWRITEBYTECODE=1`, `PYTHONNOUSERSITE=1`.
- Реальные пользовательские конфигурация (`~/.config/typr/config.json`), история и секреты не читались.
- Выходной лог `process-output.log` служит нативным краш/Qt-диагностическим стоком и не подлежит публикации без privacy review.
- Логирование Typr (`logging.disable(logging.CRITICAL)`) отключено до импортов для предотвращения раскрытия имен системных аудиоустройств и персональных метаданных. В результаты (`results.json`) включены только булевы флаги, счетчики и имена типов исключений, без сырых сообщений или полезной нагрузки.

#### Архитектура сдерживания (ContainedApp)
- Тестовый контроллер реализован изолированным подклассом `ContainedApp(TyprApp)`:
  - Обработчики сигналов записи `_on_recording_start` и `_on_recording_stop` переопределены как no-op (нажатия хоткеев и клики трея физически не могут инициировать оркестрацию записи);
  - Обработчик `_on_audio_ready` вызывает `RuntimeError("SMOKE_ORCHESTRATION_DISABLED")`;
  - Метод `controller.transcriber.transcribe` заменен на функцию, возбуждающую `RuntimeError("SMOKE_TRANSCRIPTION_DISABLED")`;
  - Зарегистрирован процессный аудит-хук `sys.addaudithook`: блокирует сетевые вызовы (`socket.connect`, `socket.connect_ex`, `socket.getaddrinfo`, `socket.bind`, `socket.sendto`) с `PermissionError("SMOKE_NETWORK_DISABLED")`. Во всех запусках зафиксировано `network_attempts: 0`, реальный HTTP-транскрибер не вызывался.
- Диалоговые окна Settings и History отображались кратковременно в видимом режиме и блокировались (`setEnabled(False)`) от случайных кликов на период наблюдения; автоматическое перечисление устройств в Settings выполнялось штатно, явные проверки аудио вынесены в отдельный изолированный фасад.

#### Проверенные подсистемы и результаты
- **Config & History persistence:** roundtrip изолированного `AppConfig` (`api_key=""`, проверка создания `config.json` и положительного DACL gate без изменения системных прав) — PASS; roundtrip `HistoryManager` (`HistoryEntry.create("Typr smoke: Привет 世界 🙂", model="smoke-only")`) — PASS. API key пустой, секреты не использовались.
- **GUI & Tray:** видимый `QApplication` на Windows (`app.platformName() == "windows"`), доступность системного трея (`QSystemTrayIcon.isSystemTrayAvailable()`), видимость иконки трея (`tray_icon.isVisible()`), видимость диалогов настроек и истории из пути с Unicode и пробелами (`Рабочая папка Unicode`).
- **Audio subsystem (sounddevice / PortAudio):** отдельный экземпляр `AudioRecorder` с реальной PortAudio DLL (`OWNER._module is not None and not OWNER._broken`). Асинхронное перечисление устройств (`request_devices()` -> `devices_ready`, `input_devices_present: true`), завершение воркера перечисления (`enumeration_worker_exited: true`). Нативная запись звука с реального микрофона по умолчанию длительностью около 2 секунд. Получен валидный WAV: PCM 16-bit, моно, 16000 Hz (`wav_pcm16_mono_16k: true`), ненулевое число фреймов (`wav_nonempty_frames: true`). Аудио валидировалось исключительно в оперативной памяти (`io.BytesIO`), ссылки на аудиоданные сразу очищены (`captured.clear()`), аудио на диск не сохранялось. Фактическое завершение воркера записи (`recording_worker_exited: true`) и деинициализация аудио-подсистемы (`audio_cleanup_actual_exit: true`). *Ограничение:* ненулевые фреймы подтверждают нативный захват с оборудования, но не являются доказательством разборчивости речи.
- **Low-level keyboard hooks (WH_KEYBOARD_LL):** регистрация и снятие двух реальных фасадов: основного хука приложения (`Ctrl+Alt+Z`) и тестового зонда (`Ctrl+V`). Во время синтетической вставки Ctrl+V тестовый зонд не сгенерировал PTT-сигналов (`synthetic_ctrl_v_ignored_by_hook: true`). Нативные ошибки хуков отсутствуют (`native_hook_errors_absent: true`, `hook_cleanup_errors_absent: true`). *Ограничение:* зарегистрированный Ctrl+V-зонд не выдал PTT при синтетической вставке; доставка synthetic events в callback и их фильтрация непосредственно не наблюдались; не доказывает доставку физических событий, физическую семантику PTT, поведение AltGr/раскладок или обнаружение silent hook removal.
- **SendInput & Clipboard policy:**
  - Тест создавал собственное окно `QTextEdit` («Typr OWN paste target — acceptance only»).
  - До отправки `SendInput` предохранитель `FocusGuard` проверял инварианты окна: `HWND`, `PID`, `GetForegroundWindow()`, активное окно Qt, точный фокус виджета и отпущенные клавиши вставки; при нарушении фокуса `SendInput` блокируется, разрешая только keyup cleanup синтетических модификаторов.
  - Тестовый текст Unicode: `"Typr smoke: Привет 世界 🙂 — café"`.
  - Успешный цикл вставки: контракт `request_injection` с `token` -> `injection_completed(token)`.
  - Буфер обмена: тестовый текст остается в системном буфере обмена (`QApplication.clipboard().text() == text`), подтверждая контракт Windows clipboard policy (без restore/clear).
- **Cleanup barrier:** приложение ожидает фактического завершения всех воркеров (`all_workers_actual_exit: true`): рекордер завершен, контроллер завершен, оба потока хуков завершили message loop и закрылись (`thread.is_alive() == False`). Принудительное завершение процессов (`kill`) не применялось.

#### Прогоны и результаты

| Прогон / Каталог | Режим | Exit code | Статус | Детали и диагностика |
| --- | --- | --- | --- | --- |
| `run-0ea08e986c554133901a49bba548c93b` | Обычный (python.exe) | 1 | FAIL | `TimeoutError` на этапе ожидания фокуса окна вставки `own_target_focus_required` до попытки вставки. SendInput не вызывался (сработал focus guard). Аудиозапись, GUI, перечисление устройств, трей и cleanup — PASS. |
| `run-098ddd1a19cb486492cb42dd2ea0ddaa` | Обычный (python.exe) | 0 | **PASS** | Выполнен после минимальной правки harness (`SetForegroundWindow` на собственный HWND с повторами до 15 с, без `AttachThreadInput`/обходов ОС). Фокус получен (`fg_own=true, pid_own=true, qtactive=true, focusOwn=true, visible=true`). Полный цикл SendInput, Unicode paste в target, текст в буфере, воркеры завершены. |
| `run-9f5f6fd60bb14571921c26a75c2d5a01` | Consoleless (`--consoleless`, pythonw.exe) | 1 | FAIL | `TimeoutError` ожидания фокуса `own_target_focus_required`. Диагностика фокуса: `fg_own=false, pid_own=false, qtactive=true, focusOwn=true, visible=true`. Точная причина focus timeout не установлена (ограничения Windows — возможная причина); injection не запускался (SendInput предотвращен focus guard). Production-дефект не подтвержден. Аудиозапись 2 с, перечисление устройств, GUI/трей, хуки и чистый выход воркеров — PASS. |

*Примечание к consoleless-режиму:* запуск выполнялся через `pythonw.exe` из каталога `Рабочая папка Unicode` с перенаправлением `stdout`/`stderr` в `process-output.log`. Этот запуск **НЕ является** приемкой продакшен-лаунчера `typr-gui.exe` (или `python -m typr`) и **НЕ доказывает** поведение логгера при `sys.stdout is None`.

#### Статус и открытые вопросы первого натурного smoke
- **Дефекты и изменения:** production-код, тесты репозитория и зависимости не менялись. Подтвержденных production-дефектов нет: точная причина focus timeout в consoleless-запуске не установлена (зафиксированы только диагностические флаги `fg_own=false, pid_own=false, qtactive=true, focusOwn=true, visible=true`), ограничения активации Windows рассматриваются как возможная причина; injection не запускался (SendInput предотвращен focus guard), дефект в `TextInjector` или `Win32Input` не подтвержден.
- **Baseline:** базовый набор тестов (**256 passed, 2 skipped**) в этой проверке не перезапускался.
- **Статус ворот:** Native Gate 8 находится в статусе **PARTIAL / OPEN**.
- **Поддержка Windows приложения НЕ готова.**

### Натурные launcher-ворота L/R/T и устранение дефекта транскрибера (2026-11-04)

По явному разрешению пользователя продолжены открытые gates натурной верификации Windows.

#### 1. Натурные launcher-ворота L/R/T на старом установленном runtime этапа 5
Проверка проведена на существующем установленном бинарнике `typr-gui.exe` этапа 5:
`C:\Users\smale\AppData\Local\Temp\kilo\typr-stage5-verify-30225342fbd746ee88fbf361606abdc2\runtime\Scripts\typr-gui.exe` (CPython 3.15.2 x64, установленный wheel `typr==0.4.0`, `sounddevice==0.5.6`, `cffi==2.1.1`, `PyQt6==6.12.0`). **Важно:** проверка выполнялась на СТАРОМ установленном runtime, а НЕ на новом коде транскрибера.

- **Механизм запуска и изоляции (contained scope):**
  - Запуск через внешний оркестратор `gate.py` с флагом `creationflags: DETACHED_PROCESS` без перенаправления и присвоения дескрипторов `stdout`/`stderr`.
  - Child-only bootstrap: изоляция подключается через `PYTHONPATH` дочернего процесса (`bootstrap/sitecustomize.py`, `bootstrap/native_gate_probe.py`), который перехватывает окружение до создания `QApplication` и импорта приложения.
  - Наблюдение консольных потоков: `sys.stdout is None` и `sys.stderr is None` зафиксированы на всех стадиях: до импортов (`stdout_none_early`, `stderr_none_early`), во время работы GUI (`stdout_none_running`, `stderr_none_running`) и при выходе (`streams_still_none`).
   - Логирование: штатный логгер без подмен использует `FileHandler` строго в изолированном профиле (`native_logger_file_only: true`), консольные хэндлеры отсутствуют.
  - Изоляция окружения: `HOME`, `USERPROFILE`, `LOCALAPPDATA`, `APPDATA` направлены в `<run>\profile`; `TMP`, `TEMP` — в `<run>\tmp`; рабочий каталог (`cwd`) — `<run>\Рабочая папка Unicode`. Секреты и пользовательские файлы не читались.
  - Аудит-хук сети: процессный `sys.addaudithook` блокирует известные сокетные функции Python (`socket.connect`, `socket.bind`, `socket.getaddrinfo`, `socket.sendto`, и т.д.); это защита на уровне Python runtime, а не сетевой экран операционной системы.
  - Жизненный цикл: исполняется настоящий продакшен-код (`main()`, `start()`, `quit()`, `_finish_quit_when_injection_closed()`, `finally`-очистка в entrypoint).

- **Проверенные кейсы и результаты (все три PASS, exit 0):**
  - **Case L (Idle launcher):** штатный запуск `typr-gui.exe`, видимый трей, регистрация глобального хука `Ctrl+Alt+Z`, пустой API key, отключенная история, изолированный конфиг сохранен; штатный запрос на выход через сигнал иконки трея (`quit_requested_via_tray_signal: true`) -> штатный вход и выход из cleanup в entrypoint -> чистый выход всех воркеров (`audio_actual_exit`, `hook_actual_exit`, `injection_cleanup_complete`). Аудио-чанки не генерировались (`audio_chunk_count: 0`).
  - **Case R (Recording shutdown gate):** штатный запрос на старт записи принят; с реального микрофона получен первый непустой аудио-чанк (`real_audio_chunk_nonempty: true`, `audio_chunk_count: 1`); в момент активной записи (`RECORDING`) запрошен выход через сигнал трея (`recording_active_at_quit: true`, `controller_recording_at_quit: true`) -> штатный барьер завершения дождался фактической остановки потока записи (`audio_actual_exit: true`) и деинициализации подсистемы sounddevice/PortAudio. Это новый gate остановки записи при активном потоке, а не повторение микрофонного baseline.
  - **Case T (Typing timer shutdown gate):** симуляция фиктивного завершения транскрипции (fake fixed completion) -> запрос на вставку принят контроллером (`injection_request_accepted: true`), приложение перешло в `TYPING`, запущен таймер ожидания отпускания клавиш вставки в бекенде (`backend_request_pending: true`); в момент активного таймера до истечения задержки инициирован выход через трей (`controller_typing_at_quit: true`) -> операция ожидания отменена (`pending_backend_cancelled: true`), выход произошел строго ДО публикации в буфер обмена и ДО отправки `SendInput` (`publication_attempts: 0`, `sendinput_attempts: 0`), без реальной вставки (`no_injection_callback: true`).

- **Сводные показатели L/R/T:**
  - Сетевые попытки: `network_attempts: 0`;
  - Непредвиденные вызовы транскрибера: `unexpected_transcribe: 0`;
  - Попытки публикации в буфер: `publication_attempts: 0`;
  - Попытки вызова SendInput: `sendinput_attempts: 0`;
  - Ошибки: `errors: []`;
  - Освобождение ресурсов: нативный GUI, микрофон и хуки корректно освобождены (`all workers actual exit: true`).
   - Исключение сценария P (Paste target focus): сценарий передачи фокуса в собственное окно `QTextEdit` исключен из-за остаточного риска гонки фокуса в Windows. Причина таймаута фокуса в предыдущем consoleless smoke не установлена; production-дефект не подтвержден.

- **Артефакты проверки:**
  - Каталог: `C:\Users\smale\AppData\Local\Temp\kilo\typr-lrt-20261104-0755`;
  - Файлы: `gate.py`, `bootstrap\sitecustomize.py`, `bootstrap\native_gate_probe.py`, `static.json`;
  - Прогоны: `run-L-95dbd8992dde4e15a5f83fb9bd8288c2` (L, PASS), `run-R-6c7a9b3560314d5f90ff122ef627e863` (R, PASS), `run-T-c061ca4adc63416e83b8a54c629d05a0` (T, PASS);
  - Манифесты и результаты проверены родительским процессом (parent read).
  - Команды: `& $python -I -B gate.py` (статический preflight PE, entrypoints, AST, audit hook self-check) и `& $python -I -B gate.py --case <L|R|T>`.
  - Граница применимости: Launcher PASS относится исключительно к ограниченному тестовому контуру (contained / instrumented bootstrap). Приемка несконфигурированного продакшен-лаунчера `typr-gui.exe` со сквозным вызовом реального endpoint остается **OPEN**.

#### 2. Выявление дефекта и исправление жизненного цикла транскрибера (FLS exit probe & barrier)
- **Подтвержденный дефект в исходном коде:**
  - `WhisperTranscriber` испускал сигнал результата транскрипции до закрытия контекста HTTP-клиента (`httpx.Client.close()`);
  - `TyprApp` не включал воркер транскрибера в барьер выхода (`_finish_quit_when_injection_closed` проверял `text_injector`, `audio_recorder`, `settings_dialog`, но не `transcriber`).
  - Данный факт не противоречит историческому smoke "дефектов нет", так как в натурном smoke транскрипция была отключена (`SMOKE_TRANSCRIPTION_DISABLED`).
- **Опровержение достаточности `wait(0)` на Windows (Qt 6.12.0):**
  - Экспериментальный тест на Windows 11 с Qt 6.12.0 показал, что после завершения метода `run()` вызов `QThread.wait(0)` возвращает `True`, а `QThread.isRunning()` — `False`, тогда как поток ОС все еще выполняет деструкторы и коллбеки FLS (Fiber Local Storage) / TLS.
  - Проверка собственного нативного хэндла потока: `WaitForSingleObject(handle, 0)` возвращает `258` (`WAIT_TIMEOUT`).
- **Реализованное архитектурное решение:**
  - Модуль `src/typr/platforms/windows_thread.py`: обертки Win32 API (`OpenThread`, `WaitForSingleObject`, `CloseHandle`) с правами `SYNCHRONIZE`.
   - `TranscriberWorker`: до HTTP-запроса открывает собственный нативный хэндл через `OpenThread(SYNCHRONIZE, False, GetCurrentThreadId())`. Данные передаются отдельными worker-сигналами `result(str)` и `error(str)`; стандартный `QThread.finished` сохранен для уведомления о завершении Qt-потока.
   - Фасад `WhisperTranscriber`: перехватывает сигналы воркера в queued slots, но удерживает результат до полного нативного выхода потока и закрытия `httpx.Client`. После получения `QThread.finished` фасад проверяет `worker.wait(0)` и нативный хэндл (`WaitForSingleObject(handle, 0) == WAIT_OBJECT_0`), повторяя неподтвержденную проверку через таймер (10 мс). Только после подтверждения ядром ОС хэндл закрывается, ссылка на воркер освобождается, вызывается `deleteLater()` и публикуется публичный сигнал `transcription_complete` или `transcription_error`.
  - Reentrant & Busy: reentrant completion может сразу запустить новую транскрипцию без взаимного наложения или потери нового воркера; устаревшие события отбрасываются по identity отправителя.
  - Терминальный `cleanup()`: идемпотентный метод запрещает новые задачи, подавляет поздние результаты, не блокирует Qt thread и не делает force kill; текущий HTTP-запрос завершается естественным путем по тайм-аутам, после чего воркер закрывает transport. `is_cleanup_complete()` возвращает `True` только после фактического выхода воркера.
  - Барьер выхода в `TyprApp`: предикат `self.transcriber.is_cleanup_complete()` добавлен в `_finish_quit_when_injection_closed()` и вызов cleanup в блоке `finally` shutdown.
  - Linux: задокументирован контракт `wait(0)`, нативная верификация Linux остается **OPEN**.
  - Fail-closed обработка ошибок:
    - Сбой `OpenThread` отменяет HTTP-запрос до старта и логируется; воркер удерживается, shutdown блокируется с диагностикой `Shutdown blocked: native thread exit unverified` (без ложного pass).
    - Сбой таймера зонда диагностируется с подавлением дубликатов, повторные попытки продолжаются.
    - Сбой `CloseHandle` после подтвержденного выхода логируется как утечка ресурсов, но не срывает барьер выхода (выход потока уже доказан).
  - Неизменность сетевых параметров: HTTP payload, endpoint, timeouts и отсутствие принудительного обрыва запроса сохранены; естественный timeout может задерживать shutdown приложения без фиксированного общего дедлайна.
- **Измененные файлы:**
  - `src/typr/app.py`, `src/typr/core/transcriber.py`, `src/typr/platforms/windows_thread.py` (новый), `tests/test_app.py`, `tests/test_transcriber.py`, `tests/test_windows_thread.py` (новый), `docs/ARCHITECTURE.md`.
- **Результаты тестов и проверок:**
   - Полный набор тестов исходного кода через изолированный `verify_tests.py`: **280 passed, 2 skipped** (Linux installer shell tests; повторный прогон 2.59 с), новый baseline по сравнению с 256 passed этапа 5 и 232 passed этапа 4.
  - Scoped ruff: все файлы проверены, замечаний нет (`All checks passed!`).
  - `git diff --check`: чисто.
  - Независимое general-deep review: замечаний нет; targeted suite: **54 passed за 1.49 с** (включая реальные held FLS тесты нормального выхода и cleanup).
  - Снятие блокера `WinError 32`: сканирование корня репозитория обойдено запуском из внешней временной папки с абсолютными флагами `--rootdir`, `--confcutdir`, `--import-mode=importlib`.
- **Граница готовности пакета (историческая):**
  - Сборка wheel и чистая установка приложения этапа 5 исходно не пересобирались сразу после внесения изменений в транскрибер.
  - **Актуальный статус (post-fix package pass):** новый source wheel `typr-0.4.0-py3-none-any.whl` (32 файла, включая `windows_thread.py`) успешно пересобран и прошел полную чистую офлайн-установку (14 бинарных зависимостей + pip, итого 15 wheels), `pip check` (exit 0) и guarded imports (`typr.app`, `typr.__main__`) в Unicode+spaces каталоге с изолированным профилем. Также сквозная верификация WhisperTranscriber на новом установленном рантайме через `QCoreApplication` с синтетической тишиной (1.5 с WAV PCM 16k mono) и реальным HTTP 200 от локального GigaSTT подтвердила native thread exit probe (`WaitForSingleObject`, handle closed, worker reaped, cleanup == True). Пакетный сборщик и узкий transcriber probe — PASS; нативная сквозная проверка полного GUI-приложения и системный Gate 8 остаются PARTIAL / OPEN.

### Этап 6 — Автономный per-user инсталлятор Windows 11 x64 и интеграция локального Docker STT

**Статус (2026-11-07): реализация этапа 6 завершена; automated build PASS; package pass нового fix PASS; натурные ворота на чистой Windows 11 x64 — OPEN.**

Пользователь санкционировал утвержденное продолжение работ по Windows (этап 6). Реализованы скрипты сборки дистрибутива, мастера установки и деинсталлятора в каталоге `scripts/windows`. Раздел фиксирует утвержденный архитектурный контракт, область поставки и чеклист критериев приемки:
- Скрипт сборщика автономного дистрибутива (builder, `Build-Payload.ps1`): чистая пересборка source wheel Typr с актуальным исходным кодом (включая FLS-исправление транскрибера), проверка официального архива CPython 3.15.2 embeddable amd64 ZIP (скачивание опционально), использование заранее подготовленного wheelhouse бинарных зависимостей с проверкой SHA-256, компоновка автономного ZIP-пакета.
- Мастер установки (`Install.bat`, `Install.ps1` на Windows PowerShell 5.1): распаковка в `%LOCALAPPDATA%\Programs\Typr`, настройка embeddable runtime (изолированный `._pth`, исключающий влияние внешних сред), создание ярлыков в меню «Пуск» (`Typr`, `Uninstall Typr`), опциональный автозапуск через ярлык в папке Startup (строго с явного подтверждения пользователя, без прав администратора и без записи в реестр; ярлык на рабочем столе не создается).
- Интеграция локального STT в Docker: интерактивный выбор между Parakeet и GigaSTT (или внешним API), запуск с собственными per-user именами контейнеров `typr-win-<SID>-<kind>` и именованными томами `typr-win-<SID>-<kind>-models`, привязка строго к loopback `127.0.0.1`, отказ при конфликте портов/имен без перехвата чужих ресурсов, переиспользование кэша моделей хоста, запросы подтверждения на скачивание образов/моделей и UAC при необходимости, запрет скрытых правок WSL; для контейнеров действует политика `--restart no`, автозапуск Typr не запускает Docker/STT.
- Скрипт безопасного удаления (`Uninstall.bat`, вызывающий `Install.ps1 -Uninstall`): корректная очистка `%LOCALAPPDATA%\Programs\Typr`, ярлыков в меню «Пуск» и ярлыка автозапуска в Startup, с безусловным сохранением по умолчанию пользовательских данных в `%LOCALAPPDATA%\Typr` и томов моделей Docker (удаление томов требует явного `-RemoveModels`).

**Ворота готовности этапа 6 (Gate Checklist):**
- **Gate 6.1 (Builder):** сборка актуального wheel Typr, загрузка/проверка официального CPython 3.15.2 embeddable runtime ZIP, загрузка полного графа бинарных колес wheelhouse, компоновка полностью автономного ZIP-дистрибутива `Typr-Windows-x64-20261107-final.zip` (105 245 862 байт, SHA-256 `9c5e3614a3e09da58b2411c09a8ad6830e972d58722041734f7bf79d7286aaef`). (Статус: **PASS**)
- **Gate 6.2 (Offline per-user install):** установка и runtime во временном каталоге проверены; ярлыки и согласия проверены mocked harness. Установка в `%LOCALAPPDATA%\Programs\Typr` на чистой Windows без системного Python и реальные Start Menu/Startup остаются OPEN. (Статус: **TEMP / MOCKED PASS; clean Windows OPEN**)
- **Gate 6.3 (Docker local STT):** выбор пользователем Parakeet/GigaSTT; запуск контейнера строго на loopback-интерфейсе `127.0.0.1`; имена `typr-win-<SID>-<kind>`, тома `typr-win-<SID>-<kind>-models`; политика restart no; отказ при конфликте портов/имен; обнаружение и переиспользование кэша моделей; интерактивные подтверждения на скачивание/сборку (Parakeet commit `06464cd...`, SHA `fa58716...`, верифицировано скачивание архива без сборки; GigaSTT pinned digest `sha256:ac7f7ccb...`, live module PASS). (Статус: **PARTIAL (live Giga PASS; Parakeet unbuilt; end-to-end OPEN)**)
- **Gate 6.4 (Safe uninstall):** удаление управляемого дерева во временном каталоге с сохранением соседних данных проверено; ярлыки и сохранение моделей проверены mocked harness. Натурная приемка на чистой Windows остается OPEN. (Статус: **TEMP / MOCKED PASS; clean Windows OPEN**)
- **Gate 6.5 (E2E Integration & Smoke):** запуск установленного через инсталлятор Typr на чистой Windows 11 без системного Python; сквозная работа GUI/трея/PTT/вставки; взаимодействие с локальным Docker STT на loopback. (Статус: **OPEN**)

| Ворота | Область проверки | Результат / Доказательство | Статус |
| --- | --- | --- | --- |
| Gate 6.1 | Сборка офлайн-пакета (`Build-Payload.ps1`) | Сформирован `Typr-Windows-x64-20261107-final.zip` (105 МБ, SHA-256 `9c5e3614...`), полный граф зависимостей, pip check PASS, Verify-Runtime PASS | **PASS** |
| Gate 6.2 | Per-user установка | Temp install, embedded runtime, private fresh config PASS; recovery и shortcuts mocked PASS; чистая ОС и реальные ярлыки не проверены | **TEMP / MOCKED PASS; clean Windows OPEN** |
| Gate 6.3 | Локальный Docker STT (loopback 127.0.0.1) | GigaSTT live module PASS (`typr-win-<SID>-gigastt`, `/ready` + `/health` rnnt, repeat same ID); Parakeet archive SHA-256 verified download only (unbuilt) | **PARTIAL** |
| Gate 6.4 | Безопасное удаление | Temp managed tree удалено, соседние данные сохранены; shortcuts и model preservation mocked PASS | **TEMP / MOCKED PASS; clean Windows OPEN** |
| Gate 6.5 | Сквозной E2E smoke на чистой Windows 11 x64 | Запуск без системного Python, видимый GUI/трей, физический PTT, вставка и локальный STT | **OPEN** |

## 4. Чеклист верификации и критерий готовности

### 4.1. Автоматизированные проверки
- **PASS на Windows CPython 3.15.2 x64:** isolated sdist/wheel, full binary download, clean full install и pip check без `--no-deps`/stubs; gates 1–5 этапа 5.
- **PASS:** installed imports из Unicode+spaces cwd с изолированным профилем и удаленным PYTHONPATH, без audio module/native init; gates 6–7.
- **PASS на Windows:** полный applicable pytest актуального исходного кода **280 passed, 2 skipped** и scoped ruff (новый baseline; исторические срезы: 256 passed этапа 5, 232 passed этапа 4); targeted suite **54 passed** за 1.49 с (включая реальные FLS-пробы транскрибера).
- **HISTORICAL (superseded):** пересборка wheel и чистая установка пакета этапа 5 исходно не выполнялись сразу после исправления транскрибера. **Актуальный статус:** новый source wheel пересобран, чистая офлайн-установка полного графа зависимостей wheelhouse, `pip check` (exit 0) и guarded imports — PASS; сквозной HTTP-вызов транскрибера на тишине подтвердил native thread exit probe — PASS.
- **OPEN на Linux:** полный suite и native regressions; Git Bash syntax check их не заменяет.
- **Этап 6 (Windows installer & Docker STT):** Gate 6.1 PASS; Gates 6.2, 6.4 TEMP / MOCKED PASS (чистая ОС и реальные ярлыки OPEN); Gate 6.3 PARTIAL (live GigaSTT PASS, Parakeet unbuilt); Gate 6.5 OPEN. Финальный полный suite: **284 passed, 2 skipped**.

### 4.2. Натурный Smoke Checklist (требует отдельного разрешения)
- **Contained PASS (натурные проверки в ограниченном/инструментированном контуре):**
  - **Натурный smoke ContainedApp в обычном режиме (exit 0):** видимый GUI Qt/tray/settings/history из Unicode+spaces cwd; нативная запись с реального микрофона в память (~2 с WAV PCM 16-bit 16k mono); регистрация/снятие хуков `WH_KEYBOARD_LL`; зарегистрированный Ctrl+V-зонд не выдал PTT при синтетической вставке (доставка synthetic events в callback и их фильтрация непосредственно не наблюдались); вставка Unicode через SendInput в собственное окно `QTextEdit` с focus guard; сохранение текста в буфере обмена; чистый выход всех воркеров.
  - **Натурные launcher-ворота L/R/T (typr-gui.exe на старом runtime этапа 5, exit 0):**
    - Case L (idle launcher): запуск без консоли (DETACHED_PROCESS), `sys.stdout`/`sys.stderr is None`, FileHandler only, выход по сигналу трея, чистый выход воркеров;
    - Case R (recording shutdown): получение первого реального непустого `audio_chunk` (`count: 1`) с микрофона, штатный выход в активном состоянии `RECORDING`, фактическая остановка потока записи и освобождение PortAudio;
    - Case T (typing timer shutdown): фиктивное завершение транскрипции, переход в `TYPING`, активный таймер ожидания отпускания клавиш, отмена операции и выход строго ДО публикации в буфер и SendInput;
    - Во всех кейсах: 0 попыток сети, непредвиденной транскрипции, публикации и SendInput; GUI, микрофон и хуки корректно освобождены.
- **Contained FAIL / historical diagnostic:**
  - **Натурный smoke ContainedApp в consoleless-режиме (harness pythonw.exe, exit 1):** таймаут фокуса окна вставки `FocusGuard` (`fg_own=false, pid_own=false, qtactive/focusOwn/visible=true`), точная причина не установлена (ограничения активации Windows — вероятная причина); SendInput предотвращен focus guard; production-дефект не подтвержден; остальные проверки и cleanup воркеров — PASS. Не является квалификацией `typr-gui.exe`. В проверках L/R/T сценарий P исключен для устранения focus race.
- **OPEN (release / uninstrumented / full):**
  - Старт и работа `typr-gui.exe` без консоли из cwd с Unicode/пробелами в пути как полноценного приложения без инструментального сдерживания (uninstrumented);
  - HISTORICAL: пересборка wheel и чистая установка приложения этапа 5 (новый source wheel пересобран, чистая установка полного графа зависимостей PASS; uninstrumented GUI запуск остается OPEN);
  - Сквозная транскрипция с реальным endpoint и обработка сетевых/API ошибок;
  - Физический PTT (реальные нажатия пользователем на клавиатуре, удержание, release);
  - Физические раскладки клавиатуры (RU/EN) и AltGr;
  - Игнорирование duplicate down на физических клавишах;
  - Освобождение модификаторов в реальных пользовательских условиях;
  - Вставка в сторонние приложения (ввод в privileged/elevated окна и Secure Desktop/UAC является неподдерживаемым non-goal по разделу 2.3);
  - Session reset, lock / unlock рабочих станций Windows;
  - Device privacy toggles в настройках Windows 11;
  - Hotplug / unplug recovery аудиоустройств;
  - Завершение работы приложения во время активной транскрипции с реальным сетевым запросом;
  - Базовый нативный регресс Linux (Wayland и X11: PTT через evdev, uinput вставка, восстановление через wl-copy/xclip, shell tests);
  - Сквозной натурный smoke автономно установленного Typr без системного Python с локальным Docker STT (Gate 6.5).

### 4.3. Критерий готовности и открытые ворота
- Поддержка принимается только если согласованные contracts реализованы, applicable automation и desktop smoke пройдены на обеих ОС без прав admin.
- Пользовательские данные и секреты сохранены, UI остается отзывчивым, непроверенное честно указано в отчете.
- Hardware/GUI проверки требуют отдельного разрешения, тестового endpoint и фиктивных секретов.
- Этап 5 и post-stage 5 проверки: gates **1–7 PASS**, gate **8 PARTIAL / OPEN**. Packaging/import для существующего Python 3.15.2 подтверждены; частичный натурный smoke и launcher-ворота L/R/T выполнены в ограниченном контуре; полная native/release qualification minor открыта.
- **Поддержка Windows приложения все еще НЕ готова.**
- **Полный перечень открытых ворот и непроверенных сценариев:**
  1. Сквозная транскрипция с реальным endpoint и обработка сетевых/API ошибок;
  2. Физический PTT (реальные нажатия пользователем на клавиатуре, удержание, release);
  3. Физические раскладки клавиатуры и AltGr;
  4. Session reset, lock / unlock рабочих станций Windows;
  5. Device privacy toggles в настройках Windows 11;
  6. Hotplug / unplug recovery аудиоустройств;
  7. Завершение работы приложения во время активной фазы транскрипции с реальным HTTP-запросом;
  8. Квалификация продакшен-лаунчера `typr-gui.exe` без инструментального bootstrap и сдерживания;
  9. HISTORICAL (superseded по сборке пакета): пересборка wheel и чистая установка приложения с новым кодом транскрибера (узкий package pass и HTTP silence probe выполнены; сквозной GUI/uninstrumented runtime и Gate 8 остаются OPEN);
  10. Полная релизная квалификация Python minor;
  11. Полный нативный регресс Linux (evdev, uinput, clipboard, installer shell checks);
  12. Per-user установка и деинсталляция на чистой Windows 11 без системного Python (Gate 6.1 сборка PASS; Gates 6.2, 6.4 натурная приемка OPEN);
  13. Интеграция и сквозной запуск локального Docker STT на loopback с верификацией моделей и портов (Gate 6.3 PARTIAL: live GigaSTT module PASS, Parakeet unbuilt; end-to-end OPEN);
  14. Сквозной E2E smoke автономно установленного Typr с локальным Docker STT (Gate 6.5).
- Действуют строгие ограничения: запрещена установка новых версий Python без согласования, запрещены несанкционированные GUI и hardware тесты, запрещены git commit и git push.

## 5. Отложенные задачи (Deferred)

Следующие задачи не входят в утвержденный объем и требуют отдельного решения при необходимости:
- Standalone сборка через сторонний freezer (PyInstaller/one-dir bundle) и внешние инсталляторы (Inno Setup / WiX) — не требуются благодаря официальному embeddable runtime ZIP и встроенному PowerShell-мастеру установки.
- Настройка автозапуска через системный или пользовательский реестр (Run keys) — отложена в пользу безопасного ярлыка в пользовательской папке Startup.
- Иконка `.ico`, PE metadata (file/product version), подпись Authenticode и SmartScreen reputation.
- Полноценный snapshot и надежный restore сложных форматов буфера обмена (HTML/RTF/OLE) с учетом TOCTOU.
- Системный межпроцессный мьютекс (`CreateMutexW`) для блокировки повторного запуска.
- Полноценный workflow отмены записи (Cancel hotkey).
- Настройка матрицы Windows в GitHub Actions CI.

