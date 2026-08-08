---
name: code-review
description: Проводит ревизию незакоммиченных изменений Typr, исправляет подтвержденные дефекты в целевой работе, синхронизирует tests/docs и повторяет релевантные проверки до успеха или явного blocker. Используй для запросов «сделай ревью» и «проверь изменения».
---

# Code Review

## Назначение

Стандартный review незакоммиченного рабочего дерева выполняется с исправлениями подтвержденных defects. Review-only используй, если пользователь явно запретил правки, либо для исторического diff ветки, commit или PR без отдельной просьбы применить исправления.

Перед нетривиальным review загрузи `typr-codebase`. Глобальные ограничения задает `AGENTS.md`, обязательные companions - `docs/DOCUMENTATION_POLICY.md`, команды - `docs/DEVELOPMENT.md` и `pyproject.toml`.

## Область

Начни с:

```bash
git status --short
git diff
git diff --staged
```

Проверь tracked, staged и содержательные untracked файлы. Раздели целевые изменения, обязательные companions и явно несвязанную пользовательскую работу. Несвязанную работу анализируй, но не изменяй.

## Проверка

Оцени:

1. Корректность state transitions, error recovery и cleanup.
2. Blocking I/O и thread ownership в Qt, audio, network и input paths.
3. Clipboard preservation, Unicode paste и races с пользовательским clipboard.
4. Совместимость config/history, atomic persistence и защита API key.
5. `evdev`/`uinput` permissions, installer/uninstaller safety и desktop integration.
6. Локализацию новых пользовательских строк на RU/EN.
7. Позитивные, негативные и regression tests.
8. Актуальность docs по `docs/DOCUMENTATION_POLICY.md`.
9. Secrets, debug code, caches, logs и лишние generated files.

## Исправления И Проверки

Исправляй все подтвержденные проблемы в целевой связке, включая tests/docs. Не выполняй несвязанный refactor и не меняй test только ради зеленого результата.

Запусти релевантные tests и static checks. Для широкого cross-component diff нужен полный `pytest`; для shell changes - `bash -n install.sh uninstall.sh`. Повторяй упавшую проверку после диагностики root cause до успеха либо blocker.

Blocker: отсутствующий project toolchain, необходимый hardware/system permission, external API/secret, destructive operation, конфликт чужих изменений или архитектурное решение вне запроса.

## Финальная Приемка

Повторно проверь `git status --short`, `git diff` и `git diff --staged`. Убедись в полноте tests/docs, отсутствии secrets/artifacts и сообщи исправленные defects, проверки, blockers и оставшиеся несвязанные изменения.

В review-only начни с findings по severity с `file:line`; если findings нет, скажи это явно и укажи residual risks или testing gaps.
