---
name: subagent-coordination
description: Организует безопасное делегирование изолированных задач в Typr: исследование call sites, targeted tests, локальные механические правки и документационные companions с явными границами и приемкой.
---

# Координация Субагентов

## Назначение

Загрузи skill перед первым делегированием в нетривиальной задаче. `AGENTS.md` задает глобальные ограничения, `typr-codebase` - проектный контекст, этот skill - процедуру делегирования.

Основной агент сохраняет ownership архитектуры, concurrency, system permissions, clipboard behavior, интеграции и финальной приемки.

## Подходящие Задачи

Делегируй только когда результат однозначен, scope ограничен и приемка дешевле самостоятельного выполнения:

- read-only карта файлов, call sites и documentation companions;
- targeted unit/regression tests для уже определенного поведения;
- локальная механическая правка без изменения runtime contract;
- проверка stale imports, paths, translations и generated artifacts;
- актуализация одного документа по уже проверенной реализации.

Не делегируй самостоятельный выбор architecture, thread ownership, Qt lifecycle, clipboard restore semantics, `evdev`/`uinput` permissions, destructive uninstall behavior или работу с реальным API key и пользовательскими данными.

## Контракт Подзадачи

Prompt должен содержать:

```text
Цель и ожидаемый результат:
Source of truth или исследовательский вопрос:
Разрешенный read/write scope:
Запрещенные изменения и операции:
Acceptance criteria:
Проверки:
Формат отчета:
```

Для правок требуй минимальный diff. Запрещай commit, revert, массовое форматирование, чтение реальных пользовательских secrets и изменение несвязанных файлов.

## Параллельная Работа

Параллельно запускай только задачи без пересечения файлов, архитектурных решений и runtime resources. Файлы `app.py`, `config.py`, `pyproject.toml`, install scripts и канонические документы должны иметь одного writer на этап.

Не запускай конкурентные проверки, которые одновременно используют микрофон, `/dev/input`, `/dev/uinput`, clipboard или одну GUI session.

## Приемка

1. Проверь отчет, измененные файлы и полный diff.
2. Подтверди отсутствие выхода за scope и чтения secrets.
3. Сверь обязательные companions по `docs/DOCUMENTATION_POLICY.md`.
4. Независимо подтверди ключевой результат targeted проверкой или чтением ключевых ссылок.
5. При ошибке один раз продолжи тот же task с точным списком оставшейся работы; затем верни задачу основному агенту.

## Stop Conditions

Субагент возвращает blocker, если требуется изменить architecture, выйти за write scope, использовать реальные user config/history, выполнить privileged/destructive operation, запустить конфликтующий desktop resource или разрешить противоречие между code и contract.

## Итоговый Отчет

```text
Результат:
Измененные файлы или изученные источники:
Проверки и результат:
Невыполненные пункты:
Риски и предположения:
```
