# План реализации поддержки Windows 11

## Статус и правила исполнения

Это **план будущих изменений**, а не описание работающей Windows-версии. Baseline ниже установлен чтением репозитория; запуск приложения, устройств и Windows/Linux runtime не выполнялся при подготовке документа. Действующая архитектура описана в [ARCHITECTURE.md](ARCHITECTURE.md), правила синхронизации — в [DOCUMENTATION_POLICY.md](DOCUMENTATION_POLICY.md).

Документ предназначен координатору и исполнителям отдельных этапов:

- Агент выполняет **только явно порученный этап**, а не весь план. Наличие плана не разрешает запуск GUI/устройств, установку пакетов, изменение системы, создание сессий, commit или push.
- Перед работой прочитай актуальные `AGENTS.md`, skill `typr-codebase`, этот план и файлы порученной области. Зафиксируй исходный diff и сохрани чужие правки.
- Координатор утверждает архитектуру, thread/clipboard semantics, зависимости и системные разрешения; исполнитель выбирает локальную реализацию внутри утвержденного контракта. Не расширяй область записи и не меняй контракт без согласования: верни факты, варианты, рекомендацию и blocker.
- Пути будущих файлов ниже — предлагаемые области записи для поручений, не свидетельство их существования и не самостоятельное разрешение их создавать. Точный список новых файлов закрепляет координатор после этапа 0.
- У каждого файла один писатель. Этапы идут последовательно с приемкой; review — read-only после завершения автора. Общие `app.py`, config, UI, tests и docs не редактируются параллельно разными исполнителями.
- Отчет каждого исполнителя: результат, измененные пути, принятые локальные решения, команды и результаты проверок, непроверенное и блокеры. Чтение кода и mocked tests не выдавай за desktop/runtime-проверку.

## Цель и non-goals

Обеспечить нативную работу tray-first клиента Typr на Windows 11 и сохранить Linux Wayland/X11: удержание хоткея → запись → Whisper-compatible HTTP transcription → history → Unicode paste → готовность к следующей записи. Одна кодовая база и одна линия разработки, общие UI, audio, transcription и history; отдельные OS build artifacts одной версии.

Не входят в реализацию: WSL, Docker, поставка/запуск STT server, модели и GPU runtime; Typr остается клиентом отдельно подготовленного backend. Не требуются macOS, новый UI framework, универсальная plugin-система, посимвольная эмуляция текста, обход UIPI/UAC, постоянный запуск от администратора, legacy-адаптеры внутренних API или переработка Linux shell installer. Не добавлять поддержку live streaming или cancel-hotkey только потому, что соответствующие поля уже есть в config: отдельное изменение поведения требует поручения.

## 1. Фактический baseline

Срез исходного дерева при подготовке плана: версия `0.4.0`. Перед реализацией перечитай текущие файлы: номера строк и детали могут измениться.

