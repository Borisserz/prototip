# Semantic layer — целевой формат данных проекта

**Статус:** скелеты заполнены под **demo** (`data/sample.csv`). **Не подключены к runtime** — код по-прежнему использует `app/domain/constants.py` и FEW_SHOT в агентах.

**Цель:** при фазе 0 [PLAN_PRODUKTA.md](../PLAN_PRODUKTA.md) заменить содержимое этих файлов согласованными данными заказчика, затем фаза 1 — loader в Python (`app/domain/loader.py`).

## Файлы

| Файл | Назначение |
|------|------------|
| [schema_registry.yaml](schema_registry.yaml) | Таблицы, колонки, типы, grain |
| [metrics_catalog.yaml](metrics_catalog.yaml) | Бизнес-метрики и формулы SQL |
| [chart_playbook.yaml](chart_playbook.yaml) | Сценарий вопроса → тип графика |
| [sql_examples.yaml](sql_examples.yaml) | Эталонные SQL для few-shot DataAgent |
| [dashboard_templates.yaml](dashboard_templates.yaml) | Шаблоны дашбордов (layout, KPI, графики) |

Eval-набор вопросов: [tests/eval/golden_questions.yaml](../tests/eval/golden_questions.yaml).

## Как заполнять (фаза 0)

1. Воркшоп с аналитиками заказчика: валидация метрик и SQL.
2. Перенос из Confluence/Excel в YAML (один источник правды в git).
3. Подпись аналитика: «10 golden SQL корректны на sandbox».
4. Версионирование: тег `domain-v1.0` при старте пилота.

## Связь с кодом (фаза 1)

```
domain/*.yaml
     ↓ loader.py
prompt_builder.py → промпты Planner / DataAgent / ChartAgent
sql_guard.py      → валидация таблиц и JOIN
```

Альтернативы и приоритеты: [PUTI_RAZRABOTKI.md](../PUTI_RAZRABOTKI.md) §2.1–2.2.