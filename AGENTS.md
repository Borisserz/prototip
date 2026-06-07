# AGENTS.md — правила для разработки и AI-ассистентов

## О проекте

**prototip** — локальная мультиагентная BI-платформа для налоговой/гос-аналитики (Республика Беларусь, синтетические данные, валюта Br).

Пользователь задаёт вопрос на русском → система формирует SQL → получает таблицу → строит график и текстовые выводы → может собрать дашборд или презентацию. Всё офлайн через Ollama.

Это **прототип**, не production-система. Вдохновлён идеей executive BI (Epsilon Metrics-подобный сценарий), реализован на Python.

**Важно:** это Text-to-SQL по табличным данным, **не RAG**. Не предлагать векторный поиск по документам.

---

## Окружение

- **Машина:** MacBook Air M4 (Apple Silicon, Metal в Ollama).
- **Данные:** синтетический CSV `data/sample.csv`, без реальной БД.
- **SQL:** DuckDB выполняет `SELECT` по DataFrame/CSV in-memory.
- **Модель:** `qwen2.5-coder:7b-instruct` (Q4_K_M), `ollama pull qwen2.5-coder:7b-instruct`.
- **LLM:** всегда `temperature=0`, только structured output (JSON schema из Pydantic). Парсить свободный текст запрещено.

---

## Стек

| Слой | Технология |
|------|------------|
| API | FastAPI + uvicorn |
| UI | Streamlit (тонкий клиент → `Orchestrator`) |
| Контракты | Pydantic v2 |
| Данные | pandas + DuckDB |
| Графики | plotly + kaleido |
| Презентации | python-pptx |
| LLM | пакет `ollama` |
| Качество | pytest + ruff |

---

## Архитектура (актуальная)

```
UI / API / CLI
     ↓
Orchestrator (+ correlation_id)
  .ask()          → PlannerAgent (singleton, LRU-кэш)
  .dashboard()    → DashboardAgent (fast-path)
  .presentation() → PresentationAgent → slide_pipeline (без nested Planner)
     ↓
AgentExecutor + AgentRegistry (factory.get_executor / get_planner)
     ↓
data_agent → chart_agent → analyst_agent
dashboard_agent, presentation_agent (высокоуровневые)
     ↓
viz/charts.py (детерминированный рендер)
```

### Главный принцип графиков (spec-first)

LLM возвращает **ChartSpec** (Pydantic). Рисует только `viz/charts.py` + `viz/style.py`.  
**Никогда** не выполнять сырой код графиков от модели (`exec`, `eval`).

### PlannerAgent

- **Singleton** через `get_planner()` — один экземпляр, общий LRU-кэш (`PlannerResultCache`).
- Генерирует план из 1–3 задач (`Task` с `depends_on`).
- DAG-исполнение (ThreadPoolExecutor, RLock), injection `data` / `source_sql` / `chart_spec`.
- **Пропуск зависимых задач** при `success=False` у родителя.
- **Честная агрегация** AskResult: `success = data_ok AND chart_ok AND analyst_ok`.
- Прикрепляет `PlannerTrace` к результату (`executed_plan`, `plan_execution`, `agent_calls`).
- Высокоуровневые агенты вызывают sub-агентов внутри себя — sub-вызовы не дублируются в trace планировщика.

### PresentationAgent + slide_pipeline

- `app/slide_pipeline.py`: для каждого вопроса слайда — data_agent → chart_agent → analyst_agent.
- Контекст `presentation_subplan()` запрещает `planner_agent` / `presentation_agent` во вложенных планах.
- `get_executor(include_planner=False)` — без рекурсии планировщика.

### Базовые абстракции

- `BaseAgent` (`app/agents/base_agent.py`) — `name`, `description`, `run() → AgentResult`.
- `AgentExecutor` (`app/agents/executor.py`) — `executor.run(agent_name, request)`.
- Модели: `app/agents/models.py`, `ChartSpec` в `core/models.py`, re-export в `app/schemas.py`.

---

## Агенты

| Агент | Вход | Выход | Заметки |
|-------|------|-------|---------|
| **data_agent** | вопрос (+ drilldown filters) | SQL + records | SELECT only, whitelist колонок, самокоррекция |
| **chart_agent** | вопрос + data | ChartSpec | FEW_SHOT, `normalize_chart_spec` + `repair_chart_spec` |
| **analyst_agent** | вопрос + data (+ chart_spec) | AnalysisResult | 3–5 тезисов на русском |
| **dashboard_agent** | DashboardRequest | DashboardResult | KPI + 3–5 графиков, reuse ChartAgent |
| **presentation_agent** | вопросы / тема | PresentationResult | slide_pipeline → `.pptx`, DeckNarrative |
| **planner_agent** | вопрос | AskResult / Dashboard / Presentation | Оркестрация, trace |