| Область | Файлы и фактическое поведение | Следствие для Windows |
| --- | --- | --- |
| Lifecycle | `src/typr/__main__.py` создает `QApplication`; `src/typr/app.py` напрямую создает `HotkeyManager` и `TextInjector`, связывает Qt signals; состояния `IDLE/RECORDING/TRANSCRIBING/TYPING/ERROR` | Нужна точка выбора OS backend без ветвления всей state machine |
| Hotkeys | `src/typr/core/hotkey_manager.py`: evdev, `/dev/input/event*`, reader thread и периодический hotplug scan; repeat value `2` не запускает запись повторно; отпускание target или требуемого modifier останавливает запись; дополнительные modifiers допускаются | Нельзя заменить PTT одноразовым уведомлением `RegisterHotKey`; Linux поведение закрепить tests до выделения адаптера |
| Injection | `src/typr/core/text_injector.py`: evdev `UInput`, Shift+Insert, `wl-copy/wl-paste`, `xclip/xsel`; backup только текста, restore по сравнению текущего текста с вставленным; QTimer и ownership helper process, cleanup | Нет сохранения произвольных clipboard formats и нет надежной идентификации копирования того же текста пользователем. Это ограничение baseline, не гарантия полного restore |
| Блокирующие места | `app.py::_on_transcription_complete` синхронно вызывает `type_text`; injector использует `sleep`, subprocess read/write/wait; `audio_recorder.py` открывает stream в `start_recording`, делает join/stop/close в `stop_recording` | Архитектурный инвариант неблокирующего pipeline еще нельзя считать доказанным для этих мест. Нельзя механически перенести их в Windows Qt slots |
| Audio | `src/typr/core/audio_recorder.py`: общий PyAudio/PortAudio, PCM int16 → WAV, reader thread; `input_device=None` выбирает default, иначе поиск по имени с fallback на default | Заголовок про PipeWire не доказывает Linux-only реализацию. Проверить Windows wheels, host APIs, частоты, default/device changes; не заменять весь audio stack заранее |
| HTTP | `src/typr/core/transcriber.py`: worker `QThread`, multipart WAV на `/audio/transcriptions`, connect/read timeouts, настройка model/language/prompt | Сохранить общий клиент и существующие endpoint/error contracts; не связывать Windows package с локальным сервером |
| Config | `src/typr/config.py`: пути `~/.config/typr`, tolerant loading, backup `.json.bak`, temp + replace, `chmod(0600)`, блокировка save после ошибки чтения | POSIX mode не является Windows ACL. Путь загрузки и поля пути сохранения сейчас заданы отдельно: заменить согласованно |
| History/logs | `src/typr/core/history.py`: import-time `~/.local/share/typr/history.json`, JSON temp + replace, retention; после ошибки разбора history становится пустой в памяти. `src/typr/utils/logger.py`: import-time создание `~/.config/typr/logs/typr.log`, stdout handler | Не допустить перезаписи поврежденной history при следующем add/trim; устранить нежелательные import-time записи и учесть отсутствие stdout в GUI launcher |
| UI | `src/typr/ui/settings_dialog.py`: `QKeySequenceEdit`, сериализация shortcut через `toString`, перечисление audio devices; `history_dialog.py` копирует через Qt clipboard; `tray_icon.py` рисует state icons через QPainter | Проверить portable shortcut notation и single-chord validation; history Copy тоже участвует в clipboard races. Сохранить общий UI; строки в `utils/i18n.py` менять одновременно RU/EN |
| Package/install | `pyproject.toml`: hatchling, Python >=3.10, PyQt6/PyAudio/httpx/websockets, безусловный evdev; `typr` и `typr-gui` entrypoints; wheel включает `src/typr` | Условные зависимости, проверка состава ресурсов и Windows GUI launcher; Windows frozen build еще не задан |
| Linux integration | `install.sh`, `uninstall.sh`, `resources/org.typr.desktop`, `resources/typr.desktop`, SVG в `resources/icons/`; installer настраивает venv, desktop/autostart, input/uinput permissions, умеет отдельно готовить STT | Не запускать и не переписывать installer для Windows. Существующую Linux интеграцию и подтверждения удаления данных сохранить |
| Version/CI/tests | `scripts/bump_version.py` синхронизирует pyproject, `src/typr/__init__.py`, RU/EN About и README badge; `tests/test_project_skills.py` проверяет версии и docs map. В исследованном дереве `.github` workflow не найден | CI нужно добавить явно; не заявлять существующий Windows CI. Build metadata обеих OS получать из одной версии |

Прочитанные существующие tests: `tests/test_text_injector.py` (helper replacement, новое clipboard content, cleanup), `test_settings_dialog.py` (defaults и mocked HTTP discovery/probes), `test_transcriber.py` (timeouts/errors), `test_installer.py`, `test_uninstaller.py` (изолированные shell mocks), `test_project_skills.py`. Отдельных suites hotkey, audio lifecycle, app state, config/history persistence в исследованном дереве нет. Это пробелы покрытия, не доказательство неисправности runtime.

## 2. Утвержденные архитектурные контракты

### 2.1. Границы и потоки

