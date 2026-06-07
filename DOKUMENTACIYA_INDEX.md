# Индекс документации prototip

**Назначение:** единая точка входа — кто что читает, в каком порядке, что делать дальше.  
**Репозиторий:** https://github.com/Borisserz/prototip  
**Дата:** июнь 2026

---

## Текущий статус проекта

**Прототип готов к демонстрации.** Реализованы фазы 0–8, волны улучшения оркестрации 1–3, 146 автотестов (`pytest -m "not live"`). Система работает на синтетическом CSV через DuckDB и Ollama, собирает графики, дашборды и презентации.

**Полноценный продукт** — следующий этап: нужны материалы от заказчика (схема БД, метрики, use cases, дизайн). До их получения команда опирается на [PUTI_RAZRABOTKI.md](PUTI_RAZRABOTKI.md) и шаблоны в [templates/](templates/).

---

## Кому что читать

| Роль | С чего начать | Затем | Действие |
|------|---------------|-------|----------|
| **Руководство** | [OBZOR_DLYA_RUKOVODSTVA.md](OBZOR_DLYA_RUKOVODSTVA.md) часть 1 | [SRAVNENIE_S_EPSILON_METRICS.md](SRAVNENIE_S_EPSILON_METRICS.md) §1–2 | Демо: `streamlit run ui/streamlit_app.py` или `showcase/` |
| **PM / аналитик продукта** | [PUTI_RAZRABOTKI.md](PUTI_RAZRABOTKI.md) | [PLAN_PRODUKTA.md](PLAN_PRODUKTA.md) | Отправить заказчику [templates/customer_questionnaire.md](templates/customer_questionnaire.md) |
| **Разработчик (новый)** | [README.md](README.md) | [AGENTS.md](AGENTS.md) → [PROJECT_SPEC.md](PROJECT_SPEC.md) | `pytest -m "not live" -q` |
| **Разработчик (продукт)** | [PUTI_RAZRABOTKI.md](PUTI_RAZRABOTKI.md) | [PLAN_PRODUKTA.md](PLAN_PRODUKTA.md) фазы 0–5, [domain/README.md](domain/README.md) | Ждать/заполнять `domain/*.yaml` |
| **Заказчик** | [templates/customer_questionnaire.md](templates/customer_questionnaire.md) | [templates/use_case_card.md](templates/use_case_card.md) | Заполнить и передать команде |
| **QA** | [tests/DETAILED_TEST_PLAN.md](tests/DETAILED_TEST_PLAN.md) | [PROJECT_SPEC.md](PROJECT_SPEC.md) §тесты | `pytest -m "not live"` |

---

## Карта документов

| Документ | Аудитория | Содержание |
|----------|-----------|------------|
| **[DOKUMENTACIYA_INDEX.md](DOKUMENTACIYA_INDEX.md)** | Все | **Этот файл** — навигация |
| **[PUTI_RAZRABOTKI.md](PUTI_RAZRABOTKI.md)** | Команда, PM | Альтернативы, сценарии, блокеры, что делать без/с заказчиком |
| [README.md](README.md) | Разработчик | Быстрый старт, структура, API |
| [OBZOR_DLYA_RUKOVODSTVA.md](OBZOR_DLYA_RUKOVODSTVA.md) | Руководство | Простыми словами + архитектура агентов |
| [PLAN_PRODUKTA.md](PLAN_PRODUKTA.md) | PM, аналитики | Что запросить у заказчика, фазы 0–6, DoD продукта |
| [SRAVNENIE_S_EPSILON_METRICS.md](SRAVNENIE_S_EPSILON_METRICS.md) | Руководство, архитектор | Сравнение с enterprise BI (без RAG) |
| [PROJECT_SPEC.md](PROJECT_SPEC.md) | Разработчик | ТЗ прототипа, выполненные фазы, контракты |
| [AGENTS.md](AGENTS.md) | Разработчик, AI-ассистент | Правила кода, стек, бэклог |
| [tests/DETAILED_TEST_PLAN.md](tests/DETAILED_TEST_PLAN.md) | QA | Стратегия тестирования |

### Папки с артефактами

| Путь | Назначение | Статус |
|------|------------|--------|
| [templates/](templates/) | Шаблоны для заказчика (вопросник, карточка UC) | Готово к отправке |
| [domain/](domain/) | Скелеты semantic layer (YAML) | Demo-заполнение; не подключено к runtime |
| `app/domain/constants.py` | Текущий runtime: 8 колонок, типы графиков | Активно в коде |
| `showcase/` | Офлайн-портфолио для демо | Готово |

---

## Что сделано / что дальше (кратко)

| Область | Статус | Следующий шаг |
|---------|--------|---------------|
| Агенты и оркестрация | ✅ Волны 1–3 | Eval-набор, wave 4 (Job API) — см. PUTI_RAZRABOTKI |
| UI Streamlit | ✅ 4 вкладки, 2 режима | Рефактор модулей, мультиграфик в чате |
| Данные | ✅ Demo CSV | Sandbox БД заказчика → фаза 2 PLAN_PRODUKTA |
| Semantic layer | 🟡 constants.py | Заполнить `domain/*.yaml` → loader в коде (фаза 1) |
| Дизайн | 🟡 Gov-хардкод | `design/tokens.yaml` после брендбука |
| Production | ❌ | Auth, audit, мониторинг — фаза 5 |

Подробная матрица альтернатив и рекомендации: **[PUTI_RAZRABOTKI.md](PUTI_RAZRABOTKI.md)**.

---

## Рекомендуемый порядок чтения (30 минут)

1. **5 мин** — [README.md](README.md) §«Быстрый старт» + запуск UI.
2. **10 мин** — [PUTI_RAZRABOTKI.md](PUTI_RAZRABOTKI.md) §«Где мы» и §«Три сценария».
3. **10 мин** — [PLAN_PRODUKTA.md](PLAN_PRODUKTA.md) часть A (что нужно от заказчика).
4. **5 мин** — [AGENTS.md](AGENTS.md) §«Архитектура» (для разработчика).

---

## Связь документов

```
DOKUMENTACIYA_INDEX (вы здесь)
        │
        ├── PUTI_RAZRABOTKI ─── альтернативы, пути, приоритеты
        │         │
        │         └── PLAN_PRODUKTA ─── фазы, DoD, вопросник
        │                   │
        │                   └── templates/ ─── для заказчика
        │                   └── domain/ ─── semantic layer (целевой)
        │
        ├── OBZOR_DLYA_RUKOVODSTVA ─── для совещаний
        ├── SRAVNENIE_S_EPSILON ─── позиционирование vs enterprise
        └── README + PROJECT_SPEC + AGENTS ─── разработка прототипа
```

---

*При добавлении нового MD-файла обновляйте этот индекс и таблицу в README.md.*