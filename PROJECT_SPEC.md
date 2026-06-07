# PROJECT_SPEC.md — техническое задание

## Цель

Прототип мультиагентной BI-платформы: вопрос на русском → SQL по датасету → данные → анализ → профессиональный график → (опционально) дашборд или презентация. Локально, на Ollama.

Акцент: **красивые, понятные, единообразные графики** в гос-стиле для демо руководству.

---

## Данные

Синтетический CSV — налоговые поступления по регионам РБ (валюта Br).

| Колонка | Тип | Описание |
|---------|-----|----------|
| `period` | string | `2024-01` … `2024-12` |
| `region` | string | 7 регионов РБ |
| `tax_type` | string | 5 видов налогов |
| `accrued` | float | Начислено |
| `paid` | float | Уплачено |
| `debt` | float | Задолженность |
| `taxpayers` | int | Плательщики |
| `penalties` | float | Штрафы/пени (5–18% от debt) |

- **Файл:** `data/sample.csv` (420 строк, committed).
- **Генератор:** `data/make_dataset.py` (сезонность, аномалия, региональные факторы).
- **SQL:** DuckDB in-memory по DataFrame. DataAgent: whitelist + `LIMIT`, только `SELECT`.

---

## Модули

| # | Модуль | Статус | Описание |
|---|--------|--------|----------|
| 1 | Visualization | ✅ | `viz/charts.py`, `viz/style.py`, 12 типов |
| 2 | DataAgent | ✅ | NL → SQL, самокоррекция |
| 3 | AnalystAgent | ✅ | Текстовые выводы |
| 4 | ChartAgent | ✅ | Вопрос + data → ChartSpec |
| 5 | Orchestrator | ✅ | Фасад ask / dashboard / presentation |
| 6 | PresentationAgent | ✅ | `.pptx` из графиков и выводов |
| 7 | Streamlit UI | ✅ | 4 вкладки, 2 режима, drill-down |
| 8 | PlannerAgent | ✅ | Иерархическая оркестрация, trace |
| 9 | DashboardAgent | ✅ | KPI + multi-chart + layout |
| 10 | Showcase | ✅ | Офлайн-портфолио для руководства |
| 11 | FastAPI | ✅ | `/health`, `/ask`, dashboard, presentation |

---

## Фазы (все выполнены)

### Phase 0 — Каркас ✅
venv, requirements, FastAPI `/health`, ruff, pytest.

### Phase 1 — Графики ✅
- `ChartSpec` (Pydantic, `core/models.py`): 12 `chart_type`, storytelling-поля.
- `build_chart(df, spec)` → Plotly, единый стиль Okabe-Ito, RU/Br.
- Экспорт PNG (kaleido) + HTML.

### Phase 2 — DataAgent ✅
NL → SQL (structured), DuckDB, whitelist, penalties в схеме и FEW_SHOT.

### Phase 3 — AnalystAgent ✅
3–5 тезисов, `key_conclusion`, `data_explanation`.

### Phase 4 — ChartAgent ✅
Structured ChartSpec, правила типов (area/scatter/waterfall, color=region).

### Phase 5 — Orchestrator ✅
Явный пайплайн, `POST /ask`.

### Phase 6 — PresentationAgent ✅
`.pptx`, титульный, слайды с графиками, рекомендации.

### Phase 7 — UI ✅
Streamlit чат, графики, презентация.

### Phase 8 — Финализация ✅
Логирование `[Agent]`, e2e-тесты, обработка ошибок.

### Post-Phase 8 (текущее состояние) ✅

- **PlannerAgent v2.5+:** generate/execute/repair, trace, LRU-кэш, DAG-параллелизм.
- **DashboardAgent:** KPI, layout, post-gen editor, client filters.
- **Gov UX:** disclaimer, режимы руководство/аналитик, 4 вкладки, unified actions.
- **Drill-down:** клик на графике → фильтр → уточняющий вопрос.
- **Pinned dashboard:** закрепление и сравнение графиков.
- **Showcase:** `scripts/generate_leadership_showcase.py` → `showcase/`.
- **Chart repair:** `normalize_chart_spec`, `repair_chart_spec` перед рендером.
- **Тесты:** 146 non-live + 8 live, `test_agent_waves.py`, `test_planner_agent.py`.

