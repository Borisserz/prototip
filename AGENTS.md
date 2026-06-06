# AGENTS.md

## О проекте
bi_multiagent_tax — локальная мультиагентная BI-платформа для налоговой/гос-аналитики.
Пользователь задаёт вопрос на русском → система формирует SQL-запрос к данным →
получает таблицу → делает текстовый анализ → строит КРАСИВЫЙ график → может собрать
презентацию. Всё работает оффлайн через локальную модель в Ollama.

Это прототип, вдохновлённый платформой Epsilon Metrics, но полностью свой, на Python.

ВАЖНО по терминологии: это Text-to-SQL (вопрос → SQL по данным), а НЕ RAG.
Не путай и не предлагай векторный поиск по документам.

## Окружение
- Машина: MacBook Air M4 (Apple Silicon, Metal-ускорение в Ollama).
- Реальной БД НЕТ. Данные — синтетический CSV-датасет (налоговые поступления по регионам Республики Беларусь, валюта Br).
- "Шаг с данными" эмулируем через DuckDB: SQL выполняется прямо по CSV/DataFrame,
  отдельную базу данных поднимать НЕ нужно.

## Локальная модель (Ollama)
- Основная модель: qwen2.5-coder:7b-instruct (Q4_K_M).
- Запуск: `ollama pull qwen2.5-coder:7b-instruct`.
- Всегда temperature=0 для генерации SQL и спецификаций графиков.
- Всегда использовать structured output (JSON schema по Pydantic-модели).
  Свободный текст вместо JSON парсить запрещено.

## Технологический стек
- Backend/API: FastAPI + uvicorn
- UI (демо): Streamlit — ТОНКИЙ клиент, который ходит в API. Бизнес-логику в UI не класть.
- Контракты между модулями: Pydantic v2 (ChartSpec, SqlResult и т.д.)
- Данные: pandas + DuckDB (SQL по датасету)
- Графики: plotly + kaleido (интерактив + экспорт PNG)
- Презентации: python-pptx
- LLM: пакет ollama
- Тесты/линт: pytest + ruff

## Архитектура (Spec-first)
Streamlit → FastAPI → Orchestrator (свой явный пайплайн), который вызывает агентов:
- DataAgent: вопрос → SQL → DataFrame (через DuckDB; только SELECT)
- AnalystAgent: DataFrame → текстовые выводы (на русском)
- ChartAgent: DataFrame → ChartSpec (Pydantic) → детерминированный рендер графика
- PresentationAgent: графики + выводы → .pptx

ГЛАВНЫЙ ПРИНЦИП графиков: LLM возвращает СПЕЦИФИКАЦИЮ (ChartSpec), а рисует график
наш детерминированный код в едином фирменном стиле. НИКОГДА не выполняй сырой код
графиков от модели через exec(). Это вопрос и красоты (единый стиль), и безопасности.

### Базовые абстракции (подготовка к PlannerAgent)
- `BaseAgent` (app/agents/base_agent.py): абстрактный базовый класс. Обязательные атрибуты: `name`, `description`. Абстрактный `run(self, request: Any, *args, **kwargs) -> AgentResult`. Метод `get_capabilities() -> dict`. Все агенты (Data/Analyst/Chart/Dashboard/Presentation) наследуются от него.
- `AgentResult` (app/agents/models.py): базовый Pydantic для всех результатов агентов. Поля: `success: bool`, `reasoning: str` (обязательно заполняется агентом — объяснение решений/выбора), `error: str | None`.
- `AgentRegistry` + `AgentExecutor` (app/agents/executor.py): реестр по имени + единая точка вызова `executor.run(agent_name, request, **kw) -> AgentResult`. Логирует все вызовы в формате `[AgentExecutor] call: ... / done: ... (Nms) / error: ...`. Простая обработка ошибок (возвращает failed AgentResult). Orchestrator постепенно использует executor вместо прямых вызовов.
- Модели для Planner (Task, Plan, AgentCall) уже объявлены в models.py — готовы к использованию.

Orchestrator оставлен тонким (только высокоуровневые ask / dashboard). Логика планирования и сложной маршрутизации — для будущего PlannerAgent.

## Жёсткие правила разработки
1. Двигаемся строго по фазам из PROJECT_SPEC.md. Не начинай следующую фазу,
   пока текущая не покрыта тестом и не запускается.
2. Все данные между модулями передаются только через Pydantic-модели. Голые dict запрещены.
3. Любой график строится ТОЛЬКО через модуль viz/charts.py и стиль из viz/style.py.
   Не хардкодь цвета/шрифты в других местах.