1. Одна кодовая база. OS-маркеры зависимостей (`sys_platform == 'linux'` для evdev); Windows не импортирует Linux backend и наоборот. Отсутствующий обязательный backend дает понятную ошибку/degraded capability, не production-заглушку и не silent fallback.
2. Узкие платформенные адаптеры: global hotkeys; text injection/clipboard; стандартные пути и установка/desktop integration. Общие `TyprApp`, UI, PyAudio pipeline, transcription и history остаются общими. Выбор backend централизован; не распространять `if Windows` по бизнес-логике.
3. Hotkey backend публикует start/stop/error через queued Qt boundary и не управляет audio/network. Hook callback короткий: обновить минимальное состояние/поставить событие в очередь, передать дальше hook chain; без I/O, sleep, логирования каждого key event, clipboard, join и работы UI.
4. Длительные операции audio, subprocess и input выполняются вне Qt main thread и reader/hook callback. **Все обращения к Qt clipboard/QMimeData и их уничтожение — только Qt main thread**; ожидания, retries и delay — через события/таймеры, не sleep. Нельзя просто перенести весь `TextInjector` в worker вместе с Qt clipboard.
5. Для вставки нужен неблокирующий запрос с явным завершением/ошибкой, идентификатором операции и отменой при shutdown. `TYPING` не заканчивается сразу после enqueue; успех означает отправку paste gesture, а не подтвержденное содержимое чужого документа. Отдельный delayed restore не удерживает UI в `TYPING`. Точную сигнатуру сигналов фиксирует этап 0.
6. Один активный pipeline; повторные start/stop, late completion и callback старой операции не создают параллельную запись или вставку. Cleanup идемпотентен: stop timers, invalidate operation tokens, unhook/stop message loop, закрыть устройства/helpers/streams; после cleanup нет новых UI callbacks или синтетических нажатий.

### 2.2. Hotkeys

- Linux сохраняет evdev reader/hotplug и uinput semantics. Выделение адаптера не меняет требование прав и поведение нажатия/отпускания.
- Windows: Win32 low-level keyboard hook (`WH_KEYBOARD_LL`) с собственным живым message loop и удерживаемой ссылкой на callback; корректные pointer-size types, lifetime и `UnhookWindowsHookEx`. `RegisterHotKey` не заменяет release-семантику.
- Одно событие start при press target с требуемыми modifiers, дополнительные modifiers разрешены, autorepeat игнорируется. Один stop при release target или утрате требуемого modifier. Хранить физические left/right states, чтобы отпускание одного из двух Ctrl не означало утрату Ctrl, пока второй удерживается; проверить AltGr и system-key сообщения.
- Собственные injected paste events не должны запускать PTT; правила обработки сторонних injected events и hotkey normalization утверждаются на этапе 0. Не перехватывать/подавлять пользовательские клавиши без отдельного решения.
- При update shortcut, потере desktop/session, ошибке hook и cleanup сбрасывать pressed state и завершать/отменять текущую запись по согласованному lifecycle, без зависшего recording. Reserved/system combinations отвергать либо явно показывать ограничение; надежность каждой комбинации не обещать.

### 2.3. Clipboard и paste

