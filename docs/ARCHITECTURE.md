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
- `HotkeyManager` - чтение keyboard devices через `evdev` в background thread и hotplug scan.
- `TextInjector` - Unicode paste через desktop clipboard и virtual keyboard `/dev/uinput`.
- `HistoryManager` - локальная JSON history с ограничением количества записей.
- `AppConfig` - tolerant JSON loading, backup и atomic persistence пользовательских настроек.
- `TrayIcon`, `SettingsDialog`, `HistoryDialog` - desktop UI и пользовательские действия.

## Инварианты

1. Main Qt thread не выполняет длительные network, audio или input операции.
2. `HotkeyManager` только публикует события записи и не управляет audio/network напрямую.
3. `AudioRecorder` завершает stream и thread до публикации готового WAV.
4. Один результат транскрипции либо вставляется и возвращает приложение в `IDLE`, либо переводит его в управляемый `ERROR` с автоматическим recovery.
5. Clipboard захватывается непосредственно перед paste. Исходное содержимое восстанавливается только если пользователь не заменил вставленный текст новым clipboard content.
6. Unicode-вставка не зависит от активной keyboard layout.
7. API key хранится только в пользовательском config с mode `0600` и не попадает в history, logs, tests или документацию.
8. Поврежденный config не перезаписывается автоматическим save.
9. UI state является проекцией `AppState`; tray actions не создают параллельный recording/transcription pipeline.
10. Cleanup освобождает audio stream, input devices, virtual keyboard и clipboard helper process.

## Данные И Системные Границы

```text
~/.config/typr/config.json       settings and API key
~/.config/typr/logs/typr.log    application log
~/.local/share/typr/history.json transcription history
/dev/input/event*               global hotkey input
/dev/uinput                     virtual keyboard output
```

Typr поддерживает Wayland и X11 через clipboard utilities и kernel input interfaces. Права доступа к input devices и `/dev/uinput` являются обязательной системной предпосылкой, а не частью Python fallback logic.

## Изменение Архитектуры

Новый processing stage добавляется как отдельный компонент с явным ownership, сигналами завершения/ошибки, cleanup и состоянием UI. Архитектурное решение должно сопровождаться обновлением этого документа, tests и соответствующих пользовательских инструкций.
