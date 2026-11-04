# Development

## Назначение

Документ описывает локальный workflow разработки и проверки Typr.

## Окружение

Проект требует Python 3.10+ и использует `hatchling`, PyQt6, sounddevice 0.5.6, cffi,
httpx и evdev
(зависимость evdev ограничена Linux). `install.sh` создает проектное окружение
`.venv` и устанавливает package в editable mode вместе с dev-зависимостями,
включая `pytest` и `ruff`. Этапы 1–5 Windows реализованы и прошли независимое review.
Актуальная verification этапа 5: **256 passed, 2 skipped**, scoped ruff, isolated
sdist/wheel, полная binary-only резолюция, clean install/`pip check` и installed
imports на существующем CPython 3.15.2 x64 успешны; исторический blocker PyAudio снят.
Команды, версии и внешние Temp paths приведены в
[плане Windows](WINDOWS_IMPLEMENTATION_PLAN.md#этап-5--миграция-аудио-подсистемы-на-sounddevice-portaudio-lifecycle-metadata-и-clean-install-gates).
Native gates обеих ОС и полная релизная квалификация Python остаются открыты.

Для разработки с уже созданным окружением:

```bash
./.venv/bin/pip install -e '.[dev]'
```

Не используй реальные значения из пользовательского config в tests.
`tests/conftest.py` изолирует HOME, USERPROFILE и LOCALAPPDATA временным каталогом
до импорта test modules (и default logger). Windows shell tests пропускаются до
чтения scripts. Persistence unit tests отдельно подменяют security boundary;
`test_windows_acl_on_temporary_directory` использует настоящий read-only Win32
binding и fake keys только во временном каталоге. При небезопасном окружении
проверяет отказ без записи и отмечает положительный native gate как xfail.

Targeted stage-1 suite: `python -m pytest -q tests/test_paths.py tests/test_config.py
tests/test_history.py tests/test_logger.py tests/test_installer.py tests/test_uninstaller.py`.
Это не проверка GUI, devices, clipboard или готовности всего приложения на Windows.

Targeted stage-2 suite: `python -m pytest -q tests/test_windows_hotkeys.py
tests/test_hotkey_manager.py`. Win32 API здесь полностью mocked: тесты не ставят
реальные hooks и не регистрируют session notifications. Linux evdev events/hotplug
проверяются fake devices; нативный Linux regression остается отдельным gate.
Для unit suite достаточно QCoreApplication, без запуска GUI.

## Запуск

Windows venv использует `Scripts\python.exe`, не Linux `.venv/bin/python`.
Инструкция wheel/`pip check`/consoleless `typr-gui`/Unicode cwd — в
[README](../README.md#установка). Не переиспользуйте Linux-only venv на Windows.
Существующий Python 3.15.2 x64 прошел packaging/import gates, но это не полная
релизная квалификация minor. Новый Python не устанавливался. GUI требует
отдельного разрешения и не входит в unit-проверки.

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

# Installer regressions (mocked commands, temporary HOME, no real installation/services):
./.venv/bin/python -m pytest -q tests/test_installer.py tests/test_uninstaller.py tests/test_project_skills.py

# Installer preflight без изменений системы (интерактивен для выбора локального STT и зависит от текущего Linux desktop environment, не универсальный CI check):
./install.sh --dry-run
```

## Стратегия Tests

- Config/history tests используют временный HOME и не читают пользовательские данные.
- Transcriber tests mock HTTP transport и Qt worker boundaries; реальные API calls не входят в unit suite.
- Audio, global hotkeys, clipboard и uinput проверяются unit tests через mocks, а hardware smoke выполняется вручную в видимой desktop session.
- Unit UI/lifecycle tests используют fake widgets, method isolation и QCoreApplication,
  без QApplication/widgets или native hooks/clipboard/microphone. Targeted stage-4:
  `python -m pytest tests/test_audio_recorder.py tests/test_app.py tests/test_settings_dialog.py tests/test_main.py`.
- Full suite, build, clean install/pip check выполняются отдельно; команды и результаты
  финальной verification этапа 5 — в плане Windows. Успешный `pip check` требуется
  для **полного** package: `--no-deps` install его не заменяет. Миграция использует
  sounddevice==0.5.6 (проверенный private finalizer) и cffi>=2.1.1,<3 (проверенный
  binary floor целевого Python 3.15 Windows). Linux использует системную PortAudio
  >=19.6.0,<20. Targeted audio suite дополнительно включает
  `tests/test_sounddevice_backend.py`: source-loader double проверяет import failures,
  баланс init/finalization, atexit removal и broken owner без настоящего sounddevice.
  Единственный owner сохраняет importlib module reference даже при failed import,
  снимает зарегистрированный handler и вызывает vetted finalizer только в worker
  под общим lock; ошибка финализации poison-ит owner до перезапуска. `_initialized`
  не модифицируется приложением. Вызов `import sounddevice` не является безопасной
  import-пробой: он вызывает native init. Installed probe использует import guard,
  проверку `sys.modules` и читает source без импорта, без production stubs.
  Native Linux regression и Windows GUI smoke unit-тестами не закрываются.
- Shell syntax проверен существующим Git Bash 5.3.15 отдельным `bash -n` для каждого
  script. Это не native Linux shell regression; installer и dry-run не запускались.
- Wheel evidence этапа 5 относится к реализованному коду и зависимостям до финального
  docs-only обновления статуса; повторная сборка из-за этого обновления не выполнялась.

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
