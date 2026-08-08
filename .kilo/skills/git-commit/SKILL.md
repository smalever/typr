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

## Staged Gate

Проверь `git diff --staged --stat` и полный `git diff --staged`. Staged diff должен совпадать с прошедшим review и содержать все обязательные tests/docs companions без secrets и artifacts.

## Commit

Создай обычный локальный Conventional Commit, точно описывающий staged diff. Не используй `--amend`, `--no-verify` или `--allow-empty` без отдельного запроса.

После commit проверь `git log -1 --oneline` и `git status --short`. Сообщи hash, subject, состав, проверки и оставшиеся незакоммиченные изменения. Push не выполняй.
