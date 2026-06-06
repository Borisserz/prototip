# PROJECT_SPEC.md — Техническое задание

## Цель проекта
Прототип мультиагентной BI-платформы: вопрос на русском → SQL по датасету →
данные → анализ → красивый график → (опционально) презентация. Локально, на Ollama.
Акцент заказчика — на КРАСИВЫХ, понятных, профессиональных графиках.

## Данные (вместо реальной БД)
Синтетический CSV: налоговые поступления по регионам Республики Беларусь (валюта Br).
Колонки (Phase 2+): period, region, tax_type, accrued, paid, debt, taxpayers, **penalties** (штрафы/пени, 5-18% от debt).
Генератор: data/make_dataset.py (региональные факторы, сезонность, одна аномалия, penalties). 420 строк (12 мес × 7 рег × 5 налогов).
SQL по этим данным выполняется через DuckDB прямо по DataFrame (DataAgent whitelist + LIMIT; обновлён под penalties в ALLOWED_COLUMNS + FEW_SHOT).

## Модули
1. Visualization (Phase 1) — фабрика графиков + единый стиль. Сердце проекта.
2. Data (Phase 2) — DataAgent: NL → SQL (DuckDB), только SELECT, самокоррекция.
3. Analyst (Phase 3) — выводы по данным (3–5 чётких тезисов, без воды).
4. ChartAgent (Phase 4) — выбор типа графика и заполнение ChartSpec.
5. Orchestrator (Phase 5) — явный пайплайн вызова агентов.
6. Presentation (Phase 6) — .pptx из графиков и выводов.
7. UI (Phase 7) — Streamlit поверх API.

## Фазы и критерии готовности

### Phase 0 — Каркас — Готово
- venv, requirements, структура папок, FastAPI /health, ruff.
- Готово: `uvicorn app.main:app` отвечает на /health.

### Phase 1 — Графики — Готово (Phase 2 расширения)
- Генератор синтетического датасета → data/sample.csv (Phase 2: + penalties).
- Модель ChartSpec (Pydantic, core/models.py): chart_type (Literal: bar/grouped_bar/stacked_bar/line/area/scatter/waterfall/treemap/horizontal_bar/donut/kpi/heatmap — 12 типов), title (RU), action_title/show_average/highlight_category (Data Storytelling), x/y/color (из колонок df), agg, source (RU), insights (RU тезисы), rationale. AnalysisResult: +data_explanation (explainability).
- Единая дизайн-система (viz/style.py + charts.py): Okabe-Ito палитра, русские лейблы (get_russian_label), Br форматирование, value labels, hover cleanup, hbar sort/order, tick ru (без SI B/M), apply_common_style. Никаких хардкодов цветов/шрифтов вне viz/.
- Фабрика графиков (viz/charts.py, spec-first): build_chart(df, ChartSpec) → go.Figure детерминировано. Поддержка всех 11 (area=px.area, scatter=px.scatter, waterfall — basic relative/bar-with-base; полная go.Waterfall + cumulative prep — в бэклоге). Экспорт PNG (kaleido, scale 2 для слайдов, ~1000x600 sharp) + HTML.
- Готово: на sample.csv (в т.ч. с penalties) строятся графики в едином стиле; тесты + экспорт; новые типы с правилами в ChartAgent.

### Phase 2 — DataAgent (Text-to-SQL по датасету) — Готово
- Описание схемы датасета (колонки + типы) для подсказки модели.
- NL → SQL через structured output; выполнение через DuckDB.
- Безопасность: только SELECT, белый список колонок, лимит строк.
- Самокоррекция: при ошибке выполнения вернуть текст ошибки модели и перегенерить (до N раз).
- Готово: на 5 типовых вопросах возвращает корректный исполняемый SQL и данные.

### Phase 3 — AnalystAgent — Готово
- Вход: вопрос + таблица. Выход: 3–5 тезисов на русском (тренды, аномалии, топы).
- Готово: осмысленные выводы по разным таблицам.

### Phase 4 — ChartAgent — Готово (Phase 2: новые типы)
- Вход: вопрос + данные (records). Выход: ChartAgentResult(spec: ChartSpec, reasoning).
- Structured (temp=0) + FEW_SHOT + сильный промпт. Правила (Phase 2): area для накопительной/сглаженной динамики (часто color=region); scatter для корреляций/распределений (x/y разные метрики); waterfall для изменений (x=шаги, y=change); "по регионам" + время → color="region" для line/area обязательно. "По регионам" → horizontal_bar для топов.
- Готово: модель выбирает + заполняет spec (валидация Pydantic); детерминированный рендер в viz/ (без exec).

