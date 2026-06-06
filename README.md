# prototip

Локальная мультиагентная BI-платформа (прототип) для налоговой/гос-аналитики.

**Phase 0–8 выполнены + эволюция (Dashboard + PlannerAgent v2.5+ интерактив + Phase 2 polish)** (строго по AGENTS.md / PROJECT_SPEC.md, гейты ruff+pytest).

- Каркас + все Phase + DashboardAgent (KPI + multi ChartSpec + layout + editor + filters) + PlannerAgent (Главный агент: generate/execute/repair/editing/trace/iteration).
- Данные: data/sample.csv (Беларусь, Br, 7 регионов, **penalties** колонка Phase 2; регенерируй `python data/make_dataset.py` при изменениях).
- Графики: фабрика 11 типов (bar/.../line/area/scatter/waterfall/horizontal_bar/donut/kpi/heatmap), Okabe-Ito + RU/Br стиль в viz/, spec-first (LLM только ChartSpec, детерминированный рендер), PNG/HTML экспорт, live plotly.
- Презентация: .pptx с exact count, prefs per-q, visuals из specs, narrative, recs; поддержка "from dashboard" / Planner.
- Логирование: [Agent]..., [AgentExecutor]..., stdout + артефакты.
- UI: streamlit run ui/streamlit_app.py — "🤖 Главный агент" (preview плана + редактирование + execute status + clean textual results + "Что было сделано" + trace JSON dl + iteration buttons + history), + dedicated tabs (полные визуалы + editors). Две render path. Тонкий клиент.
- Тесты: per-agent + viz + orchestrator + ui_smoke (Phase 1/2 polish: editing/trace/iteration/penalties/new types) + новый test_planner_agent.py (детальный: repair/invoke/execute/error/quality/Planner-orchestrated + penalties/new types) + DETAILED_TEST_PLAN.md. ruff + pytest зелёные.
- /health цел.

Полный сценарий (Python 3.11+):

```
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# данные (Беларусь)
python data/make_dataset.py

# модель (локально)
ollama pull qwen2.5-coder:7b-instruct

# тесты + линт
python -m pytest -q
ruff check . && ruff format .

# UI
streamlit run ui/streamlit_app.py

# или прямая презентация (3 вопроса)
python -c '
from app.agents.presentation_agent import PresentationAgent
agent = PresentationAgent()
res = agent.run([
    "Какие регионы имеют наибольшую задолженность по НДС?",
    "Динамика начислений подоходного налога в г. Минск по месяцам?",
    "Топ-3 региона по сумме имущественных налогов?",
])
print("Презентация:", res.pptx_path, "слайдов:", res.num_slides)
'

# API
uvicorn app.main:app --reload
```

## Архитектура (текущее)

Spec-first (графики) + явный пайплайн + **PlannerAgent v2.5+ как primary интерактивный оркестратор** ("Главный агент").

```
Streamlit (тонкий клиент) / CLI / тесты / API
        ↓
PlannerAgent (Главный) — generate_plan (structured + repair + correction) → preview/edit в UI
        ↓ execute_plan (topo sort, context injection data/source_sql по depends_on,
          _invoke_agent, graceful per-task, attach trace _plan_execution + briefs)
  - 1-3 Task: data_agent / chart_agent / analyst_agent / dashboard_agent / presentation_agent
  - Высокоуровневые (dashboard/presentation) сами вызывают sub (Data/Analyst/Chart/Orch) — sub не в Planner trace
  - Низкоуровневые цепочки (data → chart/analyst) — repair + injection
        ↓
Orchestrator.ask / .dashboard (legacy linear + для sub-calls внутри high-level)
        ↓
DataAgent (Text-to-SQL DuckDB, penalties-aware) → Analyst + ChartAgent (structured → ChartSpec 11 типов)
        ↓
viz/charts.py (det build_chart + apply_common_style) → plotly (live) / PNG (pres)
PresentationAgent → .pptx (exact slides, visuals из specs, narrative)
```

**Две render path в UI**:
- Главный агент: clean textual (title + summary + "Выводы") + "Что было сделано" (steps+briefs) + "Скачать trace (JSON)" (полный: plan/execution/specs/data/penalties). Kitchen (reasoning/SQL/LLM details) скрыт.
- Dedicated tabs (Графики/Дашборды/Презентация): полные интерактивные визуалы + post-gen editors (типы, фильтры), KPI grid, multi-plotly, prefs, outline, download.

**Главный принцип (Spec-first для графиков):** LLM возвращает только ChartSpec (Pydantic). Рендер — детерминированный код viz/charts.py + стиль viz/style.py (единый Okabe-Ito, RU, Br, no exec raw code — безопасность + красота).

