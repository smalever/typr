# Документация Typr

## Назначение

Каталог содержит действующие архитектурные и developer-контракты Typr. Пользовательская установка, настройка и эксплуатация остаются в корневом `README.md`.

## Карта Документов

- `../AGENTS.md` - обязательный workflow ИИ-агента и правила безопасной работы с проектом.
- `../.kilo/skills/typr-codebase/SKILL.md` - проектная навигация и правила изменений.
- `../.kilo/skills/subagent-coordination/SKILL.md` - процедура делегирования изолированных задач.
- `../.kilo/skills/code-review/SKILL.md` - review незакоммиченных изменений с исправлениями.
- `../.kilo/skills/git-commit/SKILL.md` - локальный commit после обязательного review.
- `ARCHITECTURE.md` - runtime pipeline, компоненты, зависимости и инварианты.
- `DEVELOPMENT.md` - локальное окружение, команды проверок и границы hardware-dependent validation.
- `DOCUMENTATION_POLICY.md` - источники истины и матрица синхронизации code/tests/docs.

Kilo обнаруживает skills по YAML frontmatter в `.kilo/skills/*/SKILL.md`. После добавления, удаления или изменения skill перезагрузи project configuration либо начни новую сессию, чтобы гарантированно использовать актуальную версию.

## Правило Актуальности

Документы описывают текущее подтвержденное поведение. Если code и documentation расходятся, сначала установи источник расхождения, затем исправь implementation либо синхронно обнови code, tests и contract при осознанном изменении поведения.