### Phase 5 — Orchestrator — Готово
- Свой явный пайплайн: вопрос → DataAgent → (AnalystAgent + ChartAgent) → сборка ответа.
- Эндпоинт POST /ask {question} → {sql, data, insight, chart}.
- Готово: один вызов возвращает текст + график.

### Phase 6 — PresentationAgent — Готово
- Шаблон слайда, титульный + слайды (график + вывод), на русском.
- Готово: из нескольких вопросов собирается единый .pptx в фирменном стиле.

### Phase 7 — Streamlit UI — Готово
- Чат, отображение плана и шагов агентов, интерактивные графики,
  кнопка "Сгенерировать презентацию".

### Phase 8 — Финал — Готово (+ эволюция)
- Обработка ошибок, логирование [Agent]..., README, e2e-тесты.
- Пост-Phase 8: DashboardAgent + PlannerAgent v2.5+ (интерактивный, repair, editing/trace/clean render в UI, Phase 2 polish: penalties + area/scatter/waterfall + iteration/history buttons).
- Детальные тесты (test_planner_agent.py + расширения viz/ui_smoke + DETAILED_TEST_PLAN.md) + docs refresh по аудит-плану.

## Следующий спринт / Текущее (post-audit)
- PlannerAgent v2.5+ + UI polish (интерактив generate/edit/execute/trace/iteration/"Что было сделано"/clean render в Главном агенте; две render path; penalties + new types end-to-end). Реализовано + детальные тесты + docs синхронизированы.
- DashboardAgent: реализован + интегрирован (KPI grid, layout multi-chart, post-gen editor "Настройка графиков", client filters, "Выводы", actions, full Planner support в clean mode).
- Визуализация: area/scatter/waterfall в viz + ChartAgent (правила/FEW_SHOT); waterfall пока basic (бэклог: full go.Waterfall + cumulative prep).
- Dataset: penalties добавлены (make_dataset + sample.csv + DataAgent/FEW_SHOT/UI hints). Можно расширять (ещё колонки?).
- Telegram-бот (отложен).
- Phase 3+: evaluator качества планов/результатов, кэширование, больше экспортов, prompt lab, динамическая история/"Можно продолжить".
- Дополнительные улучшения по запросу (см. AGENTS.md "Следующий спринт").

## Принципы (повтор ключевого)
- Spec-first для графиков (красота + безопасность).
- Один стиль на всю систему.
- Это Text-to-SQL, данные — только на чтение.
- Structured output во всех вызовах LLM.
- Русский везде, полная локальность.

## Подготовка к иерархической архитектуре (PlannerAgent) — Phase 2.x + реализация
Рефакторинг + полная реализация PlannerAgent v2.5+ (интерактивный "Главный агент"):

- Модели: app/agents/models.py (AgentResult базовый + Task/Plan/AgentCall), core/models.py (ChartSpec с 12 типами), schemas.py (re-export для API/UI).
- BaseAgent + AgentRegistry/Executor (единый вызов, логи `[AgentExecutor] call... / done... (Nms)`).
- PlannerAgent: generate_plan (structured + сильный промпт + repair + self-correction + quality scoring), execute_plan (topological sort + injection только data/source_sql по depends_on + _invoke_agent с корректными формами + graceful per-task + attach _executed_plan/_plan_execution/_agent_calls).
- UI (streamlit_app.py «Главный агент»): preview + per-task editing (agent select + desc edit), execute со st.status (шаги из плана), clean textual render результатов (title/summary/insights; полные viz только в trace JSON или dedicated tabs), "Что было сделано" (steps + briefs + статусы), "Скачать trace выполнения (JSON)", iteration buttons (repeat / fork plan), richer history, "Можно продолжить".
- Две render path чётко: Главный (clean + trace/JSON, kitchen скрыт) vs dedicated tabs (KPI grid, multi plotly, editors, filters, full visuals).
- Phase 2: penalties в данных + agents + viz + UI + tests; area/scatter/waterfall (ChartAgent + viz + Planner-orchestrated); детальные тесты + DETAILED_TEST_PLAN.md + docs refresh (этот аудит).
- Высокоуровневые агенты (dashboard/presentation) вызывают sub напрямую (sub не в Planner trace); низкоуровневые цепочки — через repair/context.
- Orchestrator сохранён для ask/dashboard (legacy/linear).

Planner теперь — основной интерактивный оркестратор. Полностью spec-first, Pydantic контракты, graceful, скрытие деталей, русский, локально.