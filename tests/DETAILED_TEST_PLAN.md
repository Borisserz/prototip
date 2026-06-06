# Detailed Test Plan — Graphs, Dashboards, Presentations, Главный агент (PlannerAgent)

This artifact was created as part of the "Comprehensive Current State Audit + Detailed Test Strategy + Full Documentation Refresh" (plan.md from preper session).

It documents the **very detailed test strategy** for the 4 focus areas + cross-cutting (Planner-orchestrated flows, penalties column, new chart types area/scatter/waterfall, interactive editing/trace/iteration in Главный агент, two render paths, data flow, error handling, quality/minimality).

**Status**: Initial implementation done (see "Implemented coverage" below). Run with `python -m pytest tests/test_planner_agent.py tests/test_viz_charts.py -q --tb=line` (and full suite). Live Ollama tests are marked and optional.

## Overall Strategy (from plan)
- pytest + fixtures (sample_df with/without penalties/region, mocked call_structured / executor for determinism).
- Mock heavy/LLM for speed/CI; @pytest.mark.live for happy paths with real Ollama (qwen2.5-coder:7b-instruct, temp=0, structured).
- Assert: Pydantic contracts, data flow (source_sql + data passed via depends_on only), rendering (fig traces, Russian labels, Br, PNG size, no EN leaks), UI state via smoke + patches (messages, editing widgets values, history, buttons, expanders, download JSON), trace/JSON fidelity (_plan_execution + specs + data + steps + briefs), plan quality (minimality <=3, correct deps post-repair, high-level bias for broad/"сводка", "по регионам" color rules).
- Negative/edge: bad plans (unknown agent, missing deps, self-dep, >3), LLM errors (gen/execute/composition → graceful + trace error visible), empty data, unsupported ctype (build raises), bad prefs, penalties queries, region variety, edited plans mid-execution, error injection during Planner (one task fails → others continue + UI "ошибка" in "Что было сделано").
- Mix unit/integration/e2e (Planner full flows with UI-relevant attachments for clean render vs dedicated tabs full visuals).
- Property-ish loops (varied questions → quality/minimality/deps bias; type selection rules for area/scatter/waterfall).
- Focus: Planner-orchestrated (repair + context injection, new types from Planner data with penalties, editing/trace/iteration UI, clean textual in Главный агент).
- Coverage targets: key paths 100% (repair, invoke dispatch, clean render decision, trace attach, editing flow, data+penalties flow); >80% for changed Planner/Chart/Dashboard/Pres/viz/UI iteration.
- Gates: `ruff check . && ruff format . && python -m pytest -q -m "not live"` before commit. Add live marker runs for manual verification.

## 1. Graph Creation (ChartAgent + viz/charts.py + style)
**Unit (ChartAgent)**: mock call_structured → ChartSpec (area/scatter/waterfall + color=region for "по регионам", horizontal for top, etc.); assert spec + reasoning from rationale; soft val; diverse region sampling in prompt (via FEW_SHOT). Negative: LLM error → RuntimeError wrapper.

**Integration (ChartAgent → build_chart)**: real sample (penalties/region) + mocked specs for new types → correct fig (traces, hover, RU labels via get_russian_label, Br formatting, value labels, style). Assert no EN in titles/axes.

**viz unit (test_viz_charts.py extended)**:
- build_new_types_on_penalties_sample (area/scatter/waterfall with color=region, penalties y).
- waterfall_with_explicit_base (uses go.Bar base path).
- negative: bad col → ValueError; empty after filter → ValueError.
- new_types_from_planner_routed_data (build succeeds on Planner-passed df + new-type spec; RU/Br).
- exports_on_new_type (PNG/HTML size + content for pres from planner).
- Updated existing various + five_six + exports to exercise new + penalties data.
- Style: apply_common_style + hbar order + tick ru on new types.

**Planner-orchestrated**: mock plan data→chart (new type + penalties/region data injected) → execute → result has chart_spec (trace) → build_chart(df_from_context, spec) succeeds with correct type per rules (area for накопительная, scatter for корреляция, waterfall for водопад; color=region enforced).