### Волны улучшения оркестрации (1–3) ✅

**Волна 1 — честность и баги:**
- Singleton `PlannerAgent` (`get_planner()`), без дублирования в Presentation.
- `_aggregate_result()` уважает `success` data/chart/analyst.
- Пропуск зависимых задач при failed parent.
- `slide_pipeline.py` для презентаций (data→chart→analyst).
- AnalystAgent: `degraded=True`, `success=False` на fallback.

**Волна 2 — качество:**
- `data_sampling.py` — профиль + стратифицированная выборка для промптов.
- Retry ChartAgent (3 попытки) и `core/llm.py` (retry + JSON-repair).
- `app/domain/constants.py` — единый источник колонок и CHART_TYPE_RU.

**Волна 3 — архитектура:**
- `agent_context.py` — запрет planner/presentation во вложенных планах.
- `correlation_id` в Orchestrator и AgentCall.
- `PlannerResultCache` с mtime датасета.
- RLock в DAG-исполнении (fix deadlock).

---

## ChartSpec (контракт)

```text
chart_type: bar | grouped_bar | stacked_bar | line | area | scatter |
            waterfall | treemap | horizontal_bar | donut | kpi | heatmap
title, subtitle, x, y, color, agg, source, insights, rationale
action_title, show_average, highlight_category, top_n, sort_order
```

Рендер: `viz/charts.py`. Нормализация: `app/chart_repair.py`.

---

## UI (критерии Phase 7+, актуализировано)

### Вкладки
1. Аналитический вопрос (чат + Planner)
2. Дашборд (workspace)
3. Презентация (очередь + сборка)
4. Мой дашборд (pinned)

### Режимы
- **Руководство:** результат без технических деталей.
- **Аналитик:** SQL, trace, данные, редактор.

### Сайдбар
Глобальные фильтры, быстрые вопросы, история, экспорт сессии.

### Поведение при ошибках
Нет данных / упал chart_agent → «Нет данных для отображения», без ложного «Успешно проанализировано».

---

## API

| Endpoint | Метод | Описание |
|----------|-------|----------|
| `/health` | GET | Healthcheck |
| `/ask` | POST | `{question, drilldown?}` → PlannerAgent |
| `/generate_dashboard` | POST | DashboardRequest → DashboardResult |
| `/generate_presentation` | POST | PresentationRequest → PresentationResult |

---

## Showcase (leadership)

```
showcase/
├── manifest.json      # относительные пути, без /tmp
├── charts/01_bar/     # chart.png, chart.html, spec.json
│   … (12 типов)
└── presentations/     # 4 executive .pptx
```

Генерация: `python scripts/generate_leadership_showcase.py` (без Ollama).

---

## Тестирование

```bash
python -m pytest -m "not live" -q   # 146 тестов
python -m pytest tests/test_e2e.py -m live   # сквозной прогон с Ollama
ruff check .
```

Детали: `tests/DETAILED_TEST_PLAN.md`.

Гейты перед коммитом: ruff + pytest (not live).

---

## Принципы

1. **Spec-first** для графиков (безопасность + единый стиль).
2. **Pydantic** между всеми модулями.
3. **Text-to-SQL**, только чтение.
4. **Structured output**, temperature=0.
5. **Русский** во всём пользовательском UI.
6. **Локальность** — Ollama, без облака.

---

## Бэклог

| Задача | Приоритет |
|--------|-----------|
| Полный go.Waterfall (cumulative) | Средний |
| Evaluator качества планов | Средний |
| Кэширование LLM-ответов | Низкий |
| Telegram-бот | Отложен |
| Реальная БД + auth | Вне scope прототипа |
| Рефакторинг `streamlit_app.py` на модули | Средний |

---

## Ссылки

- [README.md](README.md) — быстрый старт
- [OBZOR_DLYA_RUKOVODSTVA.md](OBZOR_DLYA_RUKOVODSTVA.md) — обзор для руководства
- [SRAVNENIE_S_EPSILON_METRICS.md](SRAVNENIE_S_EPSILON_METRICS.md) — сравнение со статьёй Epsilon Metrics
- [AGENTS.md](AGENTS.md) — правила разработки
- [tests/DETAILED_TEST_PLAN.md](tests/DETAILED_TEST_PLAN.md) — тест-стратегия