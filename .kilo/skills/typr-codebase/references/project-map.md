# Карта Проекта

## Структура

- `src/typr/__main__.py` - создание `QApplication` и запуск `TyprApp`.
- `src/typr/app.py` - orchestration, state machine и Qt signal wiring.
- `src/typr/config.py` - dataclass configuration и persistence.
- `src/typr/core/` - audio, transcription, hotkeys, text injection и history.
- `src/typr/ui/` - tray icon, settings и history dialogs.
- `src/typr/utils/` - i18n и logging.
- `resources/` - desktop entries и icons.
- `install.sh`, `uninstall.sh` - Linux installation lifecycle.
- `tests/` - automated tests.
- `docs/` - архитектура, developer workflow и policy синхронизации.
- `.kilo/skills/` - project-specific Kilo workflows.

## Runtime Pipeline

```text
HotkeyManager / TrayIcon
  -> TyprApp
  -> AudioRecorder
  -> WhisperTranscriber
  -> HistoryManager
  -> TextInjector
  -> active application
```

## Критичные Связки

- `config.py` <-> `settings_dialog.py` <-> `app.py` <-> config tests/docs.
- `AppState` <-> `TrayState` <-> tray strings/tooltips.
- `transcriber.py` <-> OpenAI-compatible `/audio/transcriptions` contract.
- `text_injector.py` <-> clipboard tools <-> `/dev/uinput` permissions <-> installer/docs.
- `hotkey_manager.py` <-> `/dev/input/event*` permissions <-> installer/docs.
- `history.py` <-> `history_dialog.py` <-> local data cleanup in `uninstall.sh`.
- `pyproject.toml` <-> `.venv` install <-> desktop `Exec` paths <-> README.

## Куда Смотреть Сначала

- Архитектура и инварианты: `docs/ARCHITECTURE.md`.
- Обязательные companions: `docs/DOCUMENTATION_POLICY.md`.
- Команды разработки и проверок: `docs/DEVELOPMENT.md`.
- Пользовательская установка и эксплуатация: `README.md`.