- Вставка Unicode только через clipboard + paste gesture; никакого layout-зависимого посимвольного ввода. Windows gesture — через `SendInput`, с проверкой числа отправленных событий, корректными down/up и учетом уже удерживаемых modifiers. Не отпускать реальные клавиши пользователя ради удобства реализации; при конфликте ограниченно отложить вставку или завершить явной ошибкой по контракту этапа 0.
- Snapshot непосредственно перед публикацией текста, а не в начале записи/transcription. Не логировать clipboard payload. Каждая операция владеет собственными snapshot, generation/token и restore timer; новая вставка не может восстановить clipboard из старой операции поверх нового.
- Restore допускается только при доказательстве, что clipboard все еще принадлежит данной публикации Typr. Для Windows исследовать sequence number (`GetClipboardSequenceNumber`) вместе с собственным generation и уведомлениями Qt; **сравнения текста недостаточно**, включая повторное копирование пользователем того же текста. History Copy и clipboard manager считаются внешней заменой.
- При любой внешней замене, неоднозначности ownership, ошибке чтения/занятости clipboard — отменить restore, не очищать пользовательское содержимое. Guard должен действовать и на failure/cleanup path. Проверку ownership и запись нельзя объявлять атомарными на основании двух раздельных Qt вызовов: этап 0 обязан оценить TOCTOU и утвердить защищенную native-секцию либо честное ограничение/консервативную политику отключения restore. Не смешивать несогласованные native/Qt owners.
- Baseline Linux сохраняет **только текст**, не HTML/RTF/images/files. Сохранение всех Windows formats не обещается: delayed rendering, нестандартные форматы и QMimeData lifetime требуют исследования. Этап 0 фиксирует поддерживаемый snapshot (включая empty/non-text), поведение при неподдерживаемом содержимом и предупреждение пользователю. Нет безопасного snapshot — не делать вид, что backup успешен; безопасный вариант отказа от временной подмены предпочтительнее потери данных.
- Для медленного приложения задержка restore — bounded policy, не доказательство получения paste. У Windows clipboard busy retries ограничены по времени и отменяемы. Linux text-only/equality ограничения документировать отдельно; их исправление сверх безопасного выделения backend требует отдельного согласования, не скрытого изменения Linux semantics.

### 2.4. Права, аудио и данные

- Обычный процесс запускается без admin. `SendInput` ограничен UIPI; elevated target, secure desktop/UAC, lock screen и системные комбинации не поддерживаются как обычный paste target. Не обходить ограничения и не предлагать постоянное повышение прав. Ошибка должна сохранять транскрипцию в history при включенной history и оставлять доступным явное Copy; нулевой/частичный SendInput не доказывает причину UIPI, диагностика не должна утверждать ее без оснований.
- Сохранить общий WAV/HTTP contract. Проверить разрешение Windows «Microphone access» и «Let desktop apps access your microphone», отсутствие/занятость input, default input vs communications device, смену default между записями, удаление устройства во время записи, sleep/resume. Не фиксировать PortAudio index как стабильный ID и не обещать автоматическое переключение посреди записи. Ошибка → закрытие stream → управляемый recovery.
- Linux пути остаются прежними. Для Windows утвердить разрешение Known Folder LocalAppData (например, корень `%LOCALAPPDATA%/Typr`: `config.json`, `history.json`, `logs/typr.log`); пути не зависят от cwd, installation directory или привилегий. Точный resolver, тестовая инъекция путей и поведение при недоступном каталоге утверждаются до кода.
- Config, `.bak` и временный файл содержат API key. На Linux сохранить `0600`; на Windows проверить private user directory/DACL и доступ к каждому файлу, включая backup/temp, **до записи секрета**. `chmod(0600)` не заменяет DACL. Не обещать защиту от администраторов; DPAPI/Credential Manager не добавлять без отдельного решения. При невозможности безопасного сохранения — явная ошибка, не запись в общий каталог.
- Atomic replace, tolerant loading, backup и запрет clobber после ошибки сохраняются. Защитить и существующую history от автоматической перезаписи после неуспешного чтения. Не скрыто сбрасывать/удалять данные и не делать auto-migration ради внутренних legacy API. Если найдены прежние пути/два набора файлов, остановить автоматический перенос, показать конфликт и согласовать явное копирование с backup; исходники данных не удалять.
- Tests используют временные HOME/USERPROFILE/LOCALAPPDATA и внедренный resolver до импорта модулей с побочными эффектами. Никакого чтения реальных config/history, публикации ключей, audio или clipboard contents в диагностике. History хранит только предусмотренную текстовую запись, не API key и audio.

## 3. Гипотезы и решения, требующие проверки

Утвержденные границы выше не означают, что конкретная Windows API связка уже проверена.

