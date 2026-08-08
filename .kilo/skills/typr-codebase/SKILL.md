---
name: typr-codebase
description: Проектный контекст Typr для нетривиальных изменений, проектирования и ревью: PyQt6 lifecycle, аудиозапись, Whisper-compatible API, evdev/uinput, clipboard, конфигурация, история, install scripts, tests и документация.
---

# Кодовая База Typr

## Назначение

Загружай этот skill перед нетривиальными изменениями, проектированием, рефакторингом или ревью. Сначала определи затронутый runtime boundary и обязательные companions по `docs/DOCUMENTATION_POLICY.md`.

Карта документации находится в `docs/README.md`, действующая архитектура и инварианты - в `docs/ARCHITECTURE.md`, developer workflow - в `docs/DEVELOPMENT.md`. Детальная карта файлов доступна в `references/project-map.md`; читай ее, когда нужен обзор связей.

## Бюджет Контекста

Не читай без необходимости:

- `.venv/**`, `**/__pycache__/**`, `.pytest_cache/**`, `.mypy_cache/**`;
- локальные config, history и logs в home directory;
- build artifacts и package metadata.

## Архитектурные Границы

- `TyprApp` координирует компоненты и состояния, но не реализует детали audio, network, input или persistence.
- `AudioRecorder` владеет PyAudio stream и recording thread.
- `WhisperTranscriber` выполняет HTTP I/O только в worker thread и возвращает результат через Qt signals.
- `HotkeyManager` читает `evdev` devices в отдельном thread; обработчики не выполняют blocking I/O.
- `TextInjector` захватывает clipboard непосредственно перед paste и восстанавливает его только если пользователь не изменил содержимое.
- `AppConfig` терпимо читает неизвестные поля и не перезаписывает поврежденный config.
- `HistoryManager` хранит только транскрипции и не должен получать API key или audio payload без отдельного решения.

## Правила Изменений

### Runtime

- Сохраняй event-driven связи через Qt signals/slots и явные `AppState`/`TrayState`.
- Не блокируй main Qt thread сетевыми запросами, длительной audio/input обработкой или ожиданием subprocess.
- Не добавляй альтернативный путь вставки, зависящий от текущей keyboard layout, если Unicode clipboard pipeline решает задачу.
- Ошибка отдельного компонента должна возвращать приложение в управляемое состояние и не оставлять recording, worker, clipboard helper или input device без cleanup.

### Конфигурация И Данные

- Новую группу настроек оформляй dataclass и добавляй в `AppConfig.__post_init__()` и `_to_dict()`.
- Сохраняй tolerant loading, atomic write, backup и mode `0600` для config с API key.
- Изменения формата history должны сохранять безопасное чтение существующих записей либо сопровождаться явно обоснованной migration strategy.

### UI И Локализация

- UI остается компактным tray-first приложением; новые действия должны быть доступны без нарушения текущего push-to-talk workflow.
- Пользовательские строки добавляй одновременно в английский и русский словари `src/typr/utils/i18n.py`.
- Не выполняй network/audio проверки в UI thread, если операция может заметно задержать интерфейс.

### Установка

- `install.sh` и `uninstall.sh` изменяют систему и пользовательские данные. Сохраняй интерактивные подтверждения для destructive/privileged действий и корректный `--dry-run` для preflight.
- Синхронизируй desktop entries, package entry points, README и uninstall cleanup при изменении путей установки.

## Проверки Перед Завершением

- Запусти релевантные tests; для широкого изменения - полный `pytest`.
- Запусти `ruff check` для затронутых Python-файлов. Полный `ruff check .` и `mypy src/typr` используй как repository-wide диагностику: существующие findings вне текущего diff фиксируй отдельно и не смешивай с целевой правкой.
- Для packaging или entrypoint changes выполни `python -m build` либо эквивалентную доступную проверку сборки.
- Для installer changes выполни `bash -n install.sh uninstall.sh`; `--dry-run` запускай только когда он не требует нежелательного интерактивного или системного действия.
- Проверь `git diff`, обязательные docs/tests, stale paths и отсутствие secrets/generated artifacts.

## Язык

Документацию и ответы по проекту пиши на русском. Идентификаторы, команды, API paths и имена классов не локализуй.
