# prototip

Локальная мультиагентная BI-платформа (прототип) для налоговой/гос-аналитики.

**Phase 0–8 выполнены** (строго по AGENTS.md / PROJECT_SPEC.md, с гейтами ruff+pytest+/health).

- Каркас + DataAgent (Text-to-SQL DuckDB) + AnalystAgent (инсайты) + ChartAgent + Orchestrator + PresentationAgent (.pptx) + Streamlit UI.
- Данные: data/sample.csv (Беларусь, Br, 7 регионов).
- Графики: фабрика 8 типов, Okabe-Ito, русские подписи/числа, резкие 1000×600@2 PNG в out/, live plotly в UI.
- Презентация: out/presentation.pptx (титульный + слайды с PNG + 3 инсайта + вывод + общие).
- Логирование Phase 8: централизованно (core), шаги агентов в stdout + out/run.log в формате [Agent] action: details (Nms).
- UI: streamlit run ui/streamlit_app.py (тонкий, примеры, spinner, экспандер SQL).
- Тесты + ruff + format зелёные на каждом гейте. /health цел.

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

## Архитектура

Spec-first + явный пайплайн (без LangGraph).

```
Streamlit (тонкий) / CLI / тесты
        ↓
FastAPI (только /health пока; бизнес-логика не здесь)
        ↓
Orchestrator.ask(question)  — явный линейный пайплайн
        ↓
DataAgent: вопрос (ru) → безопасный SELECT SQL (через core/llm structured, temp=0) → DuckDB по data/sample.csv → SqlResult
        ↓
AnalystAgent + ChartAgent (параллельно по данным):
  - AnalystAgent: DataFrame → AnalysisResult (3-4 инсайта на ru, key_conclusion, anomaly)
  - ChartAgent: вопрос+данные → ChartSpec (Pydantic; модель выбирает тип по правилам: время→line, доли→donut и т.д.)
        ↓
viz/charts.py: build_chart(df, ChartSpec) → plotly fig (детерминировано, единый стиль из viz/style.py: Okabe-Ito палитра, русское форматирование, подписи)
        ↓
export_png → out/chart_*.png (и AskResult)
```

**Главный принцип (Spec-first для графиков):** LLM никогда не возвращает код графика и не выполняется через exec(). Модель возвращает только спецификацию ChartSpec (Pydantic), рендер — наш чистый детерминированный код в viz/ в едином фирменном стиле. Это и безопасность, и красота (один стиль на все графики).

Агенты:
- DataAgent (Phase 2): NL→SQL, самокоррекция до 3х, whitelist колонок, только SELECT + LIMIT.
- AnalystAgent (Phase 3): 3-4 тезиса + вывод на русском.
- ChartAgent (Phase 4): выбор типа + заполнение ChartSpec.
- PresentationAgent (Phase 6): оркестрирует несколько ask, собирает .pptx с PNG+инсайтами.
- Orchestrator (Phase 5): координирует, graceful degradation на ошибках шагов.

Всё через Pydantic контракты (никаких голых dict между модулями). Локально, Ollama qwen2.5-coder:7b-instruct, temperature=0 + structured output.

См. AGENTS.md, PROJECT_SPEC.md, out/ (png + pptx), core/llm.py, viz/charts.py.