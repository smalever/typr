---
name: git-commit
description: По явному запросу подготавливает изменения Typr через code-review, формирует безопасный staged diff и создает один локальный Conventional Commit без push.
---

# Git Commit

## Назначение

Используй только по явному запросу создать commit. Workflow не выполняет push, amend, создание ветки или destructive git operations. Субагент не создает commit.

## Pre-Commit Gate

Сначала загрузи и выполни `code-review` для целевых незакоммиченных изменений. Если review уже выполнен в текущей сессии, diff после него не менялся и checks относятся к тому же состоянию, используй эти результаты.

Не создавай commit при blocker, незавершенных обязательных проверках или неполной связке из `docs/DOCUMENTATION_POLICY.md`.

## Подготовка

Проверь:

```bash
git branch --show-current
git status --short
git diff
git diff --staged
git log --oneline -10
```

Собери один логически цельный commit. Исключи API keys, user config/history/logs, `.venv`, caches, build artifacts и несвязанную работу.

Добавляй только явные paths через `git add <path>...`. Не используй `git add .`, `git add -A`, `git commit -a`, stash, reset, checkout или clean.

## Версия Приложения

Каждый commit с изменениями проекта обязан непосредственно перед staging повысить SemVer-версию приложения. Не повышай версию заранее во время реализации и не создавай отдельный version-only commit.

Выбери один уровень по максимальному влиянию всех изменений commit:

1. `patch` - исправления, docs, tests, refactor, tooling и небольшие внутренние изменения без нового пользовательского workflow и без нарушения совместимости.
2. `minor` - обратно совместимая функция, заметное расширение поведения, новая настройка, поддержка платформы или существенное улучшение существующего workflow.
3. `major` - несовместимое изменение CLI, config/data format, public behavior или системных требований; удаление/замена основного workflow либо глобальная переработка продукта. Явно обоснуй major в итоговом сообщении.

При смешанных изменениях используй самый высокий применимый уровень. Если граница между соседними уровнями действительно неоднозначна, до изменения версии запроси решение пользователя.

Выполни ровно один раз:

```bash
python3 scripts/bump_version.py patch  # либо minor / major
python3 scripts/bump_version.py --check
```

Скрипт синхронизирует `pyproject.toml`, `src/typr/__init__.py`, About-строки в `src/typr/utils/i18n.py` и badge в `README.md`. Добавь эти изменения в тот же commit и повтори затронутые version/contract checks. Если после bump состав или смысл commit изменился, заново определи уровень до staging; не выполняй второй bump поверх ошибочного.

## Staged Gate

Проверь `git diff --staged --stat` и полный `git diff --staged`. Staged diff должен совпадать с прошедшим review с добавленным version bump и содержать все обязательные tests/docs companions без secrets и artifacts. Убедись, что версия повышена ровно на выбранный уровень относительно `HEAD` и `python3 scripts/bump_version.py --check` проходит.

## Commit

Создай обычный локальный Conventional Commit, точно описывающий staged diff. Не используй `--amend`, `--no-verify` или `--allow-empty` без отдельного запроса.

После commit проверь `git log -1 --oneline` и `git status --short`. Сообщи hash, subject, состав, проверки и оставшиеся незакоммиченные изменения. Push не выполняй.
