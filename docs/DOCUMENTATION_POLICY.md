# Documentation Policy

## Назначение

Документ задает источники истины и обязательные связки между code, tests и docs. Skills и README ссылаются на эту матрицу, а не дублируют ее полностью.

## Источники Истины

1. Глобальный workflow ИИ-агента: `AGENTS.md`.
2. Действующая архитектура и runtime invariants: тематические документы в `docs/`.
3. Фактически реализованное поведение: code и passing tests.
4. Пользовательская установка, настройка и эксплуатация: корневой `README.md`.
5. Специализированные procedures: `.kilo/skills/`; они не переопределяют architecture contracts.

## Разрешение Расхождений

- Если code нарушает действующий contract, исправь code и tests.
- Если behavior осознанно меняется, синхронно обнови code, tests и соответствующий contract.
- Если `README.md` устарел относительно подтвержденной реализации, обнови пользовательскую инструкцию в том же изменении.
- Не меняй test только ради прохождения: сначала установи, устарел test или implementation нарушает contract.

## Матрица Синхронизации

| Изменяемая область | Обязательная проверка и связка |
| --- | --- |
| App state, signal wiring или lifecycle | `src/typr/app.py`, затронутые components/UI, state tests, `ARCHITECTURE.md` |
| Audio format, device selection или recording lifecycle | `audio_recorder.py`, config/settings при необходимости, mocked unit tests, `README.md` при пользовательском изменении |
| Transcription endpoint, payload, timeout или response handling | `transcriber.py`, config/settings, mocked HTTP tests, `README.md` и `ARCHITECTURE.md` при contract change |
| Global hotkey parsing, devices или hotplug | `hotkey_manager.py`, settings, tests, installer/permissions docs и `README.md` |
| Clipboard, paste shortcut или uinput behavior | `text_injector.py`, mocked tests, installer/system requirements, `README.md`, `ARCHITECTURE.md` |
| Config field или persistence | `config.py`, settings/app consumers, round-trip/error tests, user configuration docs |
| History format, retention или UI | `history.py`, `history_dialog.py`, persistence/UI tests, `README.md` при видимом изменении |
| Пользовательская UI строка или действие | UI component, RU/EN entries в `i18n.py`, UI/signal tests при логике, `README.md` при новом workflow |
| Python dependency, package entrypoint или build config | `pyproject.toml`, install/uninstall scripts и desktop entries при необходимости, build/import checks, `DEVELOPMENT.md` |
| Installer, uninstaller, desktop entry или system permission | scripts/resources, `bash -n`, безопасный preflight/manual validation, `README.md` |
| Project skills или agent workflow | `.kilo/skills/`, `AGENTS.md` при глобальном правиле, `docs/README.md` и эта policy при изменении связок |

## Границы Обновления

- Обновляй только документы, относящиеся к измененному поведению.
- Не дублируй полные runtime contracts и checklists в нескольких местах; используй ссылки на канонический документ.
- Не описывай planned behavior как реализованное.
- Не включай реальные API keys, user config, history contents или machine-specific device paths в examples.
