# prototip

Локальная мультиагентная BI-платформа (прототип) для налоговой аналитики.  
Вопрос на русском → SQL по ClickHouse → данные → график → выводы → (опционально) дашборд или презентация `.pptx`.

Полностью офлайн через [Ollama](https://ollama.com). Синтетические данные, не для официальной отчётности.

**Репозиторий:** https://github.com/Borisserz/prototip

---

## Возможности

| Область | Что умеет |
|--------|-----------|
| **Оркестрация** | **LangGraph** оркестрирует Data / Chart / Analyst / Dashboard / Presentation. |
| **Графики** | 12 типов, spec-first: LLM → `ChartSpec`, рендер — `viz/charts.py` + Recharts на фронтенде |
| **Стиль** | Гос-оформление: Arial, `#003366`, русские подписи, валюта Br, Okabe-Ito |
| **UI** | React + Vite + TailwindCSS. Быстрые карточки, drill-down, SSE-стриминг |
| **RBAC** | Row-Level Security через `user_context` и инъекции `WHERE` в AST (sqlglot) |
| **RAG** | Векторный поиск внутри ClickHouse (`cosineDistance`) |
| **Semantic** | Парсинг YAML-слоя данных напрямую в Pydantic-схемы |
| **Аномалии** | Проактивный поиск отклонений в фоне и Email-уведомления (WatcherService) |
| **Визуализация**| Live-отображение дебатов агентов и анимация LangGraph графа на клиенте |
| **Analyst Mode**| Human-in-the-loop: прозрачный просмотр сгенерированного SQL прямо в UI чата |
| **Тесты** | 150+ автотестов (`pytest -m "not live"`), live e2e с Ollama, SQL Eval Pipeline |

---

## Быстрый старт

Требования: **Python 3.11+**, **Node.js 18+**, **Ollama**, **ClickHouse** (через Docker), ~8 ГБ RAM для `qwen2.5-coder:7b-instruct`.

```bash
git clone https://github.com/Borisserz/prototip.git
cd prototip

# 1. Запуск ClickHouse
docker-compose up -d

# 2. Бэкенд
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Модель
ollama pull qwen2.5-coder:7b-instruct

# Запуск API
uvicorn app.main:app --reload
# → http://127.0.0.1:8000/docs

# 3. Фронтенд (в новом окне терминала)
cd frontend_web
npm install
npm run dev
# → http://localhost:5173
```

---

## Интерфейс (React/Vite)

- **Чат (Аналитический вопрос)** — диалоговый интерфейс со стримингом через WebSocket (`/ws/chat`). 
- Потоковая генерация ответа от LangGraph, построение графиков на лету.
- **Drill-down** — клик по элементу графика (Recharts) → фильтр → уточняющий вопрос с контекстом.
- **Экспорт** в Excel, PNG.

---

## Архитектура

```
React UI (Vite) / FastAPI / CLI / тесты
              ↓
         LangGraph (StateGraph)
    ask_stream() → потоковая передача статусов
    dashboard() → DashboardAgent
    presentation() → PresentationAgent
              ↓
    SemanticEngine (парсинг YAML слоя данных)
              ↓
    Agent Nodes → data_node | chart_node | analyst_node | …
              ↓
    ClickHouse (нативный RAG и SELECT) + RBAC (sqlglot AST) → SQL Eval
              ↓
    viz/charts.py → Plotly / PNG / Recharts (frontend)
```

**Spec-first:** модель не генерирует код графиков — только Pydantic `ChartSpec`. Рендер детерминированный, тестируемый, в едином стиле.

Подробнее: [AGENTS.md](AGENTS.md), [OBZOR.md](OBZOR.md).

---

## Данные и Семантика

Синтетический CSV: `data/sample.csv`. Используется `data/semantic_model.yaml` для конфигурации семантического слоя:

- `region`: Регион РБ
- `tax_type`: Вид налога
- `accrued`: Начислено, Br
- ...

---

## Структура проекта

```
prototip/
├── app/
│   ├── graph.py         # Главный граф LangGraph
│   ├── agents/          # Агенты: Data, Chart, Analyst, Dashboard, Presentation
│   ├── semantic/        # Умный Семантический Движок (catalog.py)
│   ├── eval/            # SQL Evaluator (защита от галлюцинаций)
│   ├── orchestrator.py  # Единая точка входа
│   ├── main.py          # FastAPI
│   └── utils/           # ClickHouse клиент, RBAC (memory.py)
├── core/
│   ├── models.py        # ChartSpec и контракты
│   └── llm.py           # Ollama structured output
├── viz/                 # Рендер графиков (Plotly)
├── frontend_web/        # React + Vite + Tailwind UI
├── data/                # sample.csv + semantic_model.yaml
├── showcase/            # Демо для руководства (PNG, HTML, PPTX)
└── tests/               # 150+ автотестов
```

---

## API

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/health` | Статус сервиса |
| WS | `/ws/chat` | Основной WebSocket эндпоинт для чата (LangGraph) |
| POST | `/ask` | REST fallback (без стриминга) |
| POST | `/search` | RAG поиск по сессиям |

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

---

## Тестирование

```bash
# Быстрый прогон (без live Ollama)
python -m pytest -m "not live" -q

# Полный набор
python -m pytest -q

# E2E
python test_api.py
```

---

## Документация

| Файл | Назначение |
|------|------------|
| [README.md](README.md) | Обзор, быстрый старт (этот файл) |
| **[DOKUMENTACIYA_INDEX.md](DOKUMENTACIYA_INDEX.md)** | **Индекс: кому что читать, статус, навигация** |
| **[OBZOR.md](OBZOR.md)** | **Обзор для руководства: простыми словами + полная архитектура** |
| **[ROADMAP.md](ROADMAP.md)** | **Детальный план развития (Enterprise Features)** |
| **[SRAVNENIE_S_EPSILON_METRICS.md](SRAVNENIE_S_EPSILON_METRICS.md)** | **Сравнение со статьёй Epsilon Metrics (таблицы, логика)** |

---