| Вопрос | Требуемое свидетельство перед зависимым этапом |
| --- | --- |
| Win32 binding: stdlib ctypes или узкая зависимость | Проверить API официальной документацией/установленными stubs, ABI x64, callback lifetime и cleanup. Координатор выбирает один вариант, не несколько framework layers |
| Shortcut representation и gesture | Проверить `QKeySequence` portable text, single chord, left/right, AltGr, RU/EN layout, reserved combos; определить Ctrl+V/Shift+Insert support в целевых GUI/terminal и конфликт удерживаемых keys |
| Ownership/restore | Описать порядок snapshot/write/token/sequence/restore, same-text copy, busy clipboard, TOCTOU, overlapping operations и shutdown. Если безопасный restore не доказан — blocker или согласованная консервативная политика, не заявление о сохранности |
| Clipboard formats | Проверить empty/text/non-text и cloning поддерживаемых formats; зафиксировать ограничения до включения restore по умолчанию |
| PortAudio/PyAudio | Проверить wheel для выбранной версии Python/Windows x64, host API, 16 kHz mono, микрофонные privacy settings, default и hotplug; отказать понятно при неподдерживаемом формате, не менять WAV contract незаметно |
| Пути/ACL | Временные каталоги и отдельный тестовый Windows user: Known Folder, Unicode path, temp/backup ACL, atomic replace при sharing violation; import без QApplication не создает реальные данные |
| Дистрибутив | Проверить Windows freezer с Qt plugins/PyAudio native libs, GUI launcher без stdout, icon/version metadata и per-user install. Выбрать один поддерживаемый способ после smoke, не обещать одновременно MSI/MSIX/portable |

## 4. Последовательные поручения

Зависимости: **0 → 1 → 2 → 3 → 4 → 5**. Это шесть связных этапов, не очередь автоматически запускаемых агентов. Для каждого координатор передает результат предыдущей приемки и точные write boundaries. Непройденный gate блокирует зависимую работу; не маскировать его mock-успехом.

### Этап 0 — подтвердить контракты и минимальный Windows маршрут

**Режим:** read-only исследование кода и официальных API; runtime probes только отдельным явным разрешением, на тестовых данных. **Запись:** только уточнение этого плана по поручению; production-файлы не менять.

**Задача:** разрешить вопросы раздела 3, выбрать Win32 binding и Windows build target (сначала Windows 11 x64 и одна проверенная Python minor из поддерживаемых), определить сигнатуры adapter signals/request/completion, stop/cancel при смене shortcut/session, clipboard format policy, пути/DACL, gesture и тестовые seams. Не создавать новый abstraction framework ради будущих платформ.

**Expected result/gate:** таблица решений с evidence и оставшимися blockers; точный согласованный перечень новых backend/test/build файлов. Координатор принимает thread/clipboard/security contracts перед реализацией. Невозможность runtime probe записать как непроверенное, а не закрывать предположением.

### Этап 1 — платформенные границы, безопасные пути и Linux characterization

**Область записи:** `pyproject.toml`; `src/typr/core/hotkey_manager.py`, `text_injector.py`; новый узкий пакет `src/typr/platforms/` (selector, paths, Linux backends по согласованному списку); `config.py`, `core/history.py`, `utils/logger.py`; минимальное wiring `app.py`/`__main__.py`. Tests: существующий `test_text_injector.py`, новые `test_platform_selection.py`, `test_hotkey_manager.py`, `test_config.py`, `test_history.py`, `test_paths.py`. Docs companions: `ARCHITECTURE.md`, `DEVELOPMENT.md`, этот план; корневой README только для подтвержденных пользовательских изменений.

**Задача:** сначала characterization tests Linux press/release/repeat/extra modifiers и clipboard/helper cleanup; выделить Linux реализации без изменения их внешнего поведения. Ограничить evdev Linux OS-marker, исключить импорт чужой платформы. Провести единый resolver через config/history/logs; сохранить Linux paths, безопасную Windows persistence и guard для поврежденной history. Не подключать еще неготовый Windows backend как успешную capability.

