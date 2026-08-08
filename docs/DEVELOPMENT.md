# Development

## Назначение

Документ описывает локальный workflow разработки и проверки Typr.

## Окружение

Проект требует Python 3.10+ и использует `hatchling`, PyQt6, PyAudio, httpx и evdev. `install.sh` создает проектное окружение `.venv` и устанавливает package в editable mode.

Для разработки с уже созданным окружением:

```bash
./.venv/bin/pip install -e '.[dev]'
```

Не используй реальные значения из `~/.config/typr/config.json` в tests. Tests, затрагивающие persistence, должны подменять `HOME` временным каталогом до импорта модулей с home-relative constants.

## Запуск

```bash
./.venv/bin/typr
```

Запуск требует desktop session, system tray, microphone, clipboard utility, доступ к `/dev/input/event*` и `/dev/uinput`. Отсутствие этих ресурсов в CI не должно маскироваться production fallback-кодом.

## Проверки

Полный набор Python tests:

```bash
./.venv/bin/pytest
```

Static checks:

```bash
./.venv/bin/ruff check .
./.venv/bin/mypy src/typr
```

Эти команды проверяют весь существующий Python-код. При локальном изменении сначала проверь затронутые файлы; repository-wide findings вне текущего diff фиксируй отдельно и не исправляй несвязанным массовым refactor.

Shell syntax:

```bash
bash -n install.sh uninstall.sh
```

Installer preflight без изменений системы:

```bash
./install.sh --dry-run
```

`--dry-run` остается интерактивным для выбора локального STT и зависит от текущего Linux desktop environment. Не запускай его как универсальный CI check.

## Стратегия Tests

- Config/history tests используют временный HOME и не читают пользовательские данные.
- Transcriber tests mock HTTP transport и Qt worker boundaries; реальные API calls не входят в unit suite.
- Audio, global hotkeys, clipboard и uinput проверяются unit tests через mocks, а hardware smoke выполняется вручную в видимой desktop session.
- UI tests используют `pytest-qt` и не должны требовать реального microphone/input device для проверки layout и signal wiring.

## Ручная Desktop Проверка

После изменений runtime pipeline проверь в видимой Linux session:

1. Запуск и наличие tray icon.
2. Старт/остановку записи хоткеем и кликом по tray icon.
3. Успешную транскрипцию через настроенный compatible endpoint.
4. Unicode paste в GUI-приложение и terminal.
5. Восстановление clipboard и сохранение нового clipboard content пользователя.
6. Error recovery при недоступном endpoint и повторную запись после recovery.
7. Отзывчивость Settings при `Fetch` и `Test Connection` на медленном или недоступном endpoint.

## Документация

При изменении behavior обновляй code, tests и документы по `DOCUMENTATION_POLICY.md` в одном изменении. Корневой `README.md` остается пользовательским руководством; `docs/` содержит developer и architecture contracts.
