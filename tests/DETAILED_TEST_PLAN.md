# План тестирования — prototip

Детальная стратегия для графиков, дашбордов, презентаций и PlannerAgent.  
Дополняет `pytest`-набор в `tests/`.

**Статус (июнь 2026):** 147 тестов собрано, **139** в быстром прогоне (`pytest -m "not live"`). 8 тестов с маркером `live` требуют Ollama.

**Гейты перед коммитом:**

```bash
ruff check . && ruff format --check .
python -m pytest -m "not live" -q
```

---

## Стратегия

- **pytest** + fixtures (`sample_df`, mocked `call_structured`, mocked executor).
- **Детерминизм:** тяжёлые/LLM-пути мокаются; `@pytest.mark.live` — опционально с реальной Ollama.
- **Контракты:** Pydantic-модели, data flow через `depends_on`, trace fidelity.
- **Визуал:** fig traces, RU labels, Br formatting, PNG size, 12 типов графиков.
- **UI:** smoke через импорт `ui/streamlit_app.py`, проверка строк/хелперов в `test_ui_smoke.py`, `test_ui_helpers.py`.
- **Негатив:** bad plans, LLM errors, empty data, partial planner failure.

---

## Покрытие по файлам

| Файл | Фокус |
|------|-------|
| `test_planner_agent.py` | repair, invoke, execute, orchestrated flows |
| `test_viz_charts.py` | build_chart, exports, 12 типов, penalties |
| `test_chart_agent.py` | ChartAgent + mock LLM |
| `test_chart_repair.py` | normalize, repair, aliases |
| `test_dashboard_agent.py` | KPI, composition, graceful |
| `test_presentation.py` | .pptx, slides, prefs |
| `test_orchestrator.py` | ask/dashboard/presentation facade |
| `test_showcase.py` | offline showcase, manifest paths |
| `test_ui_smoke.py` | импорт UI, ключевые строки |
| `test_ui_helpers.py` | хелперы streamlit_app |
| `test_drilldown.py` | фильтры с графика |
| `test_e2e.py` | сквозные сценарии (mocked) |

---

## 1. Графики (ChartAgent + viz)

**Unit:** mock `call_structured` → ChartSpec; правила area/scatter/waterfall; color=region.

**Integration:** `repair_chart_spec` → `build_chart` на sample с penalties.

**Нормализация:** `normalize_chart_spec` добавляет `highlight_category` и прочие defaults.

**Planner-orchestrated:** data → chart в плане → spec в trace → buildable.

**Ручные сценарии:** «динамика по регионам», «структура налогов (доли)», «корреляция», «водопад».

---

## 2. Дашборды (DashboardAgent)

**Unit:** mock composition → DashboardResult (KPI, charts, layout).

**Integration:** reuse ChartAgent на chart_ideas, graceful sub-errors.

**UI:** вкладка «Дашборд», post-gen editor, region filters (режим аналитика).

---

## 3. Презентации (PresentationAgent)

**Unit:** mock ask results → .pptx, exact slide count, prefs override.

**Integration:** visuals из ChartSpec, DeckNarrative, appendix.

**UI:** вкладка «Презентация», очередь, режимы «По вопросам» / «Одной темой».

---

## 4. PlannerAgent

**Unit:** `_repair_plan`, `_invoke_agent`, topo sort, brief results, quality scoring.

**Integration:** diamond (data → chart → analyst), high-level dashboard/pres plans.

**Trace:** `PlannerTrace` в результате, JSON download в UI (режим аналитика).

**Ошибки:** chart_agent fail → graceful, UI «Нет данных» без ложного анализа.

---

## 5. UI / UX (smoke + manual)

**Автоматически (smoke):**
- импорт `streamlit_app` без ошибок;
- наличие `GOV_DISCLAIMER`, `Мой дашборд`, `_render_unified_action_bar`;
- режимы `ui_mode`, глобальные фильтры.

**Ручная проверка:**
- переключатель «Для руководства» / «Для аналитика»;
- сворачивание/раскрытие сайдбара;
- drill-down по клику на графике;
- pin на «Мой дашборд»;
- сохранение сессии JSON.

---

## 6. Showcase

```bash
python scripts/generate_leadership_showcase.py
python -m pytest tests/test_showcase.py -q
```

- 12 chart types в каталоге;
- 4 presentation bundles;
- `manifest.json` — только относительные пути, без `slide_pngs` из `/tmp`.

---

## Live-тесты (опционально)

```bash
# Требует: ollama serve + qwen2.5-coder:7b-instruct
python -m pytest -m live -q
```

Использовать для проверки после смены модели или промптов.

---

## Чеклист перед демо руководству

1. `ollama list` — модель на месте.
2. `streamlit run ui/streamlit_app.py` — UI открывается, Ollama: ok.
3. Режим «Для руководства».
4. Happy-path запросы (30–90 с каждый):
   - «Какая задолженность по регионам?»
   - «Структура налогов по видам (доли)»
   - «Динамика начислений в г. Минск за год»
5. Showcase офлайн: открыть `showcase/presentations/01_obzor_nalogov_RB.pptx`.
6. При ошибке chart — карточка «Нет данных», не trace в режиме руководства.