**Expected result:** Linux выбирает реальные evdev/uinput adapters, Windows import/install не требуют evdev; безопасные изолированные paths и ошибки, нет записи в настоящий HOME при tests/import. Tolerant/round-trip/backup/corrupt-file tests, unknown fields, неудачный replace/ACL, сохранность исходного файла. **Gate:** targeted tests и lint измененных Python файлов; Linux import/build и mocked regressions; Windows dependency resolution/import и ACL test на Windows. Реальный ввод не объявлять проверенным.

### Этап 2 — Windows PTT backend

**Область записи:** согласованные Windows hotkey файлы в `src/typr/platforms/`, selector и общий hotkey facade; `ui/settings_dialog.py`, `utils/i18n.py` для валидации/диагностики; `app.py` только lifecycle wiring, если утверждено этапом 0. Tests: `test_hotkey_manager.py`, новые `test_windows_hotkeys.py`, затронутый `test_settings_dialog.py`. Docs: `ARCHITECTURE.md`, README (permissions/combos), этот план.

**Задача:** hook + message loop, queued delivery, startup failure, pressed/modifier state machine, autorepeat, собственные injected events, update shortcut и остановка/cleanup. Не переносить audio/transcription в callback и не реализовывать Cancel как незаявленный новый workflow.

**Expected result:** один start/stop на PTT цикл; отсутствие зависшей записи при release modifier, смене shortcut, session loss и shutdown. **Gate:** mocked Win32 tests (normal/system key messages, left/right, AltGr, repeat, hook error, double cleanup, late callback), Linux regression suite и отдельно разрешенный Windows desktop smoke. Факт установки hook не доказывает работоспособность всех сочетаний.

### Этап 3 — неблокирующая вставка и clipboard lifecycle

**Область записи:** `core/text_injector.py`, согласованные injection/clipboard adapters в `src/typr/platforms/`, `app.py`; `ui/history_dialog.py` только для согласования Copy с ownership, `utils/i18n.py` для ошибок. Tests: `test_text_injector.py`, новые `test_windows_text_injector.py`, `test_app.py`, при необходимости согласованный `test_history_dialog.py`. Docs: `ARCHITECTURE.md`, README, этот план.

**Задача:** внедрить согласованный request/completion/error API, `SendInput` gesture, Qt-main-thread clipboard, tokens и restore policy. Убрать ожидания из UI path; Linux helper I/O вынести за main thread, сохранив backend selection, Shift+Insert, text-only ограничения и helper ownership. Новое поведение, выходящее за выделение/неблокирующий lifecycle, отдельно согласовать.

**Expected result:** `TYPING` завершается по результату, отказ вставки не теряет history; restore не затирает доказанное новое content пользователя, старый timer не меняет новую операцию. **Gate:** tests thread affinity, snapshot timing, text/empty/non-text policy, same-text copy, Copy из history, busy clipboard, частичный/нулевой SendInput, конфликт modifiers, новая вставка до restore, cancel/cleanup/late callbacks, failure после публикации; Linux helper regressions и responsiveness при медленных mocks. Ограничение TOCTOU отражено в принятом контракте и пользовательской документации.

### Этап 4 — общий audio/lifecycle и пользовательская Windows интеграция

**Область записи:** `core/audio_recorder.py`, `app.py`, `__main__.py`, `ui/settings_dialog.py`, `ui/tray_icon.py`, `utils/logger.py`, `utils/i18n.py`; config только при согласованной необходимости настройки. Tests: новые `test_audio_recorder.py`, `test_app.py`, затронутые settings/path tests. Docs: README, `ARCHITECTURE.md`, `DEVELOPMENT.md`, этот план.

**Задача:** проверить общий PyAudio на Windows; устранить blocking open/stop/join из Qt path по принятому lifecycle, не писать второй audio pipeline. Обработать default/no-device/privacy/unsupported-format/device-removal/resume и повторную запись после ошибки. Подготовить общий UI к понятным OS-specific capability errors, GUI launcher без stdout и корректному quit с активными workers. Не менять HTTP protocol/discovery и не добавлять тихий выбор другого микрофона вместо согласованной политики.