**UI**: "Графики" tab + Главный агент (planner chart result → clean text + note "полные графики в JSON" + trace usable to re-build; dedicated tab full interactive plotly). Export works; no EN leaks.

**Manual scenarios** (user historical + new): "динамика ... по регионам" (area/line+color), "корреляция начислений и задолженности/штрафов" (scatter), "водопад начислений-уплата" (waterfall), vague vs specific, penalties queries ("штрафы по регионам"), edit plan to force type mid-way.

**Implemented coverage**: test_viz_charts.py extended with 5+ new tests for new types/penalties/Planner data/exports/edges. test_chart_agent.py updated allowed types set. test_planner_agent.py has orchestrated chart new-type + penalties flow + buildable spec.

## 2. Dashboards (DashboardAgent + UI rendering + Planner integration)
**Unit (DashboardAgent)**: mock Data (SqlResult with penalties), Analyst (insights), Chart (specs for ideas) + mock composition → full DashboardResult (kpi count/det, charts list with types, data+source_sql, insights, layout, reasoning). Test graceful empty → minimal valid + fallback insights. Det KPI ( _compute_basic_kpis ). Reuse Chart on "chart_ideas".

**Integration**: real sample (penalties) + mocked comp → specs → build_chart calls; data matches input; source_sql present; sub errors graceful.

**Planner-orchestrated**: plans with single dashboard_agent (broad "сводка") or data→...→dash (repair ensures); execute → result full fields + trace (only top-level dashboard_agent, subs not traced as designed). In Главный агент: clean textual render (title/summary/insights + "полные графики в JSON" per Phase 1 polish; no inline grid). Dedicated "📈 Дашборды" tab: full KPI grid + layout multi-plotly + post-gen editor (type change + re-render) + client filters (region) + "Выводы" + "в презентацию" + export JSON (full kpi/charts/data/source_sql).

**UI-specific**: post-gen editor + re-render; filters + re-render; action "в презентацию" feeds prefs/count to pres (visuals from specs in trace); JSON export fidelity; "Выводы" (renamed from Инсайты); action from Главный результат.

**Edges**: max_charts, no data, LLM comp error (fallback), bad idea col (soft), Planner + penalties data flow to kpi/charts.

**Manual**: "покажи дашборд по задолженности по регионам" via Главный (clean + trace + "Можно продолжить" + iteration) vs direct tab (full + editor + filters); KPIs accurate; charts match; trace has data/specs for re-use; editing works; cross to pres.

**Implemented**: test_dashboard_agent.py (existing unit/smoke) + test_planner_agent.py (orchestrated dashboard single-task + from-prior for pres), ui_smoke extended for Phase 2 features. Full e2e editor+re-render still mostly manual (smoke + patches); data flow asserted in planner tests.

## 3. Presentations (PresentationAgent + Orchestrator + UI)
**Unit (Pres)**: mock Orchestrator.ask (AskResult with chart_spec/data/analysis from prior), mock DeckNarrative → .pptx (exact slides: title cond, overview metrics, per-q with PNG from spec + pref override + source cleanup, side insights/conclusion, takeaways, recs cards, appendix if exact count). Test input norm (list[str]/list[dict]/PresentationInput), prefs override, num_slides early slice+appendix, graceful narrative fallback.

**Integration (real pipeline + data flow)**: real qs (incl. from Planner dashboard result or penalties) → ask → PNGs (style RU+Br+no dup source + pref) → .pptx structure (count, text, images) + narrative. Assert visuals from specs in trace.

**Planner-orchestrated**: plan with presentation_agent or "from dashboard" action (questions + prefs from prior Главный result/trace) → pres uses data/specs from trace; trace top-level only; result clean mode in Главный (text + trace JSON usable to re-build visuals).

**UI**: modes (collapsible "По вопросам" vs big "Одним предложением"); prefs per block + note; num_slides slider + live; outline after gen; download; "from dashboard" action; exact count respected.

**Edges**: empty qs (ValueError), bad prefs, num<min (appendix), narrative LLM err (fallback), Planner-routed edited plan or penalties data.

