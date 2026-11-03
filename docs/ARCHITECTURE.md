# Архитектура Typr

## Назначение

Документ фиксирует действующую архитектуру desktop-приложения Typr.

## Главный Принцип

Typr является tray-first orchestration приложением. Qt controller связывает независимые компоненты через signals/slots, а blocking audio, input и network work выполняется вне main UI thread.

```text
HotkeyManager / TrayIcon
  -> TyprApp state machine
  -> AudioRecorder
  -> WhisperTranscriber
  -> HistoryManager
  -> TextInjector
  -> active desktop application
```

## Компоненты

- `TyprApp` - lifecycle, wiring и состояния `IDLE`, `RECORDING`, `TRANSCRIBING`, `TYPING`, `ERROR`.
- `AudioRecorder` - PyAudio stream, recording thread и WAV assembly.
- `WhisperTranscriber` - OpenAI-compatible HTTP request в `QThread`.
- `HotkeyManager` - QObject facade с lazy Linux evdev / Windows WH_KEYBOARD_LL backend;
  чтение устройств, native message loop и hotplug scan выполняются в worker.
- `TextInjector` - Unicode paste через desktop clipboard и virtual keyboard `/dev/uinput`.
- `HistoryManager` - локальная JSON history с ограничением количества записей.
- `AppConfig` - tolerant JSON loading, backup и atomic persistence пользовательских настроек.
- `TrayIcon`, `SettingsDialog`, `HistoryDialog` - desktop UI и пользовательские действия;
  сетевые пробы `SettingsDialog` выполняются через Qt thread pool.

### Discovery локального Parakeet

Settings сначала использует `/models` и `/audio/models`. При их отсутствии
Parakeet распознаётся по OpenAPI title `Parakeet TDT 0.6B v3 (optimized)` и paths
`/health`, `/healthz`, `/v1/audio/transcriptions`. Только для этого контракта `/health`
служит источником загруженных моделей: `ready=true`, default model присутствует в
`loaded`, а все loaded IDs принадлежат каталогу `models`. Каталог не равнозначен
установленным моделям; OpenAPI default сам по себе также не доказывает загрузку.
Test Connection распознанного Parakeet использует ту же readiness-проверку, а не OPTIONS.
До распознавания OpenAPI для Test Connection опционален: HTML, некорректный JSON,
недоступность или HTTP-ошибка схемы не блокируют обычную OPTIONS-пробу transcription.
Исключение — 401/403, которые сохраняются как ошибки авторизации. После распознавания
ошибки `/health` и отсутствие readiness всегда завершают проверку ошибкой без OPTIONS fallback.
Deployment root получается удалением конечного `/v1`, без потери path prefix.
Все запросы остаются в существующем Qt thread pool. Для неизвестного endpoint
не применяется статический Parakeet fallback.

## Инварианты

1. Main Qt thread не выполняет длительные network, audio или input операции.
2. `HotkeyManager` только публикует события записи и не управляет audio/network напрямую.
3. `AudioRecorder` завершает stream и thread до публикации готового WAV.
4. Один результат транскрипции либо вставляется и возвращает приложение в `IDLE`, либо переводит его в управляемый `ERROR` с автоматическим recovery.
5. Clipboard захватывается непосредственно перед paste. Исходное содержимое восстанавливается только если пользователь не заменил вставленный текст новым clipboard content.
6. Unicode-вставка не зависит от активной keyboard layout.
7. API key хранится только в пользовательском config (Linux: `0600`; Windows:
   проверенный private DACL) и не попадает в history, logs, tests или документацию.
8. Любая ошибка чтения config/history блокирует последующие записи этого экземпляра;
   диагностические сообщения о parsing errors не содержат прочитанных данных.
9. UI state является проекцией `AppState`; tray actions не создают параллельный recording/transcription pipeline.
10. Cleanup останавливает clipboard restore timer и освобождает audio stream, input devices,
    virtual keyboard и текущий clipboard helper process, включая helper восстановленного clipboard.
11. HTTP transcription использует отдельные connect/read timeouts; локальному GigaSTT
    предоставляется более длинное CPU inference window, а ошибки принимаются как в OpenAI
    object-формате, так и в строковом GigaSTT envelope.

## Данные И Системные Границы

### Global hotkey boundary