**Expected result:** быстрый press/release во время открытия stream не теряется, WAV публикуется только после завершения stream/thread; один терминальный результат/ошибка, отзывчивый UI и cleanup при ошибке. **Gate:** mocked audio/state tests с задержанным open/close, disconnect и shutdown; Windows microphone/default-device smoke и Linux audio regression по разделу 5. Любые изменения device fallback явно описаны и согласованы.

### Этап 5 — сборка, CI, эксплуатационная документация и приемка

**Область записи:** `pyproject.toml`, согласованные Windows build/installer scripts под `scripts/`, build resources под `resources/` (включая `.ico` и metadata), новые `.github/workflows/` и packaging tests; entrypoint/logger/UI только для обнаруженных и согласованных packaging defects. `README.md`, `docs/DEVELOPMENT.md`, `ARCHITECTURE.md`, `docs/README.md`, этот план. Linux `install.sh`/`uninstall.sh`/desktop entries — **не область записи по умолчанию**: при доказанной необходимости сначала новое поручение и обязательные installer companions.

**Задача:** выбрать один Windows deliverable после build spike (например, per-user installer с frozen one-directory bundle); включить Qt platform plugins, PortAudio/PyAudio native binaries и ресурсы; GUI launcher без консоли, понятные ошибки запуска и место логов. Установка/upgrade/uninstall не требуют постоянного admin и не удаляют config/history молча. Autostart только per-user, с явным согласием и обратимым отключением; корректно quote пути с пробелами/Unicode, не добавлять системную службу. Предотвратить два экземпляра из launcher/autostart либо явно блокировать конфликт hooks/clipboard по согласованному решению.

**Версия/artifacts:** одна версия из существующего механизма проекта, Windows PE/file/product version и installer берут ее автоматически, не вводят второй независимый счетчик. Не повышать версию ради выполнения плана; bump выполняется только при отдельно порученном commit по проектному workflow. Нативные Windows и Linux artifacts собираются на соответствующей OS из одного revision/version, имеют OS/arch в именах и checksums. Linux artifact может оставаться существующим Python package, не нужно изобретать Linux installer заново. Проверить содержимое wheel/sdist и frozen bundle; API key, config/history, `.venv`, caches/logs в них запрещены. Signing/SmartScreen reputation отдельно обозначить как ограничение unsigned build, не обещать отсутствие предупреждений.

**CI:** Windows + Linux jobs: чистая установка зависимостей, `pip check`, import без чужих OS libraries, targeted и full applicable pytest, lint измененного кода, `python -m build`, packaging checks. Linux shell regressions запускаются только на Linux; skip на Windows узкий и мотивированный, не skip всей core suite. Сначала изолировать HOME/USERPROFILE/LOCALAPPDATA до collection/import. GUI/signal tests только в разрешенной видимой сессии или согласованном CI display environment; обычный CI не подтверждает физические hotkeys/audio/paste. Не маскировать отсутствующие зависимости production stubs.

**Expected result/gate:** воспроизводимые отдельные artifacts одной версии, отчет matrix и ручная приемка обеих OS. README разделяет Windows и Linux install/permissions/autostart/uninstall; `DEVELOPMENT.md` содержит команды окружения и OS-specific tests; `ARCHITECTURE.md` описывает только уже принятую реализацию. План сохраняет явный статус выполненных/оставшихся этапов, не превращает будущие пункты в факты.

## 5. Финальная проверка Windows + Linux

Проводит координатор после интеграции и независимого read-only review. Разрешение на hardware/desktop проверки и тестовый endpoint должно быть получено отдельно; использовать фиктивные секреты и тестовые тексты. Проверять нативно на Windows 11 и Linux, а не выводить Windows support из чтения или mock suite.

### Автоматические проверки

