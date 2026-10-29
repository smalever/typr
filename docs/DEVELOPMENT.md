# Development

## Назначение

Документ описывает локальный workflow разработки и проверки Typr.

## Окружение

Проект требует Python 3.10+ и использует `hatchling`, PyQt6, PyAudio, httpx и evdev. `install.sh` создает проектное окружение `.venv` и устанавливает package в editable mode вместе с dev-зависимостями, включая `pytest` и `ruff`.

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

### Матрица Проверок

Канонические правила выбора проверок:

| Тип изменений | Проверки | Когда запускать |
| --- | --- | --- |
| Локальные изменения кода | Targeted tests + `ruff check <файлы>` | Во время работы над правками. |
| Широкие / cross-component изменения | Полный `pytest` | Один раз после завершения интеграции; повтор при исправлениях, влияющих на результат. |
| Workflow / docs-only изменения | Targeted tests (например, `tests/test_project_skills.py`) | По завершении правок в docs/skills. |
| Диагностика кодовой базы | `ruff check .` и `mypy src/typr` | Запускаются для оценки repo-wide состояния; существующие findings вне diff фиксируются отдельно и не смешиваются с целевой правкой. |
| Packaging / entrypoints | `python -m build` (при отсутствии toolchain фиксируется как непроверенное/blocker при обязательной проверке) | При изменении `pyproject.toml`, packaging или точек входа. |
| Shell scripts / installer | `bash -n install.sh uninstall.sh` | При изменении shell-скриптов; `./install.sh --dry-run` запускается только если текущее окружение подходит для preflight. |

Отчет о проверках обязан связывать результаты с актуальным diff; запрещается выдавать старые результаты предыдущих запусков за проверку новых правок.

Команды проверок (запускаются через проектный `.venv`, если он существует):

```bash
# Python tests
./.venv/bin/pytest

# Static checks
./.venv/bin/ruff check .
./.venv/bin/mypy src/typr

# Shell syntax
bash -n install.sh uninstall.sh

# Installer preflight без изменений системы (интерактивен для выбора локального STT и зависит от текущего Linux desktop environment, не универсальный CI check):
./install.sh --dry-run
```

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

## Версионирование

Версия приложения следует SemVer. Выбор уровня, команды и обязательное повышение после review непосредственно перед staging описаны в `.kilo/skills/git-commit/SKILL.md`; изменение версии входит в тот же commit.
