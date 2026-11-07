# Development

## Назначение

Документ описывает локальный workflow разработки и проверки Typr.

## Окружение

Проект требует Python 3.10+ и использует `hatchling`, PyQt6, sounddevice 0.5.6, cffi,
httpx и evdev
(зависимость evdev ограничена Linux). `install.sh` создает проектное окружение
`.venv` и устанавливает package в editable mode вместе с dev-зависимостями,
включая `pytest` и `ruff`. Этапы 1–5 Windows реализованы и прошли независимое review.
Текущий верификационный статус Windows: полный набор с тестами установщика — **284 passed, 2 skipped** (предыдущий baseline: 280 passed, 2 skipped),
scoped ruff; чистая установка (clean install) пересобранного wheel (`typr-0.4.0-py3-none-any.whl`)
с `pip check` и изолированными import probes завершена успешно (**PASS**). Модуль локального GigaSTT
проверен в натурном режиме (**live module PASS**): контейнер и том созданы, эндпоинты `/ready` и
`/health` (модель `gigaam-v3-rnnt`, вариант `rnnt`) готовы, транскрипция синтетического аудио через
QCoreApplication выполнена без GUI/микрофона с чистым завершением потока.
Сборка полного автономного архива (full ZIP payload) через `Build-Payload.ps1` завершена успешно (**PASS**, сформирован итоговый архив `Typr-Windows-x64-20261107-final.zip` после исправления ошибки установки `LastWriteTime` для zip-записей): этапы сборки актуального wheel, развертывания runtime, `pip check` (полный граф зависимостей wheelhouse) и `Verify-Runtime.py` пройдены.
Релизная квалификация установщика и CPython 3.15.2 сохраняет статус **OPEN**, а натурный desktop smoke
в изолированном harness — статус gate 8 **PARTIAL / OPEN** (не заменен, полная готовность / PASS не заявляется).
Исторический blocker PyAudio снят.
После этапа 5 проведена санкционированная частичная нативная верификация Windows
(desktop smoke) на существующем установленном runtime этапа 5 в изолированном профиле без
сетевого endpoint; нативный gate 8 перешел в статус **PARTIAL / OPEN** (не заменен). Обычный запуск успешен
(exit 0) с реальной записью звука в память (~2 с), хуками `WH_KEYBOARD_LL`, SendInput
в собственное окно и чистым выходом; consoleless-запуск через `pythonw.exe` завершился с
exit 1 из-за таймаута фокуса окна (точная причина не установлена, ограничения Windows — возможная
причина; injection не запускался, SendInput предотвращен focus guard, production-дефект не подтвержден).
Подробности, результаты и команды приведены в
[плане Windows](WINDOWS_IMPLEMENTATION_PLAN.md#частичная-нативная-verification-windows-post-stage-5-2026-11-04).
Native gates обеих ОС и полная релизная квалификация Python/установщика остаются в статусе **OPEN**
до независимого review и сквозной натурной приемки.

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
релизная квалификация minor. Новый Python не устанавливался. Натурный smoke
проведен частично в изолированном harness (gate 8 PARTIAL / OPEN), полнофункциональный
запуск GUI и сквозная транскрипция требуют отдельного разрешения.

```bash
./.venv/bin/typr
```

Запуск требует desktop session, system tray, microphone, clipboard utility, доступ к `/dev/input/event*` и `/dev/uinput`. Отсутствие этих ресурсов в CI не должно маскироваться production fallback-кодом.

## Сборка офлайн-пакета Windows (Build-Payload.ps1)

Для формирования автономного офлайн-установщика Typr под Windows 11 x64 используется скрипт `scripts/windows/Build-Payload.ps1`. Сборка выполняется в изолированном временном каталоге и не модифицирует окружение разработчика.

### Требования к сборочному окружению (Developer Build Prerequisites)

Перед сборкой офлайн-пакета необходимо подготовить следующие компоненты:
1. **Сборочный интерпретатор CPython 3.15.2 x64 (`$BuildPython`):**
   - Строго CPython 3.15.2 win32 AMD64.
   - В окружении должны быть установлены `pip` и сборочный бэкенд `hatchling` (сборщик компилирует свежий wheel Typr из репозитория через `pip wheel --no-index --no-deps --no-build-isolation`).
2. **Официальный архив embed-дистрибутива Python (`$EmbedZip`):**
   - Файл официального дистрибутива `python-3.15.2-embed-amd64.zip`.
   - Обязательный входной параметр контрольной суммы (`$EmbedSha256`):
     `d012f3aa29cf07436dae8aea1fec0fd195c2612a0b059b1f915ae0afb9ad1f62`.
   - При несовпадении SHA256 сборка немедленно прерывается.
3. **Каталог бинарных зависимостей (`$Wheelhouse`):**
   - Каталог, содержащий предварительно подготовленные бинарные wheels для CPython 3.15.2 (win_amd64) для всех runtime-зависимостей Typr (PyQt6, sounddevice, cffi, httpx и др.).
   - **Обязательно включение wheel самого `pip`** в wheelhouse (требуется для развертывания зависимостей в целевую директорию `Lib\site-packages` встроенного runtime).
4. **Манифест wheelhouse (`$WheelhouseManifest`):**
   - JSON-файл со схемой:
     ```json
     {
       "schema": 1,
       "files": [
         {
           "path": "имя_пакета.whl",
           "sha256": "64_символьный_hex_sha256"
         }
       ]
     }
     ```
   - Манифест должен перечислять исключительно файлы с расширением `.whl`. Скрипт проверяет совпадение SHA256 каждого файла и блокирует сборку при наличии неподтвержденных файлов или расхождений.

### Команда сборки

Запуск сборщика выполняется из PowerShell 5.1 с актуальными именами параметров:

```powershell
& ".\scripts\windows\Build-Payload.ps1" `
    -BuildPython "C:\path\to\CPython315\python.exe" `
    -EmbedZip "C:\path\to\python-3.15.2-embed-amd64.zip" `
    -EmbedSha256 "d012f3aa29cf07436dae8aea1fec0fd195c2612a0b059b1f915ae0afb9ad1f62" `
    -Wheelhouse "C:\path\to\wheelhouse" `
    -WheelhouseManifest "C:\path\to\wheelhouse.json" `
    -OutputZip "C:\path\to\Typr-0.4.0-win64.zip"
```

*Примечание:* в стандартном сценарии разработчика реальные команды загрузки из сети не выполняются: все артефакты подготавливаются локально и валидируются по хэшам. Переключатель `-DownloadEmbed` опционален и запрашивает интерактивное подтверждение при необходимости скачивания официального архива Python с проверкой SHA256.

### Состав и валидация сформированного пакета

Сформированный архив содержит каталог `Typr/` со следующей структурой:
- `runtime/` — распакованный автономный CPython 3.15.2 с настроенным файлом `python315._pth` (`Lib\site-packages` и директива `import site`);
- `runtime/Lib/site-packages/` — установленный свежий wheel Typr и полный граф бинарных зависимостей, прошедший проверку `pip check` и импорты `Verify-Runtime.py` (с изоляцией и запретом прямой нативной инициализации sounddevice/PortAudio);
- `Install.bat`, `Uninstall.bat`, `Install.ps1`, `TyprInstaller.ps1`, `Initialize-Config.py`;
- `LICENSE` и лицензии dist-info установленных пакетов;
- `payload.json` — манифест инвентаря со списком всех файлов и их SHA256 (`qualification = 'OPEN'`).

Сборка полного автономного ZIP-пакета сборщиком `Build-Payload.ps1` завершена успешно (**PASS**, сформирован итоговый архив `Typr-Windows-x64-20261107-final.zip` размером 105 245 862 байт, SHA-256 `9c5e3614a3e09da58b2411c09a8ad6830e972d58722041734f7bf79d7286aaef` после устранения ошибки установки таймстемпов записей архива): этапы сборки актуального wheel Typr, развертывания embeddable runtime CPython 3.15.2, чистой офлайн-установки полного графа зависимостей wheelhouse, `pip check` и изоляции импортов `Verify-Runtime.py` проходят штатно. Релизная квалификация CPython 3.15.2 и установщика сохраняет статус **OPEN**: сквозная натурная приемка на чистой системе Windows 11 x64 ожидает выполнения.

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
- Частичная нативная верификация Windows (post-stage 5 desktop smoke): натурный
  smoke выполнен в изолированном harness без endpoint на runtime этапа 5; native
  gate 8 находится в статусе **PARTIAL / OPEN**. Продакшен-лаунчер `typr-gui.exe`
  не принят; актуальные результаты этапа 6 и открытые ворота приведены во введении и в
  [плане Windows](WINDOWS_IMPLEMENTATION_PLAN.md#этап-6--автономный-per-user-инсталлятор-windows-11-x64-и-интеграция-локального-docker-stt).
  Канонические свидетельства, команды и результаты прогонов — в
  [плане Windows](WINDOWS_IMPLEMENTATION_PLAN.md#частичная-нативная-verification-windows-post-stage-5-2026-11-04).

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