- Через проектный `.venv`, если он существует: targeted suites каждого этапа и один полный applicable `pytest` после интеграции; `ruff check` измененных Python файлов. Repo-wide `ruff`/`mypy` — диагностика, старые findings отдельно от diff.
- Linux: существующие shell tests и `bash -n install.sh uninstall.sh` при изменении scripts; `install.sh --dry-run` только при подходящем Linux preflight и отдельной необходимости. На Windows Linux installer не запускать.
- Windows: реальные install/import/build с установленными Windows dependencies, mocked hook/SendInput tests, isolated persistence/ACL tests. Не считать monkeypatch `sys.platform` заменой Windows ABI/packaging проверке.
- Проверить dependency metadata на обеих OS, отсутствие evdev в Windows install, ресурсы, version consistency, старт packaged launcher из произвольного cwd и с путем с пробелами/Unicode. Build/test команды и разрешенные skips сохранить в отчете с OS/Python/revision.

### Ручная матрица в видимых desktop sessions

| Сценарий | Windows 11 | Linux Wayland и X11 |
| --- | --- | --- |
| Startup/UI | Обычный user, launcher без консоли, tray/settings/history, согласованный autostart on/off | Существующий launcher, tray и desktop/autostart без регрессии |
| PTT | Press/hold/repeat/release, ранний release modifier, оба Ctrl, AltGr, RU/EN, смена shortcut, reserved combos, lock/unlock | Те же базовые PTT циклы плюс keyboard disconnect/reconnect/hotplug и отсутствие input permission |
| Audio | Default/выбранный mic, no device, privacy denied, busy/unsupported format, смена default между записями, unplug во время записи, sleep/resume | Default/выбранный mic, unplug/error recovery; нет новых UI stalls |
| Pipeline | WAV → отдельно доступный compatible backend → history → paste; empty result, slow/offline/401/timeout, повтор после recovery | Тот же общий HTTP/state workflow, Settings Fetch/Test Connection остаются отзывчивыми |
| Paste | Unicode/emoji/multiline при RU/EN layout в обычном editor, browser field и terminal; elevated target и UAC — ожидаемые ограничения без обхода | GUI/terminal через прежний Shift+Insert, wl-clipboard и X11 backend; uinput/clipboard-tool errors |
| Clipboard | Text/empty/non-text по утвержденной policy, same-text copy, новое content до restore, Copy из history, быстрые последовательные операции, busy clipboard | Text-only baseline, новое content не затирается, helper restored ownership и cleanup |
| Shutdown/data | Quit во время RECORDING/TRANSCRIBING/TYPING/restore, нет живого hook или stuck synthetic keys; restart, upgrade/uninstall сохраняют данные и ACL | Нет оставшихся streams/readers/uinput/helpers/timers, прежние config/history paths и безопасное сохранение |

### Критерий готовности

Поддержка принимается только если согласованные contracts реализованы и покрыты tests/docs, обе OS прошли applicable automation и разрешенный desktop smoke, artifacts воспроизводимы и данные/ключи не раскрываются. Непроверенная OS, clipboard ownership race без принятой безопасной policy, зависшая запись, blocking UI, потеря данных или требование постоянного admin — **release blocker**, не «готово с обещанием проверить позже».

## 6. Риски и формат закрытия

Главные риски: Windows hook timeout/lifetime и пропущенный release; AltGr/удерживаемые modifiers; Qt/native clipboard ownership и TOCTOU; delayed/custom formats; UIPI без надежной причины ошибки; PortAudio host API и wheel availability; import-time path effects; ACL backup/temp; отсутствие Qt plugins в frozen bundle; unsigned SmartScreen warnings; Linux regression при выделении адаптеров.

Минимизировать их следует ранним подтверждением API/контрактов, characterization tests и небольшими связанными этапами, а не дополнительными framework layers. При провале gate остановить зависимые изменения, сохранить пользовательские данные и вернуть координатору evidence. Итоговый отчет разделяет: **реализовано**, **проверено автоматически**, **проверено нативно вручную**, **ограничения**, **непроверенное/blockers**; перечисляет actual changed paths и tests/docs companions. Commit/push и системные операции не следуют из приемки автоматически.