Агенты (все через BaseAgent + Executor):
- DataAgent (Phase 2+): NL→SQL (DuckDB по CSV), самокоррекция, whitelist (вкл. penalties), только SELECT + LIMIT.
- AnalystAgent (Phase 3): 3-4 тезиса + вывод/ключ на русском.
- ChartAgent (Phase 4+): вопрос+данные → ChartSpec (area/scatter/waterfall rules + "по регионам" color enforcement).
- DashboardAgent: KPI (det) + 3-5 ChartSpec (reuse Chart) + layout + insights + data/source_sql. Graceful.
- PresentationAgent: по вопросам/теме → .pptx (exact num_slides, prefs override, visuals из specs в trace, DeckNarrative, recs).
- PlannerAgent (v2.5+): иерархический планировщик + execution с контекстом/ремонтом/trace. Интерактив в UI (edit + iterate).

Всё через Pydantic (никаких dict). Полностью локально (Ollama qwen2.5-coder:7b-instruct, temp=0, structured). Русский везде.

См. AGENTS.md (полный UI/Planner/следующий спринт), PROJECT_SPEC.md, tests/ (в т.ч. DETAILED_TEST_PLAN.md), core/llm.py, viz/, app/agents/planner_agent.py.

## Улучшения (Phase 1/2 polish + Planner v2.5+ + audit/docs refresh)
- **PlannerAgent v2.5+ (Главный агент)**: иерархическая оркестрация (1-3 Task, structured gen + сильный промпт + примеры для размытых "сводка", _repair_plan, self-correction, quality, topo, context injection data/source_sql). Полная интерактивность в UI: preview + редактирование (agent+desc), execute со st.status (шаги плана), clean textual render результатов (только text + "Выводы"; полные viz/graphs в trace JSON или dedicated tabs), "Что было сделано" (steps + briefs + статусы), "Скачать trace выполнения (JSON)" (полный payload с plan/execution/specs/data/penalties), кнопки итерации ("Повторить похожий вопрос", "Изменить план и выполнить заново" — форк в preview), richer history, "Можно продолжить". Graceful error handling. Две render path (clean в Главном vs full visuals в tabs).
- **Phase 2 dataset + визуализация**: penalties колонка (make_dataset.py + обновлённый committed sample.csv + DataAgent FEW_SHOT/ALLOWED + UI подсказки + flow в Chart/Dashboard/Analyst). area/scatter/waterfall в viz/charts.py (dispatch + style) + усиленные правила/FEW_SHOT/примеры в ChartAgent (накопительная → area, корреляция → scatter, водопад изменений → waterfall; color=region для "по регионам"+время). Тесты: test_planner_agent.py (orchestrated new types + penalties data flow), расширен test_viz_charts (build/exports/edges/Planner data + penalties).
- **Dashboard + Presentation**: "Выводы" (переименовано), редактор "Настройка графиков" + client filters + re-render, "в презентацию" (prefs + visuals из trace specs), exact num_slides + appendix, prefs override в PNG ребилде. Поддержка from-planner (вопросы/данные/спеки из trace).
- **UI polish + Главный агент**: st.status с реальными шагами, iteration/fork, trace dl usable для re-build, state across reruns, clean kitchen в planner flows, "Набор данных (демо)" с penalties hints. Smoke (test_ui_smoke.py Phase 1/2: editing/trace/iteration/penalties/new types mentions) + детальные тесты.
- **Тесты + docs + consistency**: новый test_planner_agent.py (repair/invoke/validate/quality/execute/error injection/Planner-orchestrated flows для charts/dash/pres + penalties/new types + property loops); test_core_models обновлён (11 ChartType); DETAILED_TEST_PLAN.md (artifact по плану); super full refresh AGENTS.md / PROJECT_SPEC.md / README.md + code comments (planner top docstring, ChartSpec, phases, UI описания, supported types/columns). ChartSpec Literal синхронизирован с viz + prompts (фикс latent validation bug для area/scatter/waterfall).
- **Прочее**: data regen в гейтах, Br/стиль везде, ruff/pytest зелёные перед коммитом, inline docs в sync.

Генерация "идеально" (примеры из исторических + Phase 2): "покажи сводку по налогам" → 1 dashboard (clean text + trace + iteration в Главном; или full KPI+charts+editor в dedicated); "динамика по регионам" (data+chart area/line+color, penalties flow, edit plan force type); "корреляция начислений и штрафов" → scatter; "водопад ..." → waterfall; презентация из дашборда (exact slides, visuals из specs в trace, count); penalties queries end-to-end (Data → viz/insights/kpi); edit mid-way + re-execute + trace dl usable.