Внешний API `HotkeyManager`: `recording_started`, `recording_stopped`,
`hotkey_error(str)`, `initialize() -> bool`, `update_shortcut(str) -> bool`,
`is_registered()` и идемпотентный `cleanup()`. `platforms.hotkey_backend()`
импортирует только backend текущей ОС: на Windows evdev не загружается.
Общий `platforms/shortcut.py` разбирает один chord через QKeySequence PortableText;
пустые, multi-chord (включая пустой trailing chord в исходном тексте) и
неподдерживаемые клавиши/модификаторы отвергаются явно. Comma target `Ctrl+,`
отличается от разделителя chord, но OEM punctuation пока не поддерживается.
Поддерживаются A–Z, 0–9, F1–F12, Space, Return/Enter, Esc, Tab, Backspace,
Delete/Insert, Home/End, PgUp/PgDown и стрелки; modifiers Ctrl/Alt/Shift/Meta.
Ошибка update не меняет действующий shortcut; успешный update и cleanup
прекращают активный PTT. Для Windows Qt relay отдельно проверяет identity worker
registration и shortcut generation: start/stop требуют обоих совпадений; ошибки
текущего worker, включая финальный native cleanup, не зависят от shortcut generation.
Так отказ GetMessageW до обработки WM_UPDATE остается видимым. Новый worker
получает новую registration до старта: queued start/stop/error прошлого worker
отбрасываются после restart. Идемпотентный initialize живого registered worker
не меняет identity и не теряет pending/active PTT. Linux сохраняет evdev read/select и hotplug scan;
управление update/reset передается worker через очередь, cleanup не делает join UI.

Windows binding задает pointer-sized LRESULT/WPARAM/LPARAM/HHOOK/ULONG_PTR,
WINFUNCTYPE и явные signatures. Worker создает native message queue до публикации
thread ID, скрытое окно для WTS session notifications и WH_KEYBOARD_LL, затем
выполняет GetMessageW/DispatchMessageW. State принадлежит worker; update/reset/quit
передаются private messages. Callback не делает I/O/sleep/locks и всегда вызывает
CallNextHookEx. Callback references живут до unhook и выхода worker; ошибки
установки, message loop и cleanup публикуются через queued Qt signal.

Физические left/right modifiers учитываются отдельно, duplicate down не запускает
PTT повторно; start возможен только на новом target down с required modifiers
(лишние разрешены). Stop — target up или утрата последнего modifier required группы.
Все injected события игнорируются: синтетический Ctrl AltGr не удовлетворяет Ctrl,
но настоящий Ctrl+правый Alt допустим. Lock/unlock и остальные WTS session changes
останавливают PTT и очищают pressed state. Обнаружение silent hook removal ОС
не гарантируется.

`initialize()` сохраняет bool контракт: ограниченное ожидание readiness до 100 мс,
False и явная ошибка при timeout/известном отказе, startup отменяется. Cleanup
только запрашивает остановку, без join Qt thread; повтор initialize во время
завершения возвращает False с ошибкой, после выхода worker возможен чистый restart.
Эти unit-проверенные границы не означают готовность всего Windows приложения:
injection/audio/UI этапы 3–4 и desktop smoke еще не выполнены.

```text
~/.config/typr/config.json       settings and API key
~/.config/typr/logs/typr.log    application log
~/.local/share/typr/history.json transcription history
/dev/input/event*               global hotkey input
/dev/uinput                     virtual keyboard output
```

Typr поддерживает Wayland и X11 через clipboard utilities и kernel input interfaces. Права доступа к input devices и `/dev/uinput` являются обязательной системной предпосылкой, а не частью Python fallback logic.

### Платформенные пути и persistence

`platforms/paths.py` не импортирует device backends. Linux-пути выше сохранены
без XDG-переопределений. Для Windows подготовлены `%LOCALAPPDATA%\Typr\config.json`,
`history.json`, `logs\typr.log`; это не означает готовность Windows runtime.
Отсутствующий/относительный LOCALAPPDATA вызывает явную ошибку, без cwd fallback.

JSON и logs используют UTF-8. Config и backup заменяются атомарно через уникальные
временные файлы; на Linux файлы с самого создания имеют `0600`. Ошибка backup
прерывает save, сохраняя исходный config. History использует ту же private atomic
запись; после ошибки чтения изменения возможны только в памяти.

Windows binding `platforms/windows_security.py` только читает token/profile и
реальные owner/DACL (включая inherited ACE). До mkdir и до записи проверяется
цепочка внутри профиля token user; reparse points, null DACL, неизвестные ACE и
недоверенные разрешения приводят к отказу. Допускаются user, SYSTEM,
Administrators и OWNER RIGHTS при доверенном owner; у предков допустим только
ненаследуемый read/list доступ прочих SID без прав изменения. Новые файлы
наследуют проверенные права и проверяются до записи payload. ACL не изменяются,
`chmod` не выдается за Windows privacy. Нестандартный профиль может быть отвергнут.

Logger при отсутствии stdout использует stderr, а при отсутствии обоих — файл.
Ошибки разрешения/открытия log path явно поднимаются как `OSError`, без скрытого
отключения logging и без альтернативного каталога.

## Политика Эволюции

Политика совместимости — в `AGENTS.md`. Сохраняются толерантная загрузка и атомарное сохранение конфигурации, безопасная обработка неподдерживаемых форматов без скрытого сброса или удаления данных и защита secrets.

## Изменение Архитектуры

Новый processing stage добавляется как отдельный компонент с явным ownership, сигналами завершения/ошибки, cleanup и состоянием UI. Архитектурное решение должно сопровождаться обновлением этого документа, tests и соответствующих пользовательских инструкций.