4. Работа с данными: только SELECT, лимит на число строк. Никаких изменяющих запросов.
5. Весь пользовательский текст (заголовки, подписи, выводы) — на русском языке.
6. Полная локальность: ничего не отправляем в интернет.
7. Перед коммитом: `ruff check . && ruff format .` и `pytest -q` должны быть зелёными.

## Порядок реализации (кратко; детали в PROJECT_SPEC.md)
Phase 0 — каркас проекта и зависимости. ✅ Готово
Phase 1 — КРАСИВЫЕ ГРАФИКИ: датасет, ChartSpec, единый стиль, фабрика графиков (в т.ч. area/scatter/waterfall Phase 2), экспорт в PNG. ✅ Готово
Phase 2 — DataAgent: NL → SQL по датасету через DuckDB, с самокоррекцией по ошибке. ✅ Готово (Phase 2+ обновлён под penalties)
Phase 3 — AnalystAgent: текстовые выводы по данным. ✅ Готово
Phase 4 — ChartAgent: модель выбирает тип графика и заполняет ChartSpec. ✅ Готово (Phase 2: усиленные правила/FEW_SHOT для area/scatter/waterfall + "по регионам" color)
Phase 5 — Orchestrator: единый пайплайн "вопрос → ответ + график". ✅ Готово
Phase 6 — PresentationAgent: сборка .pptx. ✅ Готово (поддержка prefs, exact count, from-planner flows)
Phase 7 — Streamlit UI + интеграция. ✅ Готово (Phase 1/2 polish: Главный агент интерактив, две render path)
Phase 8 — обработка ошибок, логирование шагов агентов, README, e2e-тесты. ✅ Готово (продолжаем расширять детальные тесты)

Эволюция: после Phase 8 добавлены DashboardAgent (полная интеграция) + PlannerAgent v2.5+ (иерархическая оркестрация с интерактивом в UI).

## Следующий спринт / Текущее состояние (post Phase 2 polish + audit refresh)
- **DashboardAgent** (реализован + UI интегрирован + Planner-ready): комплексный дашборд (KPI + 3–5 ChartSpec + layout + insights + data/source_sql). Полная интеграция в "📈 Дашборды" (st.metric, layout-driven plotly, "Настройка графиков" редактор типов + client filters, "Выводы", "в презентацию", export JSON). В Главном агенте — clean textual (только title/summary/insights + "полные в JSON").
- **PlannerAgent v2.5+** (Главный агент, полностью интерактивный, Phase 1+2 завершены + hardening):
  - generate_plan (сильный промпт + FEW_SHOT для размытых "сводка", self-correction, repair).
  - _repair_plan, _validate, _assess_quality, _topological_sort, _invoke_agent (defensive shapes + context data/source_sql по depends_on), _execute_plan (graceful per-task).
  - UI: preview плана + редактирование (select agent + text desc per task), "Выполнить план" (st.status с реальными шагами), чистый текстовый рендер результатов (без inline графиков/дашбордов — "график не надо вот показывать"), свёрнутый "Что было сделано" (шаги + briefs + статусы), "Скачать trace выполнения (JSON)" (полный: executed_plan + plan_execution + specs + data + penalties + timing), кнопки итерации ("🔁 Повторить похожий вопрос", "✏️ Изменить план и выполнить заново" — форк плана обратно в редактируемый preview), richer history (вопросы + plan info + insights), "Можно продолжить" suggestions.
  - Две render path: Главный агент (clean textual + trace/JSON для кухни) vs dedicated tabs (полные визуалы + редакторы).
  - Поддержка penalties (Data/Chart/Dashboard/Analyst), new chart types (area/scatter/waterfall) из Planner-данных, "по регионам" правила.
  - Trace показывает только top-level задачи плана (sub-calls высокоуровневых агентов скрыты, как задумано).
- Phase 2 dataset/UI polish завершён: penalties в sample.csv + make_dataset + ALLOWED + FEW_SHOT + UI hints; viz/charts + ChartAgent расширены под area/scatter/waterfall; тесты детализированы (test_planner_agent.py, расширения viz/ui_smoke + DETAILED_TEST_PLAN.md); docs синхронизированы (этот аудит).
- Telegram-бот (отложен).
- Дополнительные улучшения по запросу (Phase 3+: evaluator, более динамичная история, полный waterfall, больше колонок датасета, prompt lab и т.д.).
- Детальные тесты + docs refresh по запросу (см. план.md в сессии + tests/DETAILED_TEST_PLAN.md).

