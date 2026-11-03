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
- `TextInjector` - QObject facade с lazy Windows SendInput / Linux uinput backend;
  асинхронная Unicode-вставка через clipboard.
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
5. Windows оставляет опубликованный текст в clipboard навсегда (как Copy), без clear/restore
   даже при ошибке/shutdown. Linux сохраняет текстовый backup/restore по сравнению строк;
   это best effort, не атомарная защита от внешнего копирования.
6. Unicode-вставка не зависит от активной keyboard layout.
7. API key хранится только в пользовательском config (Linux: `0600`; Windows:
   проверенный private DACL) и не попадает в history, logs, tests или документацию.
8. Любая ошибка чтения config/history блокирует последующие записи этого экземпляра;
   диагностические сообщения о parsing errors не содержат прочитанных данных.
9. UI state является проекцией `AppState`; tray actions не создают параллельный recording/transcription pipeline.
10. Cleanup инвалидирует injection до сохранения config. Linux worker освобождает
    virtual keyboard и helper (также восстановленного clipboard) в finally без UI join;
    Windows останавливает timer, не изменяя clipboard.
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
audio/UI этапа 4 и desktop smoke еще не выполнены.

### Text injection boundary

`request_injection(text: str, token: object) -> bool` принимает уникальный caller-generated
token; `injection_completed(token)` / `injection_failed(token, reason: str)` завершают
операцию. Token сравнивается по identity, повторное использование запрещено контрактом.
Bool означает только принятие, не успех. Busy возвращает False и queued failure для
отклоненного token, не затрагивая active request. После terminal `cleanup()` запросы
возвращают False без сигналов. Kickoff отложен на Qt event loop; controller устанавливает
token до request, поэтому корректен даже при синхронном test backend callback.
Внутренний монотонный serial фильтрует late/duplicate completion. Все public facade
методы вызываются из main Qt thread, backend result доставляется queued connection.
Setters меняют только facade, immutable значения delays фиксируются при request.

`TyprApp` сохраняет транскрипцию в history до injection независимо от его результата,
удерживает `TYPING` до completion/failure, не допускает нового recording pipeline.
Устаревшие token, поздние transcription/audio и recovery после shutdown игнорируются.
Quit инвалидирует token и вызывает injection cleanup до config.save; finally гарантирует
попытки cleanup остальных компонентов даже при ошибке сохранения. Затем app опрашивает
`TextInjector.is_cleanup_complete() -> bool` через QTimer каждые 10 мс и вызывает
QApplication.quit ровно один раз только после terminal cleanup. До cleanup метод False;
Windows/no-backend завершаются немедленно, Linux — только после session.close в finally
и фактического выхода worker (is_alive=False), включая диагностируемое исключение close.
Cleanup/quit идемпотентны. Qt event loop остается активным, join и принудительного timeout
выхода нет: daemon worker не может быть оборван обычным app quit до освобождения ресурсов.
Audio redesign этим не выполняется.

Windows backend использует QTimer (poll 10 мс, timeout 2 с) для освобождения Ctrl/Shift/
Alt/Win, включая обе физические стороны, **и клавиши V** (она не modifier).
Ожидание V исключает synthetic keyup уже удерживаемой V. Timeout не публикует clipboard и не отпускает
физические клавиши. Clipboard.setText и весь backend lifecycle выполняются в main Qt
thread. После публикации отправляется Ctrl down, V down/up, Ctrl up через ctypes
SendInput с явными signatures и полной INPUT union (40 bytes, align 8 на x64).
Проверяется точный count; partial failure отпускает только synthetic keys, оставшиеся
down в отправленном prefix, с диагностикой неудачного cleanup. Успех — отправка событий,
не target acknowledgement. UIPI/elevated target и secure desktop/UAC не обходятся.
Внешнее копирование между публикацией и paste может изменить вставляемое содержимое;
race-free paste не обещается, clear/restore отсутствуют во всех ветках.

Linux backend владеет одним последовательным worker: lazy UInput initialization,
backup, helper stdin, 120 мс ожидания, Shift+Insert, restore deadline и cleanup идут
вне Qt. Выбор wl-copy/xclip/xsel и строковый backup/restore сохранены; прежний
typing_delay остается неиспользуемым для clipboard paste. Read/clear bounded 500 мс,
stdin nonblocking с 1 с deadline, terminate/kill ожидания по 200 мс. Helper, удерживающий
clipboard, не ожидается через communicate.
Все clipboard owners остаются foreground: wl-copy --foreground, xclip -quiet,
xsel --nodetach (upstream man pages: [xclip](https://github.com/astrand/xclip/blob/master/xclip.1),
[xsel](https://github.com/kfish/xsel/blob/master/xsel.1x)). Popen владеет именно owner,
не отделившимся launcher; process восстановленного текста также остается под управлением.
Очистка X11 xclip без backup публикует пустую строку тем же managed foreground helper,
а не запускает бессрочного owner через subprocess.run. Shutdown закрывает и его.
Shutdown ставит Event и будит queue; ожидания прерываются, между блокирующими
шагами проверяется cancellation, начатая
synthetic последовательность завершается keyup. Cleanup не join UI; системный вызов
UInput/open/write не обещается принудительно прерываемым: зависший syscall может
неограниченно задержать выход, но не блокирует Qt и не обходится timeout kill приложения.
Restore и cleanup errors
логируются, injection ошибки передаются caller; failed verification не очищает clipboard.
Preflight is_available на Linux проверяет зависимости/helpers, но реальный отказ открытия
uinput определяется асинхронной операцией. Settings/i18n clipboard подсказка — этап 4.

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