---

## UI (Streamlit)

Файл: `ui/streamlit_app.py`. Логика — только через `Orchestrator.ask()` / `.dashboard()` / `.presentation()`.

### Вкладки

- **Аналитический вопрос** — чат, empty state с категориями сценариев.
- **Дашборд** — отдельный workspace для `Orchestrator.dashboard()`.
- **Презентация** — очередь слайдов + сборка `.pptx`.
- **Мой дашборд** — pinned items, compare mode.

### Режимы

- **Для руководства** — график + выводы; trace/SQL/редактор скрыты; конвейер сворачивается.
- **Для аналитика** — полная прозрачность: trace «Что было сделано», SQL, таблица, редактор графика.

### Сайдбар

Глобальные фильтры (region, tax_type, period) → `DrilldownContext`. Быстрые вопросы, история, экспорт сессии JSON.

### Ошибки визуализации

Если данных нет или `chart_agent` упал — короткая карточка «Нет данных для отображения», без ложного анализа и зелёного бейджа «Успешно».

---

## Жёсткие правила

1. Контракты — только Pydantic. Голые `dict` между модулями запрещены.
2. Графики — только через `viz/charts.py` и `viz/style.py`. Не хардкодить цвета вне `viz/`.
3. SQL — только `SELECT`, лимит строк, whitelist колонок.
4. Весь пользовательский текст — на русском.
5. Полная локальность — ничего в интернет (кроме `git push` разработчиком).
6. Перед коммитом: `ruff check . && python -m pytest -m "not live" -q`.
7. Не использовать LangChain.
8. Не поднимать реальную БД.

---

## Команды

```bash
pip install -r requirements.txt
python data/make_dataset.py
streamlit run ui/streamlit_app.py
uvicorn app.main:app --reload
python -m pytest -m "not live" -q
ruff check . && ruff format .
python scripts/generate_leadership_showcase.py
```

---

## Структура ключевых путей

| Путь | Назначение |
|------|------------|
| `app/orchestrator.py` | Фасад ask/dashboard/presentation |
| `app/slide_pipeline.py` | Пайплайн слайда презентации |
| `app/domain/constants.py` | ALLOWED_COLUMNS, CHART_TYPE_RU |
| `app/agents/planner_agent.py` | Планировщик (~1000 строк) |
| `OBZOR_DLYA_RUKOVODSTVA.md` | Документ для руководства |
| `app/chart_repair.py` | `normalize_chart_spec`, `repair_chart_spec` |
| `viz/charts.py` | `build_chart`, 12 типов |
| `ui/streamlit_app.py` | Основной UI |
| `showcase/` | Офлайн-демо для руководства |
| `out/` | Runtime-артефакты (gitignored) |

---

## Документация для разработки

| Документ | Когда читать |
|----------|--------------|
| [PAKET_DLYA_RUKOVODSTVA.md](PAKET_DLYA_RUKOVODSTVA.md) | Встреча с руководством |
| [DOKUMENTACIYA_INDEX.md](DOKUMENTACIYA_INDEX.md) | Точка входа: статус, навигация |
| [PUTI_RAZRABOTKI.md](PUTI_RAZRABOTKI.md) | Альтернативы, что делать без/с заказчиком |
| [PLAN_PRODUKTA.md](PLAN_PRODUKTA.md) | Фазы продукта, semantic layer |
| [domain/](domain/) | Целевой формат YAML (скелеты, не runtime) |

При архитектурных решениях — сначала PUTI_RAZRABOTKI, затем обновить INDEX и затронутые MD.

---

## Definition of Done

- Код типизирован, есть тест.
- `ruff` и `pytest -m "not live"` зелёные.
- Работает на `data/sample.csv`.
- Документация синхронизирована при изменении архитектуры/UI.

---

## Бэклог (не реализовано)

- Telegram-бот
- Evaluator качества планов
- Полный `go.Waterfall` с cumulative prep
- Auth, реальная БД, ETL
- Prompt lab / A-B моделей

---

## Чего НЕ делать

- Не тащить LangGraph на ранних этапах.
- Не выполнять код графиков от LLM.
- Не использовать модели >7B без явной просьбы (ноутбук).
- Не коммитить `out/`, `.venv/`, `.skills/`, локальные патчи.
- Не писать абсолютные пути пользователя в `showcase/manifest.json` — только относительные.