## Команды
- Установка: `pip install -r requirements.txt`
- Генерация датасета: `python data/make_dataset.py`
- API: `uvicorn app.main:app --reload`
- UI: `streamlit run ui/streamlit_app.py`
- Тесты: `pytest -q`

## Стиль кода
- Python 3.11+, обязательная типизация, docstring на публичных функциях.
- Маленькие чистые функции; модули viz/ и core/ — без побочных эффектов.
- Каждый новый модуль сопровождается тестом в tests/.

## Пользовательский интерфейс
UI (Streamlit) — тонкий клиент. Основная цель — понятность обычному пользователю (весь текст на русском, kitchen скрыт):

- **Вкладка «🤖 Главный агент»** (primary interactive entry, PlannerAgent v2.5+):
  - Пользователь вводит вопрос → показывается **preview плана** (1-3 задачи: agent + описание + deps).
  - **Редактирование перед выполнением**: selectbox агента + text_input описания для каждой задачи (значения сохраняются при rerun).
  - Кнопки: "✅ Выполнить план" (st.status показывает реальные шаги из (отредактированного) плана), "🔄 Перегенерировать план".
  - **Результат в чистом текстовом режиме** (специально для planner-originated): заголовок + summary + "Выводы" (bullets); полные графики/дашборды/презентации — только через "Скачать trace выполнения (JSON)" или dedicated tabs. Нет inline визуалов в чате Главного (по запросу Phase 1 polish: "график не надо вот показывать").
  - **"Что было сделано"** (свёрнутый экспандер по умолчанию): список шагов плана с иконками статусов (✅/❌/⚠️), deps, brief_result (rows / тип графика / kpi count / slides / insights / fallback / ошибка).
  - **"📥 Скачать trace выполнения (JSON)"**: полный payload (executed_plan, plan_execution, specs, data, source_sql, penalties и т.д.) — можно использовать для отладки или re-build.
  - **Итерация**: кнопки на результатах "🔁 Повторить похожий вопрос" (prefill input), "✏️ Изменить план и выполнить заново" (форк prior _executed_plan обратно в редактируемый preview в истории).
  - Richer history (в session): вопросы + plan info + insights; "Можно продолжить" suggestions.
  - Graceful: ошибки генерации/выполнения показываются дружелюбно; частичные результаты + полный trace; continue других задач при ошибке одной.
  - Две render path чётко разделены: Главный → clean textual + trace/JSON; dedicated tabs → полные интерактивные визуалы + редакторы.

- **Вкладка «📋 Данные»**: просмотр выборки (с penalties), статистика, кликабельные подсказки вопросов (в т.ч. Phase 2: "Штрафы (penalties) по регионам"), явная пометка «демо-данные» + "валюта Br, Phase 2: + penalties".

- **Вкладка «📊 Графики»**: тонкий клиент к Orchestrator/ChartAgent; живой plotly + экспорт; поддержка новых типов (через Planner или прямой).

- **Вкладка «📈 Дашборды»**: KPI st.metric grid + layout-driven multi plotly (build_chart), "Выводы", пост-ген редактор ("Настройка графиков": смена типов + re-render), client filters (напр. по region), "в презентацию", export JSON (полный: kpi/charts/data/source_sql). В Главном — clean mode.

- **Вкладка «📑 Презентация»**: два чётких режима — «По вопросам» (сворачиваемый блок с per-q prefs chart_type + note) и «Одним предложением» (большое поле темы). num_slides slider + live count, include title/recs, outline после генерации, download .pptx. Action "из дашборда" (из Главного или dedicated) передаёт вопросы + prefs + visuals из trace.

- Общее: скрыты все LLM kitchen (reasoning, "Почему этот тип?", sub-calls) из основного вида — только в свёрнутых "для разработчика" или в trace JSON. Онбординг, пустые состояния, строка состояния, простая in-memory история + быстрый repeat/iteration. Весь пользовательский текст на русском.

- Технические детали (SQL, reasoning, отладка, полный Plan JSON) — в сворачиваемых блоках или только в trace download.

## Definition of Done (для любой задачи)
- Код типизирован, есть тест, ruff чистый, функция/эндпоинт работает на sample-данных,
  результат соответствует фазе из PROJECT_SPEC.md.

## Чего НЕ делать
- Не тащить LangGraph на ранних фазах (оркестрацию пишем сами, явным пайплайном).
- Не поднимать реальную БД (работаем с CSV + DuckDB).
- Не выполнять сырой код графиков от LLM.
- Не использовать модели больше 7B без явной просьбы (ноутбук) локально стоит олама там qwen2.5-coder:7b-instruct.