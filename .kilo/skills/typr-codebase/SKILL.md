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

Границы компонентов и runtime-инварианты описаны в `docs/ARCHITECTURE.md`. `TyprApp` не реализует детали audio, network, input или persistence; `HotkeyManager` не выполняет blocking I/O в обработчиках. `AppConfig` терпимо читает неизвестные поля; `HistoryManager` хранит только транскрипции и не получает API key или audio payload без отдельного решения.

## Правила Изменений

### Runtime

- Сохраняй event-driven связи через Qt signals/slots и явные `AppState`/`TrayState`.
- Не блокируй main Qt thread сетевыми запросами, длительной audio/input обработкой или ожиданием subprocess.
- Не добавляй альтернативный путь вставки, зависящий от текущей keyboard layout, если Unicode clipboard pipeline решает задачу.
- Ошибка отдельного компонента должна возвращать приложение в управляемое состояние и не оставлять recording, worker, clipboard helper или input device без cleanup.
- Наблюдаемость ошибок: не используй silent fallback и `except: pass`. Перехватывай конкретные ожидаемые исключения. Широкий перехват (`except Exception`) допустим только на границах runtime (Qt slots, top-level worker threads, CLI entrypoints) с обязательной диагностической записью без утечки secrets, переводом компонента в явное состояние ошибки или degraded mode и корректным cleanup. Это не должно приводить к крашу Qt UI и не отменяет tolerant loading настроек.
- Источник знаний об API библиотек: установленная версия в окружении, локальные stubs/типизация или официальная документация строго соответствующей версии; не используй непроверенные сниппеты из сети.

### Конфигурация И Данные

- Новую группу настроек оформляй dataclass и добавляй в `AppConfig.__post_init__()` и `_to_dict()`.
- Сохраняй tolerant loading, atomic write, backup и mode `0600` для config с API key.
- Политика совместимости — в `AGENTS.md`; неподдерживаемый формат обрабатывай безопасно и явно, без скрытого сброса, удаления или повреждения пользовательских данных.

### UI И Локализация

- UI остается компактным tray-first приложением; новые действия должны быть доступны без нарушения текущего push-to-talk workflow.
- Пользовательские строки добавляй одновременно в английский и русский словари `src/typr/utils/i18n.py`.

### Установка

- `install.sh` и `uninstall.sh` изменяют систему и пользовательские данные. Сохраняй интерактивные подтверждения для destructive/privileged действий и корректный `--dry-run` для preflight.
- Синхронизируй desktop entries, package entry points, README и uninstall cleanup при изменении путей установки.

## Проверки Перед Завершением

Проверки выбирай по `docs/DEVELOPMENT.md`; перед завершением проверь diff, отсутствие secrets и артефактов в staged/working tree.

## Язык

Документацию и ответы по проекту пиши на русском. Идентификаторы, команды, API paths и имена классов не локализуй.