**Manual**: "сделай презентацию по [вопросы]" or from Главный dashboard result (exact slides, visuals from specs in trace, narrative, recs, count); open PPTX verify (RU, Br, count, cleaned sources, appendix); trace JSON usable; iteration (fork prior pres plan).

**Implemented**: Existing test_presentation.py + test_orchestrator cover base + prefs/count. test_planner_agent.py adds "pres from prior dashboard" orchestrated flow (mocked). ui_smoke + streamlit_app cover modes/prefs/outline/"from dashboard". Deep PNG content/slide count with Planner data mostly manual + smoke.

## 4. Main Agent / PlannerAgent — Super Detailed
**Unit (core)**: _repair_plan (adds deps for analyst/chart after data; ensures "question"; idempotent; handles LLM omissions like missing deps or "question" key). _invoke_agent (correct shapes: str for data, (q,data) for analyst/chart, DashboardRequest-ish for dash, list for pres; defensive q extraction; logs/warnings for missing data on deps). _validate (unknown, bad deps, order, self-dep). _assess_quality (penalties low-level broad, bonuses high-level, errors). _topo_sort. _make_brief (rows, chart type, kpi count, pres slides, insights, fallback, error). generate (prompt, structured, repair, correction on low qual<0.65 or errs, fallback to dash plan). execute (topo, injection only on deps, per-task try/except continue, attach trace with briefs). run (cache, wrap). _generate_plan internals.

**Integration (sub + context + cross)**: plans 1-task high (dash/pres) vs 2-task data→chart/analyst (explicit or missing deps → repair + context: data + source_sql flow to dependents); high-level sub-calls (inside dash/pres) still work (but not in Planner trace); penalties/region data flows correctly through to Chart/Dashboard/Analyst (SQL correct per DataAgent FEW_SHOT, viz new types, insights, kpi).

**Planner-orchestrated full flows (e2e)**: gen (repair/correction) → preview/edit (UI widgets change agent/desc, incl. for vague "сводка") → execute (repair/context) → result (clean textual in Главный + "Что было сделано" with steps/briefs + trace download JSON with _plan_execution + specs + data + steps + timing) → iteration (repeat q or fork plan via button → loads prior plan for re-edit/execute). Assert data flow (result has data when expected), quality (min, deps, bias), trace fidelity, UI state (messages, editing values persist, history updated, buttons), no crash partial.

**Quality/property**: many q (vague "сводка по налогам", "динамика по регионам", specific chart/pres, penalties qs) → assert minimality (1 high for broad), correct deps post-repair, high-level bias, valid, data flows (data+source_sql), new types per rules.

**Error/edge**: LLM fail gen → fallback dash plan (trace shows). Error one task execute → err in trace + "ошибка" status + continue others + final partial usable + full trace; UI shows error in "Что было сделано". Bad user edit (unknown agent) → validate catches. Empty data chain → graceful sub (fallback insights) + honest trace/UI. Edited mid + re-exec. Penalties in Data→Chart/Dash (correct SQL/viz/insights/kpi). Max 3 enforced. Self-dep/bad order.

**UI-specific for Главный (interaction)**: plan preview + editing (select agent, edit desc; values persist reruns) + execute status steps (from edited) + result clean mode (no graphs, just text + "Что было сделано" + dl button) + expander accurate on edited/partial + dl trace (JSON has plan/execution/specs/data/penalties/execution) + history (plan info + insights; re-use q; repeat/fork buttons) + "Можно продолжить". State across reruns. Error gen friendly. Cross-tab (planner res → "в презентацию" or dedicated full visuals).

**Integration other areas**: planner dashboard → "в презентацию" or direct (prefs, count, visuals from trace specs); planner chart → build (new types + Planner data); penalties/region → flows end-to-end; pres from planner dash (exact, visuals, narrative, count); trace JSON re-build (feed specs to build_chart or re-exec plan).

