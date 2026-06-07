# prototip

Локальная мультиагентная BI-платформа (прототип) для налоговой аналитики Республики Беларусь.  
Вопрос на русском → SQL по демо-датасету → данные → график → выводы → (опционально) дашборд или презентация `.pptx`.

Полностью офлайн через [Ollama](https://ollama.com). Синтетические данные, не для официальной отчётности.

**Репозиторий:** https://github.com/Borisserz/prototip

---

## Возможности

| Область | Что умеет |
|--------|-----------|
| **Агенты** | PlannerAgent оркестрирует Data / Chart / Analyst / Dashboard / Presentation |
| **Графики** | 12 типов, spec-first: LLM → `ChartSpec`, рендер — `viz/charts.py` |
| **Стиль** | Гос-оформление: Arial, `#003366`, русские подписи, валюта Br, Okabe-Ito |
| **UI** | 4 вкладки, режимы «Для руководства» / «Для аналитика», drill-down, закрепление графиков |
| **Showcase** | Офлайн-портфолио: 12 графиков + 4 презентации для демо руководству |
| **API** | FastAPI: `/health`, `/ask`, `/generate_dashboard`, `/generate_presentation` |
| **Тесты** | 146 автотестов (`pytest -m "not live"`), live e2e с Ollama |

---

## Быстрый старт

Требования: **Python 3.11+**, **Ollama**, ~8 ГБ RAM для `qwen2.5-coder:7b-instruct`.

```bash
git clone https://github.com/Borisserz/prototip.git
cd prototip

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Демо-датасет (если нужно пересоздать)
python data/make_dataset.py

# Модель
ollama pull qwen2.5-coder:7b-instruct

# Проверки
python -m pytest -m "not live" -q
ruff check .

# UI (основной способ работы)
streamlit run ui/streamlit_app.py
# → http://localhost:8501

# API (опционально)
uvicorn app.main:app --reload
# → http://127.0.0.1:8000/docs
```

### Презентация из CLI

```bash
python -c "
from app.orchestrator import Orchestrator
res = Orchestrator().presentation([
    'Какие регионы имеют наибольшую задолженность по НДС?',
    'Динамика начислений подоходного налога в г. Минск по месяцам?',
])
print('Файл:', res.pptx_path, '| Слайдов:', res.num_slides)
"
```

### Leadership showcase (без Ollama)

```bash
python scripts/generate_leadership_showcase.py
# → showcase/charts/, showcase/presentations/, showcase/manifest.json
```

---

## Интерфейс (Streamlit)

### Вкладки

1. **Аналитический вопрос** — чат с PlannerAgent, карточки сценариев, live-конвейер AI.
2. **Дашборд** — явный запрос комплексного дашборда (KPI + несколько графиков).
3. **Презентация** — очередь вопросов или одна тема → `.pptx`.
4. **Мой дашборд** — закреплённые графики из чата, режим сравнения.

### Режимы (переключатель в шапке)

| Режим | Для кого | Что видно |
|-------|----------|-----------|
| **Для руководства** | Совещание, отчёт | График, KPI, выводы; без SQL и trace |
| **Для аналитика** | Специалист BI | + SQL, таблица данных, trace, редактор графиков |

### Сайдбар

- Глобальные фильтры: регион, вид налога, период
- Быстрые вопросы и история
- Сохранение сессии (JSON)
- Метрики демо-датасета

### Действия на результате

PNG, CSV, «На дашборд», «В презентацию», drill-down по клику на графике.

---

## Архитектура

```
Streamlit UI / FastAPI / CLI / тесты
              ↓
         Orchestrator
    ask() → PlannerAgent (план 1–3 задачи, DAG, trace, честный success)
    dashboard() → DashboardAgent
    presentation() → PresentationAgent (slide pipeline, без nested Planner)
              ↓
    AgentExecutor → data_agent | chart_agent | analyst_agent | …
              ↓
    DuckDB (SELECT по CSV) → ChartSpec → viz/charts.py → Plotly / PNG
              ↓
    PresentationRenderer → .pptx
```

**Spec-first:** модель не генерирует код графиков — только Pydantic `ChartSpec`. Рендер детерминированный, тестируемый, в едином стиле.

Подробнее: [AGENTS.md](AGENTS.md), [PROJECT_SPEC.md](PROJECT_SPEC.md).

---

## Данные

Синтетический CSV: `data/sample.csv` (420 строк, 2024, 7 регионов РБ, 5 видов налогов).

| Колонка | Описание |
|---------|----------|
| `period` | Месяц (`2024-01` …) |
| `region` | Регион РБ |
| `tax_type` | Вид налога |
| `accrued` | Начислено, Br |
| `paid` | Уплачено, Br |
| `debt` | Задолженность, Br |
| `taxpayers` | Число плательщиков |
| `penalties` | Штрафы/пени, Br |

Генератор: `python data/make_dataset.py`

---

## Структура проекта

```
prototip/
├── app/
│   ├── agents/          # Data, Chart, Analyst, Dashboard, Presentation, Planner
│   ├── slide_pipeline.py # data→chart→analyst для слайдов презентации
│   ├── domain/          # Общие константы (колонки, типы графиков)
│   ├── orchestrator.py  # Единая точка входа
│   ├── main.py          # FastAPI
│   ├── chart_repair.py  # Нормализация и repair ChartSpec
│   ├── drilldown.py     # Фильтры с графика
│   └── showcase_*.py    # Офлайн-портфолио
├── core/
│   ├── models.py        # ChartSpec и контракты
│   └── llm.py           # Ollama structured output
├── viz/
│   ├── charts.py        # build_chart (12 типов)
│   └── style.py         # RU/Br/Okabe-Ito
├── ui/
│   ├── streamlit_app.py # Основной UI (~2500 строк)
│   └── components/      # pipeline, trace
├── data/                # sample.csv + make_dataset.py
├── showcase/            # Демо для руководства (PNG, HTML, PPTX)
├── scripts/             # generate_leadership_showcase.py
└── tests/               # 26 файлов, 146 non-live + 8 live тестов
```

---

## API

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/health` | Статус сервиса |
| POST | `/ask` | Универсальный запрос через PlannerAgent |
| POST | `/generate_dashboard` | Явный дашборд |
| POST | `/generate_presentation` | Генерация `.pptx` |

Пример:

```bash
curl -X POST http://127.0.0.1:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Какая задолженность по регионам?"}'
```

---

## Конфигурация

Переменные окружения `PROTOTIP_*`:

| Переменная | По умолчанию | Назначение |
|------------|--------------|------------|
| `PROTOTIP_OLLAMA_MODEL` | `qwen2.5-coder:7b-instruct` | Модель Ollama |
| `PROTOTIP_DATA_PATH` | `data/sample.csv` | Путь к CSV |
| `PROTOTIP_OUT_DIR` | `out/` | Артефакты (PNG, логи) |
| `PROTOTIP_PIPELINE_TIMEOUT` | `600` | Таймаут конвейера, с |
| `PROTOTIP_PLANNER_CACHE_SIZE` | `32` | Кэш планов Planner |

Артефакты сессий UI пишутся в `out/` (в git не попадают).

---

## Тестирование

```bash
# Быстрый прогон (без live Ollama)
python -m pytest -m "not live" -q

# Полный набор
python -m pytest -q

# Линт
ruff check . && ruff format --check .
```

Стратегия и чеклисты: [tests/DETAILED_TEST_PLAN.md](tests/DETAILED_TEST_PLAN.md).

---

## Типы графиков (12)

`bar`, `grouped_bar`, `stacked_bar`, `line`, `area`, `scatter`, `waterfall`, `treemap`, `horizontal_bar`, `donut`, `kpi`, `heatmap`

Data Storytelling-поля в `ChartSpec`: `action_title`, `show_average`, `highlight_category`.

---

## Документация

| Файл | Назначение |
|------|------------|
| [README.md](README.md) | Обзор, быстрый старт (этот файл) |
| **[OBZOR_DLYA_RUKOVODSTVA.md](OBZOR_DLYA_RUKOVODSTVA.md)** | **Обзор для руководства: простыми словами + полная архитектура** |
| [AGENTS.md](AGENTS.md) | Правила для разработки и AI-ассистентов |
| [PROJECT_SPEC.md](PROJECT_SPEC.md) | Техническое задание, фазы, критерии |
| [tests/DETAILED_TEST_PLAN.md](tests/DETAILED_TEST_PLAN.md) | Детальный план тестирования |

---

## Статус

Фазы 0–8 выполнены. Post-Phase 8: DashboardAgent, PlannerAgent v2.5+, gov UX, leadership showcase, drill-down, pinned dashboard. Волны 1–3 оркестрации: честный success, slide pipeline, retry LLM, singleton Planner, LRU-кэш.

**Не production:** нет реальной БД, auth, SLA, ETL. Прототип для демо и внутренней разработки.