# Шаблоны для заказчика

Готовые формы для сбора входных данных под [PLAN_PRODUKTA.md](../PLAN_PRODUKTA.md) фазу 0.

## Файлы

| Файл | Назначение | Кому |
|------|------------|------|
| [customer_questionnaire.md](customer_questionnaire.md) | Полный вопросник по данным, UI, инфра | Заказчик (аналитик + IT) |
| [use_case_card.md](use_case_card.md) | Одна карточка сценария (10–20 шт.) | Бизнес + аналитики |
| [ui_brief.md](ui_brief.md) | Экраны, layout, бренд, эталон ответа | Дизайн / BI-команда |
| [acceptance_criteria.md](acceptance_criteria.md) | Критерии приёмки ответов (L1–L4) | PM + руководство + аналитик |
| [workshop_agenda.md](workshop_agenda.md) | Повестка воркшопа 2–3 ч (фаза 0) | Ведущий воркшопа |

**Встреча с руководством:** [PAKET_DLYA_RUKOVODSTVA.md](../PAKET_DLYA_RUKOVODSTVA.md)

## Как использовать

1. **С руководством** — [PAKET_DLYA_RUKOVODSTVA.md](../PAKET_DLYA_RUKOVODSTVA.md) (45 мин, решения, демо).
2. PM отправляет `customer_questionnaire.md` ответственному со стороны заказчика.
3. Для приоритетных сценариев — копии `use_case_card.md` (по одной на UC).
4. Параллельно — `ui_brief.md` (дизайн) и `acceptance_criteria.md` (пороги качества).
5. Первая рабочая встреча — по `workshop_agenda.md`.
6. Материалы складываются в защищённое хранилище (вне git при необходимости).
7. Аналитик команды переносит согласованное в [domain/](../domain/) — см. [domain/README.md](../domain/README.md).
8. Сроки фаз 1–2 пересчитываются в [PLAN_PRODUKTA.md](../PLAN_PRODUKTA.md).

## Минимум для старта пилота

- DDL или экспорт схемы
- Словарь данных (хотя бы по ключевым колонкам)
- 10 эталонных SQL
- Anonymized sandbox (read-only)
- 5–10 заполненных карточек UC

Подробнее о блокерах: [PUTI_RAZRABOTKI.md](../PUTI_RAZRABOTKI.md) часть 4.