**Manual scenarios** (historical + new; run in Streamlit Главный + dedicated): vague "покажи мне сводку по налогам" (1 dash, clean text + trace + iteration + "Можно продолжить"); "динамика по регионам" (data+chart area/line+color, visuals in trace, edit plan force type); specific chart; pres request (pres_agent or from prior, exact count, visuals from specs); edit mid (high-level or deps) + re-exec; fork; trace JSON has everything (plan, steps, briefs, specs, data incl penalties, timing); "Что было сделано" accurate on edited/partial; no kitchen (reasoning/SQL) in main view for planner flows; penalties query (Data→Chart/Dash correct); new types from Planner; cross (planner dash → pres); errors (gen/execute fail → trace/UI graceful); iteration (history, repeat/fork, suggestions); UI state (editing persists, history updates, dl works, no crash rerun).

**Implemented coverage**: New tests/test_planner_agent.py (20+ tests covering repair/invoke/validate/quality/brief/topo/generate/execute/error injection/attachments/context/penalties/new-types-orchestrated/dashboard-pres-flows/property loops). test_ui_smoke.py already has Phase1/2 polish (editing, trace dl, "Что было сделано", iteration buttons, penalties/new types mentions, richer history). test_viz + chart_agent cover viz/planner-routed new types. Full interactive editing + state + manual Streamlit still primary for UI polish (smoke + this plan's manual section).

## Cross-area / E2E / Manual
- Full interactive Главный end-to-end with editing + new types + penalties + trace dl + iteration (repeat/fork) + "Что было сделано" + clean render.
- Planner pres from prior dashboard (prefs/count/visuals from trace specs).
- New types from Planner data (area cumulative, scatter corr, waterfall changes).
- Penalties queries Data→Chart/Dash (correct SQL per updated FEW_SHOT, viz, insights, kpi).
- Error injection Planner (gen fail / sub-task fail) → trace error, UI graceful, no crash.
- UI smoke + manual all tabs with Phase 2 (history, editing, trace, new types suggestions, penalties qs).
- Consistency: same q via Главный (clean textual + trace) vs dedicated tab (full visuals + editor/filters).
- Trace JSON usable to re-build (feed specs to build_chart or re-execute).
- Perf/edge: max 3, slow Ollama (status shows), empty sample, bad edits, edited+reexec, max tasks.

## Test Implementation Notes + Gaps Closed
- Extended: test_viz_charts.py (new types + penalties + planner data + exports + edges), test_chart_agent.py (allowed types), test_core_models.py (11 types + doc).
- Added: tests/test_planner_agent.py (full detailed units + orchestrated + errors + quality).
- Artifact: this file (tests/DETAILED_TEST_PLAN.md) + plan.md reference.
- UI interaction: smoke + patches in test_planner (for result attachments); full widget state/manual in Streamlit.
- No new big features; respected spec-first, Pydantic, Russian, local, thin UI.
- After changes: ruff + pytest green; data regenerated; docs refreshed (see separate step).

## Verification (this plan)
- ruff/pytest on test changes + core fixes.
- Manual Streamlit "Главный агент" + tabs with scenarios (vague summary, region dynamics, penalties, new types, edit plan, trace dl, iteration buttons, pres from dashboard, cross flows).
- Docs review + grep cross-check (no outdated Phase lists, chart types consistent 11, columns include penalties, UI Главный described with editing/trace/clean/iteration/two-paths).
- "detailed test plan" artifact created + useful.
- Any gaps found → noted (e.g. waterfall still basic approx not full go.Waterfall+cumulative prep; sub-calls of high-level not in Planner trace (by design); history in-mem only; "Можно продолжить" static-ish; full Playwright UI automation not added).

## Open (from original plan, for future)
- More property-based (hypothesis) or larger loops for plan quality/type selection.
- Full waterfall polish (data prep + go.Waterfall).
- Dynamic "Можно продолжить" from history.
- Sub-trace for high-level agents (if desired, would require executor changes).
- Dataset more columns?
- Telegram / Phase 3 (evaluator etc.).

This fulfills the "very detailed tests" + artifact requirement. Combined with doc refresh + gates + manual, the task is complete.

Run example:
```
python3 -m pytest tests/test_planner_agent.py tests/test_viz_charts.py tests/test_core_models.py tests/test_ui_smoke.py -q --tb=no
ruff check . && ruff format --check .
```
(Then full manual Streamlit verification + `python3 data/make_dataset.py` if data drift.)
