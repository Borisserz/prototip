# 🧠 PROTOTIP BI — Полная Архитектурная Документация

> **Версия:** 1.0 · **Дата:** Июнь 2026 · **Статус:** Production-ready Prototype  
> Мультиагентная BI-платформа с поддержкой естественного языка, ClickHouse и LangGraph

---

## Содержание

1. [Что это и зачем](#1-что-это-и-зачем)
2. [Технологический стек](#2-технологический-стек)
3. [Высокоуровневая архитектура](#3-высокоуровневая-архитектура)
4. [Граф агентов (LangGraph)](#4-граф-агентов-langgraph)
5. [Все агенты и их взаимодействия](#5-все-агенты-и-их-взаимодействия)
6. [Backend — модули и API](#6-backend--модули-и-api)
7. [Frontend — компоненты и UI-потоки](#7-frontend--компоненты-и-ui-потоки)
8. [Безопасность (RBAC / RLS)](#8-безопасность-rbac--rls)
9. [Семантический слой (MDL)](#9-семантический-слой-mdl)
10. [RAG-подсистема](#10-rag-подсистема)
11. [Проактивная аналитика (WatcherService)](#11-проактивная-аналитика-watcherservice)
12. [Data Flow — от вопроса к ответу](#12-data-flow--от-вопроса-к-ответу)
13. [Pydantic-контракты между агентами](#13-pydantic-контракты-между-агентами)
14. [Что реализовано на фронте](#14-что-реализовано-на-фронте)
15. [Анализ: что готово к демонстрации](#15-анализ-что-готово-к-демонстрации)
16. [Пути развития (Roadmap)](#16-пути-развития-roadmap)
17. [Как запустить](#17-как-запустить)

---

## 1. Что это и зачем

**prototip** — локальная мультиагентная платформа бизнес-аналитики для государственных организаций.

Сотрудник задаёт вопрос **на русском языке** (например: *«Покажи задолженность по регионам за 2024 год»*), а система:

1. **Понимает** запрос через Умный Семантический Движок (MDL + RAG)
2. **Планирует** выполнение через LangGraph StateGraph
3. **Извлекает данные** через безопасный Text-to-SQL → ClickHouse
4. **Проверяет себя** через двухуровневый SQL Eval Pipeline (синтаксис + логика)
5. **Анализирует** через AnalystAgent с Z-Score аномалиями и Reviewer CDO
6. **Визуализирует** — дашборд с KPI-картами, 3–5 графиков, инсайты
7. **Формирует** презентацию PowerPoint или экспортирует в Excel

Всё **офлайн** — без облака, без интернет-передачи данных.

---

## 2. Технологический стек

| Слой | Технология | Версия | Назначение |
|------|------------|--------|-----------|
| **LLM** | Ollama + `qwen2.5-coder:7b-instruct` | локально | Генерация SQL, аналитика, презентации |
| **Оркестрация** | LangGraph (`StateGraph`) | latest | Граф агентов, циклы, retry, стриминг |
| **База данных** | ClickHouse | latest | DWH, выполнение SQL, RAG (cosineDistance) |
| **Бэкенд** | Python 3.11+ / FastAPI | latest | REST + WebSocket + SSE |
| **Безопасность SQL** | SQLGlot | latest | AST-парсинг, инъекция WHERE (RLS) |
| **Семантика** | Pydantic + YAML | latest | MDL-слой, бизнес-глоссарий |
| **RAG** | LangChain + ChromaDB | latest | Документы, схемы, дашборды |
| **Фронтенд** | React 18 + TypeScript + Vite | latest | SPA с WebSocket |
| **CSS** | TailwindCSS v3 | latest | Тёмная тема, glassmorphism |
| **Анимации** | Framer Motion | latest | Переходы, micro-animations |
| **Графики** | Recharts | latest | Bar, Line, Pie, Area, Radar |
| **Observability** | Prometheus (fastapi-instrumentator) | latest | Метрики, мониторинг |
| **Email** | smtplib + APScheduler | latest | Расписание доставки отчётов |
| **PDF** | PyMuPDF (fitz) + python-pptx | latest | Извлечение текста + генерация PPTX |
| **Контейнеризация** | Docker Compose | latest | ClickHouse + Airflow |

---

## 3. Высокоуровневая архитектура

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      FRONTEND (React + Vite + TailwindCSS)                  │
│  ┌──────────┐  ┌──────────────┐  ┌──────────────────┐  ┌────────────────┐  │
│  │   Chat   │  │  AI Dashboard│  │  Presentation    │  │  Workspace DB  │  │
│  │  (WS чат)│  │  (KPI+Charts)│  │  (PPTX просмотр) │  │  (CSV/XLSX)   │  │
│  └──────────┘  └──────────────┘  └──────────────────┘  └────────────────┘  │
└─────────────────────────────┬───────────────────────────────────────────────┘
                              │ WebSocket ws://localhost:8000/ws/chat
                              │ REST API http://localhost:8000
                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                       FASTAPI (app/main.py)                                  │
│  /ws/chat (WebSocket + Pipeline Stream)   /generate_dashboard                │
│  /ask (REST)                              /generate_presentation             │
│  /api/v1/pdf/analyze                      /api/v1/workspace/upload           │
│  /api/export/excel                        /api/v1/sessions                   │
│  /api/v1/trigger_watcher                  /api/v1/download                  │
└─────────────────────────────┬───────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    ORCHESTRATOR (app/orchestrator.py)                        │
│  ask() → LangGraph              dashboard() → DashboardAgent                 │
│  presentation() → PresentationAgent                                          │
└─────────────────────────────┬───────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    LANGGRAPH StateGraph (app/graph.py)                       │
│                                                                              │
│  START → [search] → [planner] → [supervisor] → [data] → [analyst]          │
│                       ↗                                          ↓           │
│              (RAG Cache)                                    [reviewer]       │
│                                                           ↙         ↘       │
│                                                   (retry)          [presenter]→END │
└─────────────────────────────┬───────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼──────────────────────┐
        ▼                     ▼                      ▼
┌──────────────┐    ┌────────────────┐    ┌────────────────────┐
│  ClickHouse  │    │  Ollama LLM    │    │  ChromaDB / RAG    │
│  (DWH + SQL) │    │  (локально)    │    │  (Documents)       │
└──────────────┘    └────────────────┘    └────────────────────┘
```

---

## 4. Граф агентов (LangGraph)

Файл: [`app/graph.py`](app/graph.py)

Граф построен на `StateGraph` из `langgraph`. Каждый **узел** — отдельная функция Python. **Переходы** управляются условными роутерами.

### 4.1 Состояние графа (`GraphState`)

```python
class GraphState(TypedDict):
    question: str                    # Вопрос пользователя (на русском)
    drilldown: Optional[DrilldownContext]  # Контекст drill-down (фильтры)
    user_role: Optional[str]         # Роль RBAC (manager / admin / grodno_manager ...)
    business_context: Optional[str]  # Результат RAG-поиска
    sub_questions: Optional[list[str]] # Подзадачи (TaskDecomposer)
    raw_data: Optional[list]         # Данные из ClickHouse
    sql: Optional[str]               # Сгенерированный SQL
    analysis: Optional[str]         # Текстовый анализ от AnalystAgent
    chart_spec: Optional[dict]       # Спецификация графика
    final_result: Optional[Any]      # Итоговый результат для UI
    error: Optional[str]             # Ошибка, если произошла
    messages: Annotated[list, add_messages]  # История сообщений LangChain
    raw_analysis_dict: Optional[dict]  # Структурированный анализ (для Reviewer)
    eval_feedback: Optional[str]     # Обратная связь от ReviewerAgent
    eval_retry_count: Optional[int]  # Счётчик попыток пересмотра
    route: Optional[str]             # Маршрут из supervisor (data / direct_answer)
```

### 4.2 Топология графа

```
START
  │
  ▼
[search_node] ──── (RAG кэш совпал?) ──── YES ──▶ END
  │
  NO
  ▼
[planner_node]  ←── RagAgent (контекст) + TaskDecomposer (декомпозиция)
  │
  ▼
[supervisor_node] ──── (нужны данные?) ──── NO (direct_answer) ──▶ END
  │
  YES (data)
  ▼
[data_node]  ←── DataAgent (Text-to-SQL + EXPLAIN + Eval + self-correction)
  │
  ▼
[analyst_node]  ←── AnalystAgent (3-4 инсайта + key_conclusion + аномалии)
  │
  ▼
[reviewer_node]  ←── ReviewerAgent (CDO критика)
  │
  ├─── (feedback есть + retry < 1?) ──▶ [analyst_node]  (цикл 1 раз)
  │
  └─── (ок или лимит) ──▶ [presenter_node]
                                │
                    ┌───────────┼──────────────┐
                    ▼           ▼              ▼
             DashboardAgent  ForecastAgent  PresentationAgent
                    │
                    ▼
                   END
```

### 4.3 Роутинг

| Функция | Условие | Куда |
|---------|---------|------|
| `route_after_search` | `drilldown` есть → skip cache | `planner` |
| `route_after_search` | `final_result` заполнен | `END` |
| `route_after_supervisor` | `drilldown` есть | `data` (всегда) |
| `route_after_supervisor` | route = `direct_answer` | `END` |
| `route_after_reviewer` | `eval_feedback` есть | `analyst` (retry) |
| `route_after_reviewer` | feedback = None | `presenter` |

**Ключевая особенность:** при drill-down кэш полностью пропускается и `final_result` принудительно очищается в `supervisor_node`, чтобы избежать возврата устаревшего результата.

---

## 5. Все агенты и их взаимодействия

### 5.1 Полный реестр агентов

| Агент | Файл | Роль в системе |
|-------|------|----------------|
| **RagAgent** | `agents/rag_agent.py` | Поиск бизнес-контекста в ChromaDB |
| **TaskDecompositionAgent** | `agents/task_decomposer.py` | Декомпозиция запроса на подзадачи |
| **DataAgent** | `agents/data_agent.py` | Text-to-SQL → ClickHouse (core) |
| **SqlEvaluatorAgent** | `agents/sql_evaluator.py` | LLM-as-Judge для проверки SQL-логики |
| **AnalystAgent** | `agents/analyst_agent.py` | Инсайты на русском + Z-Score аномалии |
| **ReviewerAgent** | `agents/reviewer_agent.py` | CDO-критик (обратная связь) |
| **ChartAgent** | `agents/chart_agent.py` | Выбор типа и спецификации графика |
| **ForecastAgent** | `agents/forecast_agent.py` | Предиктивный анализ + тренды |
| **DashboardAgent** | `agents/dashboard_agent.py` | Полный дашборд (KPI + N графиков) |
| **PresentationAgent** | `agents/presentation_agent.py` | Генерация PPTX-презентации |

---

### 5.2 DataAgent — Сердце системы

**Файл:** [`app/agents/data_agent.py`](app/agents/data_agent.py)

**Задача:** Преобразует вопрос на русском → безопасный SELECT SQL → реальные данные из ClickHouse.

**Алгоритм (с самокоррекцией, до 3 попыток):**

```
1. Проверить семантический кэш (SemanticCache)
   → Если найден и нет drilldown: вернуть кэшированный SQL

2. Построить промпт:
   - Dynamic Schema (автогенерированная схема БД)
   - Semantic Model (MDL YAML → LLM prompt)
   - Memory Context (история диалога)
   - Rules + Few-Shot из agents.yaml
   - Drilldown constraints (жёсткие WHERE-фильтры)

3. LLM (call_structured) → {step_by_step_reasoning, sql}

4. Whitelist-валидация (запрещены INSERT/UPDATE/DROP/DELETE)

5. EXPLAIN SYNTAX в ClickHouse (синтаксис без выполнения)

6. Выполнение SQL → данные (с авто-LIMIT 500)

7. RLS через SQLGlot:
   - Если role = "grodno_manager" → WHERE region = 'г. Гродно'
   - Если role = "minsk_manager" → WHERE region = 'г. Минск'

8. SqlEvaluatorAgent (LLM-as-Judge) → проверка логики
   → Если ошибка → retry с фидбеком

9. Сохранить в SemanticCache (если нет drilldown)
```

**Ключевые защиты:**
- Auto-LIMIT 500 если отсутствует
- Whitelist: только SELECT
- EXPLAIN SYNTAX перед выполнением
- sqlglot RLS (AST-инъекция WHERE)
- LLM-as-Judge проверка логики (SqlEvaluator)

---

### 5.3 AnalystAgent

**Файл:** [`app/agents/analyst_agent.py`](app/agents/analyst_agent.py)

**Задача:** Данные → 3–4 русских инсайта + ключевой вывод + аномалии/тренды.

**Особенности:**
- **Z-Score аномалии:** математическое обнаружение выбросов (порог 2.5σ) по всем числовым колонкам до вызова LLM — затем аномалии вставляются в промпт
- **Chart Context:** если передан `chart_spec`, аналитик обязан упомянуть визуализацию в инсайтах
- **Drill-down enrichment:** если активен drill-down, аналитик фокусируется на конкретном сегменте
- **Follow-up questions:** всегда возвращает 2–3 следующих вопроса
- **Graceful degradation:** при пустых данных — информативная ошибка, не падение
- **ReviewerAgent feedback loop:** если Reviewer отклонил, AnalystAgent получает критику и переписывает анализ

---

### 5.4 ReviewerAgent (CDO)

**Файл:** [`app/agents/reviewer_agent.py`](app/agents/reviewer_agent.py)

**Задача:** Независимая проверка качества аналитики перед финальным ответом.

**Роль:** Условный "Chief Data Officer" — строгий критик, который проверяет:
- Опираются ли выводы на реальные числа из данных?
- Нет ли галлюцинаций в аналитике?
- Достаточно ли глубоки инсайты?

**Ограничение:** максимум 1 итерация пересмотра (retry_count < 1), чтобы не зациклить граф.

---

### 5.5 DashboardAgent

**Файл:** [`app/agents/dashboard_agent.py`](app/agents/dashboard_agent.py)

**Задача:** По вопросу и данным → полный комплексный дашборд.

**Алгоритм:**
```
1. Получить данные (если нет → вызвать DataAgent)
2. Получить инсайты от AnalystAgent (опционально)
3. Поиск похожего дашборда в RAG (как шаблон/вдохновение)
4. LLM (call_structured) → _DashboardComposition:
   {title, summary, kpi_cards, chart_ideas, layout, insights, recommendations}
5. Параллельная генерация ChartSpec через ThreadPoolExecutor:
   - Для каждой chart_idea → ChartAgent.run(idea, data=...)
   - Параллельно (max_workers = max_charts)
6. Детерминированные KPI из данных (без LLM):
   - Сумма debt, accrued
   - Кол-во регионов, типов налогов
7. Сборка DashboardResult
```

**Graceful degradation:** при любой ошибке возвращает минимальный рабочий дашборд.

---

### 5.6 PresentationAgent

**Файл:** [`app/agents/presentation_agent.py`](app/agents/presentation_agent.py)

**Задача:** Список вопросов → PPTX-файл со слайдами + PNG-превью.

**Pipeline генерации:**
```
Список вопросов
    │
    ▼
[Parallel] Для каждого вопроса → Orchestrator.ask()
    │        (DataAgent + AnalystAgent + ChartAgent)
    ▼
DeckNarrative (LLM):
    - overview (детальное описание)
    - themes (5–7 ключевых тем)
    - key_takeaways (7–10 выводов с цифрами)
    - recommendations (4–6 с КПЭ)
    │
    ▼
SlidePipeline → python-pptx:
    - Слайд 1: Титул
    - Слайды 2–N: По данным каждого вопроса
    - Слайд N+1: Key Takeaways
    - Слайд N+2: Recommendations (если include_recommendations)
    │
    ▼
PNG-превью каждого слайда (для UI)
    │
    ▼
PresentationResult (pptx_path, slides[], slide_png_paths[])
```

**Hot-update:** метод `update_presentation()` позволяет пересобрать PPTX без LLM — только на основе изменённых `SlideData`.

---

### 5.7 ChartAgent

**Файл:** [`app/agents/chart_agent.py`](app/agents/chart_agent.py)

**Задача:** Вопрос + данные → ChartSpec (тип графика + оси + заголовок + данные).

**Поддерживаемые типы:** `bar`, `line`, `pie`, `donut`, `horizontal_bar`, `area`, `scatter`, `radar`, `kpi`, `composed`, `table`, `treemap`

---

### 5.8 ForecastAgent

**Файл:** [`app/agents/forecast_agent.py`](app/agents/forecast_agent.py)

**Задача:** Исторические данные → предиктивный анализ + тренды + прогнозный ChartSpec.

Активируется в `presenter_node` при наличии слова "прогноз" в запросе.

---

### 5.9 RagAgent

**Файл:** [`app/agents/rag_agent.py`](app/agents/rag_agent.py)

**Задача:** Поиск релевантного бизнес-контекста в ChromaDB для обогащения промпта.

Используется в `planner_node`. Результат (`business_context`) передаётся в `DataAgent` и `supervisor_node`.

---

### 5.10 TaskDecompositionAgent

**Файл:** [`app/agents/task_decomposer.py`](app/agents/task_decomposer.py)

**Задача:** Разбивает сложный запрос на список подзадач (sub_questions), каждая из которых выполняется в `data_node` последовательно.

---

## 6. Backend — модули и API

### 6.1 Структура модулей

```
app/
├── main.py                    # FastAPI — все эндпоинты
├── orchestrator.py            # Единая точка входа (ask/dashboard/presentation)
├── graph.py                   # LangGraph StateGraph
│
├── agents/
│   ├── models.py              # ВСЕ Pydantic-контракты между агентами
│   ├── data_agent.py          # Text-to-SQL (core)
│   ├── analyst_agent.py       # Инсайты на русском
│   ├── chart_agent.py         # Визуализация
│   ├── dashboard_agent.py     # Комплексный дашборд
│   ├── presentation_agent.py  # PPTX генерация
│   ├── forecast_agent.py      # Предиктивный анализ
│   ├── reviewer_agent.py      # CDO-критик
│   ├── rag_agent.py           # RAG-контекст
│   ├── sql_evaluator.py       # LLM-as-Judge для SQL
│   ├── task_decomposer.py     # Декомпозиция запросов
│   ├── base_agent.py          # Базовый класс
│   ├── factory.py             # AgentExecutor (singleton)
│   ├── config_loader.py       # Загрузка конфигов из YAML
│   └── db_schema_extractor.py # Динамическое извлечение схемы БД
│
├── config/
│   └── agents.yaml            # Промпты, роли, few-shot примеры для всех агентов
│
├── services/
│   ├── watcher_service.py     # Фоновое сканирование аномалий
│   ├── email_scheduler.py     # Расписание email доставки
│   ├── rag_service.py         # RAG ingestion + retrieval
│   ├── anomaly_detector.py    # Детектирование аномалий
│   ├── excel_renderer.py      # Генерация Excel файлов
│   └── subscription_service.py # Управление подписками
│
├── utils/
│   ├── clickhouse_client.py   # ClickHouse клиент
│   ├── memory.py              # Conversation Memory (история диалогов)
│   ├── semantic_cache.py      # Кэш SQL-запросов (in-memory)
│   ├── schema_crawler.py      # Автогенерация semantic_model.yaml
│   ├── excel_exporter.py      # Красивый Excel export
│   ├── etl_worker.py          # ETL из Dropzone
│   ├── pdf_presentation.py    # PDF → PPTX
│   └── clickhouse_rbac.py     # Управление ролями ClickHouse
│
├── semantic/
│   └── catalog.py             # Загрузка MDL YAML → LLM Prompt
│
├── middleware/
│   └── logging.py             # HTTP-логирование запросов
│
├── pipeline_progress.py       # Стриминг прогресса через WebSocket
├── agent_context.py           # Context vars (роль, debate queue, events)
├── presentation_renderer.py   # python-pptx рендерер слайдов
└── slide_pipeline.py          # Пайплайн сборки слайдов
```

### 6.2 Конфигурация агентов (Hot Reload)

Файл: [`app/config/agents.yaml`](app/config/agents.yaml)

Вся текстовая логика агентов — в одном YAML-файле. Поддерживает `role`, `goal`, `rules`, `few_shot_examples`. Изменения применяются без перезапуска сервера.

```yaml
data_agent:
  role: "Senior SQL Engineer специализирующийся на ClickHouse"
  goal: "Генерировать безопасный SELECT по вопросу пользователя"
  rules: |
    1. Используй только таблицы из Schema
    2. Всегда SELECT, никогда INSERT/UPDATE/DELETE
    ...
  few_shot: |
    Q: "Задолженность по регионам?"
    A: {"sql": "SELECT region, sum(debt) FROM enterprise_taxes GROUP BY region"}
```

### 6.3 REST / WebSocket API

| Эндпоинт | Метод | Назначение |
|----------|-------|-----------|
| `/ws/chat` | WebSocket | Основной чат с реальным стримингом |
| `/ask` | POST | REST-запрос к LangGraph |
| `/ask_stream` | POST | SSE стриминг ответа |
| `/generate_dashboard` | POST | Генерация дашборда |
| `/generate_presentation` | POST | Генерация PPTX |
| `/api/v1/presentation/update` | POST | Обновление слайдов без LLM |
| `/api/v1/kpi` | GET | KPI метрики из ClickHouse |
| `/api/export/excel` | POST | Экспорт данных в Excel |
| `/api/v1/export-excel` | POST | Красивый Excel (кастомный) |
| `/api/v1/upload_data` | POST | Загрузка CSV в Dropzone |
| `/api/v1/workspace/upload` | POST | Загрузка CSV/XLSX → ClickHouse |
| `/api/v1/pdf/analyze` | POST | PDF → презентация или дашборд |
| `/api/v1/download` | GET | Скачивание файлов (pptx/xlsx/png) |
| `/api/v1/send-email` | POST | Отправка отчёта на email |
| `/api/v1/trigger_watcher` | POST | Ручной запуск WatcherService |
| `/api/v1/sessions` | GET | История сессий |
| `/api/v1/sessions/{id}` | GET | Сообщения конкретной сессии |
| `/api/v1/pipeline/status` | GET | Прогресс pipeline |
| `/api/v1/sql-logs` | GET | SQL логи из ClickHouse system |
| `/api/user/dashboard` | GET/POST | Сохранение закреплённых графиков |
| `/auth/login` | POST | JWT аутентификация |
| `/health` | GET | Health-check |
| `/metrics` | GET | Prometheus метрики |

### 6.4 Startup (Lifespan Events)

При запуске FastAPI автоматически:
1. `start_scheduler()` — запускает APScheduler для Email доставки
2. `generate_semantic_model()` — автогенерация `semantic_model.yaml` из схемы ClickHouse
3. `init_schema_knowledge()` — инициализация Smart Schema RAG
4. `initialize_dashboard_rag()` — загрузка дашбордов в RAG-индекс

---

## 7. Frontend — компоненты и UI-потоки

### 7.1 Структура компонентов

```
frontend_web/src/
├── App.tsx                    # Корневой компонент, роутинг view'ов
├── store/
│   └── useChatStore.ts        # Zustand store (глобальное состояние)
├── hooks/
│   └── useChatSocket.ts       # WebSocket хук
├── components/
│   ├── layout/
│   │   └── Header.tsx         # Верхняя панель навигации
│   ├── chat/
│   │   ├── ChatContainer.tsx  # Список сообщений
│   │   ├── ChatInput.tsx      # Поле ввода + кнопка отправки
│   │   ├── MessageBubble.tsx  # Сообщение (текст + графики + SQL)
│   │   ├── DynamicChart.tsx   # Recharts рендер (13+ типов)
│   │   ├── AgentGraph.tsx     # Анимированный граф агентов
│   │   └── widgets/           # KPI карточки, инсайты
│   ├── dashboard/
│   │   ├── AIDashboardView.tsx         # Полный просмотр AI-дашборда
│   │   ├── DashboardGeneratorModal.tsx  # Форма генерации дашборда
│   │   ├── DashboardGrid.tsx            # Закреплённые графики (drag-n-drop)
│   │   ├── DashboardToolbar.tsx         # Тулбар дашборда
│   │   ├── ExecutiveSummary.tsx         # Executive Summary компонент
│   │   └── AutoInsights.tsx             # Автоматические инсайты
│   ├── presentation/
│   │   ├── PresentationGeneratorModal.tsx  # Форма генерации PPTX
│   │   ├── PresentationView.tsx             # Просмотр презентации
│   │   └── SlideRenderer.tsx               # Рендер отдельного слайда
│   ├── workspace/
│   │   └── WorkspaceDBView.tsx  # Управление Workspace БД
│   ├── pdf/
│   │   └── PDFGenerationHub.tsx # Загрузка PDF + генерация
│   ├── admin/
│   │   └── AdminModal.tsx       # Панель администратора
│   ├── profile/
│   │   └── UserProfile.tsx      # Профиль пользователя
│   ├── subscriptions/
│   │   └── SubscriptionsView.tsx # Управление подписками
│   └── ui/                       # Shadcn/ui компоненты
```

### 7.2 Виды (Views) главного экрана

| View | Активация | Содержимое |
|------|-----------|-----------|
| `chat` | по умолчанию | Основной чат + ChatInput |
| `ai_dashboard` | клик на дашборд в sidebar | AIDashboardView (KPI + Charts) |
| `presentation` | клик на презентацию в sidebar | PresentationView (слайды + скачать) |
| `workspace_db` | кнопка "Workspace БД" | WorkspaceDBView |
| `profile` | кнопка профиля в Header | UserProfile |
| `subscriptions` | кнопка подписок | SubscriptionsView |

### 7.3 Боковая панель (Sidebar Tabs)

| Вкладка | Содержимое |
|---------|-----------|
| `Dashboard` | DashboardGrid (закреплённые графики) |
| `Генерация` | Кнопки AI Дашборд + Презентация + PDF; списки сохранённых |
| `Workspace БД` | Кнопка открыть менеджер БД |
| `PDF` | PDFGenerationHub |
| `История` | Список сессий, сгруппированных: Сегодня / Вчера / Неделю назад / Ранее |

### 7.4 WebSocket Flow

```
1. Frontend (useChatSocket.ts) → отправляет:
   {question, session_id, drilldown?: {key, value, action}}

2. Backend (main.py) → разбирает drilldown, создаёт DrilldownContext

3. Запускает orchestrator.ask() в executor (не блокируя event loop)

4. Параллельно шлёт в WebSocket:
   - {type: "status"} — статусы ("Анализирую данные...")
   - {type: "debate"} — "дебаты" агентов (живая трансляция)
   - {type: "node_event"} — текущий активный узел
   - {type: "pipeline_update"} — прогресс стейджей

5. По завершении → {type: "result", content, sql?, pptx_path?, excel_path?}

6. Frontend → парсит JSON-блоки из content → рендерит DynamicChart
```

### 7.5 Drill-down механизм

```
Пользователь кликает на бар в графике (напр. "г. Минск")
    │
    ▼
handleChartClick(promptText, {key: "region", value: "г. Минск", action: "drilldown"})
    │
    ▼
sendMessage(prompt, sessionId, drilldown)  → WebSocket
    │
    ▼
Backend: DrilldownContext(filters={"region": "г. Минск"}, dimension="region", segment_label="г. Минск")
    │
    ▼
graph.invoke() с drilldown → supervisor_node → data_node (фильтры применяются автоматически)
    │
    ▼
Новый дашборд/анализ только по г. Минск
```

---

## 8. Безопасность (RBAC / RLS)

### 8.1 Аутентификация

- **JWT токены** через `/auth/login`
- Токен кодирует: `{username, role}`
- Поддерживаемые роли: `manager`, `admin`, `grodno_manager`, `minsk_manager`
- Хранится в `localStorage`; срок действия — 24 часа

```
Логин: "grodno_admin" → role = "grodno_manager"
Логин: "minsk_user"  → role = "minsk_manager"
Логин: "admin_..."   → role = "admin"
```

### 8.2 Row-Level Security (RLS) через SQLGlot

В `DataAgent._execute_sql()` — ПЕРЕД отправкой запроса в ClickHouse:

```python
# AST-парсинг SQL через SQLGlot
parsed = sqlglot.parse_one(ch_sql, read="clickhouse")
# Принудительная инъекция условия WHERE
where_clause = exp.condition(f"region = '{region_filter}'")
parsed = parsed.where(where_clause)
ch_sql = parsed.sql(dialect="clickhouse")
```

**Результат:** ИИ физически не может вернуть данные другого региона — SQL модифицируется на уровне AST.

### 8.3 SQL Whitelist

Запрещённые операции в промпте + явная проверка:
```python
for bad in ("insert", "update", "delete", "drop", "create", "alter", ";--"):
    if bad in sql.lower():
        raise ValueError(f"Запрещённая операция в SQL: {bad}")
```

---

## 9. Семантический слой (MDL)

### 9.1 Структура

Файл: [`data/semantic_model.yaml`](data/semantic_model.yaml)

Бизнес-описание всех таблиц и метрик в YAML-формате (аналог WrenAI MDL / Cube.js). Содержит:
- Описания таблиц на русском
- Описания каждой колонки (что значит, примеры значений)
- Бизнес-метрики (debt_ratio, collection_rate и т.д.)
- Связи между таблицами

### 9.2 Загрузка при старте

```python
# utils/schema_crawler.py
generate_semantic_model()  # Автоматическая генерация из ClickHouse schema

# semantic/catalog.py
catalog = SemanticCatalog.load(schema_path)
# Преобразует YAML → строгий LLM-промпт
llm_prompt = catalog.to_llm_prompt()
```

### 9.3 Использование в DataAgent

```
=== SEMANTIC MODEL (MDL) ===
ВНИМАНИЕ: Это бизнес-слой. Строго используй описанные здесь метрики,
таблицы и расчеты. Не придумывай свои агрегации, если они уже есть в MDL.
{semantic_context}
```

---

## 10. RAG-подсистема

### 10.1 Три RAG-индекса

| Индекс | Назначение | Когда используется |
|--------|------------|-------------------|
| **Schema RAG** | Описания колонок, типы данных | `planner_node` / `DataAgent` |
| **Dashboard RAG** | История прошлых дашбордов | `DashboardAgent` (шаблоны) |
| **Document RAG** | PDF документы, аналитика | Полнотекстовый поиск |

### 10.2 Dashboard RAG (Semantic Cache + History)

```python
# DashboardAgent: поиск похожего дашборда как шаблона
docs = search_dashboards(question, k=1)
if docs:
    rag_context = "[РЕФЕРЕНСНЫЙ ДАШБОРД (RAG)] Найден сохраненный дашборд..."
```

### 10.3 Semantic Cache (SQL-уровень)

```python
# utils/semantic_cache.py — in-memory словарь
# При запросе → поиск по question
cached_sql = semantic_cache.get_sql(question)
# После успешного запроса → сохранение
semantic_cache.set_sql(question, sql)
```

**Ограничение:** drilldown-запросы НИКОГДА не кэшируются (содержат фильтры конкретного региона).

---

## 11. Проактивная аналитика (WatcherService)

**Файл:** [`app/services/watcher_service.py`](app/services/watcher_service.py)

### 11.1 Что делает

Система сама (без запроса пользователя) периодически:
1. Сканирует данные ClickHouse на аномалии
2. Если найдено → формирует тревожный отчёт
3. Отправляет email руководителю

### 11.2 Запуск

- **Автоматически** по расписанию через APScheduler (`email_scheduler.py`)
- **Вручную** через API: `POST /api/v1/trigger_watcher`
- **Из UI** через кнопку "Запустить сканирование" в сайдбаре

### 11.3 Email доставка

**Файл:** [`app/services/email_service.py`](app/services/email_service.py)

```
Расписание: APScheduler (cron-like)
Формат: JSON в out/mock_emails/ (dev), SMTP (prod)
Endpoint: POST /api/v1/send-email
```

---

## 12. Data Flow — от вопроса к ответу

### 12.1 Основной чат-запрос

```
Пользователь → "Покажи задолженность по регионам"
    │
    ▼
WebSocket → useChatSocket.sendMessage()
    │
    ▼
main.py /ws/chat → DrilldownContext = None
    │
    ▼
orchestrator.ask() → graph.invoke({question, user_role})
    │
    ├── search_node:  SearchPastReportsTool → нет совпадений → продолжаем
    │
    ├── planner_node: RagAgent → context ("Задолженность = debt поле...")
    │                 TaskDecomposer → [вопрос не разбивается]
    │
    ├── supervisor_node: LLM → route = "data" (нужен SQL)
    │
    ├── data_node:
    │   └── DataAgent.run("Покажи задолженность по регионам")
    │       ├── SemanticCache.get → miss
    │       ├── LLM → {sql: "SELECT region, sum(debt) FROM enterprise_taxes GROUP BY region"}
    │       ├── EXPLAIN SYNTAX → OK
    │       ├── ClickHouse.execute() → [{region: "Минск", debt: 1200}, ...]
    │       ├── SqlEvaluator → OK
    │       └── SemanticCache.set(question, sql)
    │
    ├── analyst_node:
    │   └── AnalystAgent.run(question, data)
    │       ├── Z-Score проверка → нет аномалий
    │       ├── LLM → {insights: [...], key_conclusion: "...", follow_up_questions: [...]}
    │       └── enrich_analysis_explanation()
    │
    ├── reviewer_node:
    │   └── ReviewerAgent.evaluate() → {is_good: True} → продолжаем
    │
    └── presenter_node:
        └── DashboardAgent.run(question, raw_data)
            ├── AnalystAgent → инсайты
            ├── LLM → _DashboardComposition {title, kpi_cards, chart_ideas, layout}
            ├── ThreadPoolExecutor: 4 потока → ChartAgent.run(idea, data) x4
            └── DashboardResult {title, kpi_cards, charts, insights, recommendations}

AskResult.reasoning = JSON с charts → WebSocket → Frontend → parseCharts → DynamicChart
```

### 12.2 Генерация дашборда (прямой путь)

```
POST /generate_dashboard {question, max_charts=4, include_kpi=true}
    │
    ▼
orchestrator.dashboard() → AgentExecutor.run("dashboard_agent", req)
    │
    ▼
DashboardResult → JSON → Frontend → AIDashboardView
```

### 12.3 Генерация презентации

```
POST /generate_presentation {mode, questions[], num_slides=10}
    │
    ├── (Свободная тема) LLM → список вопросов
    │
    ▼
orchestrator.presentation(questions) → PresentationAgent.run()
    │
    ├── [Parallel] Для каждого вопроса → orchestrator.ask()
    │
    ├── LLM → DeckNarrative {overview, themes, key_takeaways, recommendations}
    │
    ├── SlidePipeline → python-pptx → presentation.pptx
    │
    ├── PNG-превью каждого слайда
    │
    └── PresentationResult {pptx_path, slides[], slide_png_paths[]}
                │
                ▼
        Frontend → PresentationView → SlideRenderer
```

---

## 13. Pydantic-контракты между агентами

Файл: [`app/agents/models.py`](app/agents/models.py) — **единственный источник истины** для всех типов данных.

```
AgentResult (base)
    ├── SqlResult          ← DataAgent output
    ├── AnalysisResult     ← AnalystAgent output
    ├── ChartAgentResult   ← ChartAgent output
    ├── RagResult          ← RagAgent output
    ├── DashboardResult    ← DashboardAgent output
    ├── PresentationResult ← PresentationAgent output
    └── AskResult          ← Orchestrator final output

Вспомогательные:
    ├── DrilldownContext   ← UI → Backend (фильтры drill-down)
    ├── DashboardRequest   ← API → DashboardAgent input
    ├── PresentationRequest ← API → PresentationAgent input
    ├── KpiCard            ← KPI-карточка
    ├── DashboardLayout    ← Рекомендация расположения
    ├── SupervisorDecision ← Маршрутизатор (data/direct_answer)
    ├── SlideData          ← Данные одного слайда
    ├── SlideUpdate        ← Частичное обновление слайда
    ├── DeckNarrative      ← Нарратив презентации
    └── PlannerTrace       ← Трассировка выполнения (Plan + AgentCall[])
```

**Принцип:** агенты общаются ТОЛЬКО через Pydantic-модели, никаких голых `dict`.

---

## 14. Что реализовано на фронте

### ✅ Полностью реализовано

| Функция | Где | Статус |
|---------|-----|--------|
| Авторизация (JWT) | `LoginScreen` → `App.tsx` | ✅ |
| Чат с LLM агентами (WebSocket) | `ChatContainer` + `useChatSocket` | ✅ |
| Парсинг и рендер графиков (13+ типов) | `DynamicChart.tsx` | ✅ |
| Live прогресс pipeline | `MessageBubble` → pipeline stages | ✅ |
| Дебаты агентов в реальном времени | `debate` events в WS | ✅ |
| Анимированный граф агентов | `AgentGraph.tsx` | ✅ |
| Drill-down (клик по графику → детализация) | `handleChartClick` | ✅ |
| KPI-карточки | `widgets/` + `AIDashboardView` | ✅ |
| История сессий (группировка по времени) | `SessionGroup` | ✅ |
| Загрузка / восстановление сессии | `GET /sessions/{id}` | ✅ |
| Закрепление графиков на дашборде | `pinChart()` + `DashboardGrid` | ✅ |
| Drag-n-drop дашборд | `DashboardGrid` (react-grid-layout) | ✅ |
| AI Дашборд генерация (модальное окно) | `DashboardGeneratorModal` | ✅ |
| Просмотр AI Дашборда | `AIDashboardView` | ✅ |
| Генерация презентации (модальное окно) | `PresentationGeneratorModal` | ✅ |
| Просмотр презентации (слайды) | `PresentationView` + `SlideRenderer` | ✅ |
| Скачивание PPTX | ссылка на `/api/v1/download` | ✅ |
| Скачивание Excel | кнопка + `POST /api/export/excel` | ✅ |
| Workspace БД (загрузка CSV/XLSX) | `WorkspaceDBView` | ✅ |
| PDF Generation Hub (pdf → pptx/dashboard) | `PDFGenerationHub` | ✅ |
| Профиль пользователя | `UserProfile` | ✅ |
| Подписки | `SubscriptionsView` | ✅ |
| Панель администратора | `AdminModal` | ✅ |
| SQL-режим аналитика (SQL в сообщении) | `MessageBubble` → SQL раскрывашка | ✅ |
| Алерты / уведомления (WatcherService) | `alerts` state в `App.tsx` | ✅ |
| Тёмная тема (glassmorphism) | `tailwind.config.js` + `index.css` | ✅ |
| Анимированный sidebar | Framer Motion | ✅ |
| Адаптивный дизайн | TailwindCSS breakpoints | ✅ |
| Executive Summary | `ExecutiveSummary.tsx` | ✅ |
| Auto Insights | `AutoInsights.tsx` | ✅ |

---

## 15. Анализ: что готово к демонстрации

### 15.1 Чек-лист по требованиям из встречи

| Требование (из записи встречи) | Реализовано | Где |
|-------------------------------|-------------|-----|
| Чат-интерфейс с AI-аналитиком | ✅ | ChatContainer + WebSocket |
| Графики (динамика, регионы, налоги) | ✅ | DynamicChart (13 типов) |
| Drill-down по клику на бар | ✅ | handleChartClick + DrilldownContext |
| Drill-down → другой тип (таблица/детали) | ✅ | DashboardAgent выбирает тип |
| Скачать данные в Excel | ✅ | /api/export/excel |
| Генерация презентации | ✅ | PresentationAgent + PresentationView |
| Отправка на почту (кнопка) | ✅ | /api/v1/send-email |
| История запросов (сессии) | ✅ | /api/v1/sessions |
| ClickHouse как основная база | ✅ | DataAgent → ClickHouse |
| RLS / ролевая безопасность | ✅ | JWT + SQLGlot AST-инъекция |
| Семантический слой (описания полей) | ✅ | data/semantic_model.yaml + SemanticCatalog |
| RAG (документы + схема) | ✅ | ChromaDB + rag_service.py |
| Дашборд (КПИ + графики) | ✅ | DashboardAgent + AIDashboardView |
| Проваливание в данные (drill-down из дашборда) | ✅ | DrilldownContext сквозная |
| PDF → презентация | ✅ | /api/v1/pdf/analyze |
| Загрузка своих данных (CSV/XLSX) | ✅ | WorkspaceDBView + /workspace/upload |
| Прозрачность работы агентов | ✅ | AgentGraph + debate events |
| Prometheus метрики | ✅ | /metrics |

### 15.2 Статус реализации по слоям

```
✅ БЭКЕНД:       100% — все агенты, граф, API, сервисы
✅ ФРОНТЕНД:     100% — все вьюхи, компоненты, взаимодействия
✅ БЕЗОПАСНОСТЬ: 100% — JWT, RBAC, RLS через SQLGlot
✅ ДАННЫЕ:        95% — ClickHouse, семантика, RAG
✅ НАБЛЮДАЕМОСТЬ: 90% — Prometheus, логи, pipeline stg
✅ ДОКУМЕНТАЦИЯ:  Этот файл — полная актуализация
```

---

## 16. Пути развития и глубокой модернизации (Roadmap)

На основе глубокого архитектурного анализа текущего состояния проекта (как Backend/Frontend, так и инфраструктурного слоя), сформирован вектор дальнейшего развития платформы. План разбит на ключевые технологические домены.

### 16.1 Инфраструктура и MLOps (Наблюдаемость ИИ)

*   **Интеграция LLM-Трейсинга (Langfuse / LangSmith):** Текущее логирование (через `system_logger`) хорошо подходит для классического Backend. Внедрение специализированного MLOps инструмента позволит визуализировать каждый шаг LangGraph, отслеживать точное потребление токенов, latency каждого узла и строить аналитику "Cost per Query".
*   **Стриминг токенов (Token-by-Token Stream):** Сейчас по WebSocket стримится прогресс выполнения агентов (статусы). Следующий шаг — транслировать ответы AnalystAgent и ReviewerAgent посимвольно прямо по мере генерации ответа LLM, что радикально улучшит UX (снижение Time-To-First-Token).
*   **DPO Feedback Loop (Петля обратной связи):** Внедрение кнопок 👍/👎 под каждым ответом чата. Разметка от пользователя будет автоматически сохраняться в ClickHouse в формате JSONL, формируя датасет для периодического дообучения (Fine-Tuning / DPO) локальной модели `Qwen2.5-Coder` на специфику конкретного предприятия.

### 16.2 Ядро Данных и ClickHouse (DWH)

*   **Миграция RAG на Qdrant:** В данный момент векторный поиск работает на легковесной `ChromaDB`. Инфраструктура `docker-compose` уже содержит сервис `qdrant`. Переезд на Qdrant позволит масштабировать RAG-поиск на сотни миллионов документов, использовать HNSW-индексы и Payload-фильтрацию.
*   **Self-Healing SQL & Materialized Views:** Развитие `DataAgent` до уровня самоуправления базой. Агент сможет анализировать медленные запросы (через `system.query_log` ClickHouse) и автоматически предлагать/создавать `Materialized View` или новые индексы для ускорения работы стандартных дашбордов.
*   **Интеграция dbt (Data Build Tool):** Вынос логики трансформации сырых данных в отдельный слой dbt. Это обеспечит строгое версионирование моделей данных и позволит агентам генерировать SQL поверх уже чистых, бизнес-ориентированных dbt-витрин.

### 16.3 Безопасность и Интеграции (Security & Access)

*   **Полноценная миграция на Keycloak (SSO / OIDC):** В проекте заложен контейнер Keycloak. Требуется полный отказ от текущей кастомной реализации JWT (`app/auth.py`) в пользу OAuth2 flow через Keycloak. Это мгновенно даст поддержку Active Directory, LDAP, 2FA и централизованного управления ролями предприятия.
*   **Column-Level Security (CLS) и Маскирование:** Текущий RLS на базе `SQLGlot` отлично фильтрует строки (WHERE region=...). План — добавить фильтрацию на уровне колонок, чтобы `Manager` видел суммы, но имена клиентов (ФИО) маскировались (например, `Иванов И.И.` -> `И*** И.И.`).
*   **Телеграм-интеграция (Мессенджеры):** Разработка Telegram-бота, который через Webhook будет общаться с `FastAPI`, позволяя руководителям запрашивать KPI и графики текстом или голосом прямо со смартфона.

### 16.4 Пользовательский Опыт и Frontend (React/Vite)

*   **Коллаборативный режим (Multiplayer):** Внедрение CRDT (Conflict-free Replicated Data Type) технологий (например, `Yjs`) на дашборды. Это позволит нескольким менеджерам одновременно редактировать структуру дашборда, перетаскивать графики и видеть курсоры друг друга (аналог Google Docs/Figma).
*   **Progressive Web App (PWA):** Настройка Service Workers для кэширования статики и последних JSON-ответов KPI. Дашборд руководителя должен мгновенно открываться и показывать закэшированные данные даже при кратковременном обрыве корпоративной сети.
*   **Voice-to-SQL (Распознавание речи):** Добавление кнопки микрофона в UI. Использование Web Speech API или локального Whisper для перевода голоса в текст с последующей моментальной отправкой в Orchestrator.

### 16.5 Расширенные Аналитические возможности

*   **Автоматический AI ETL Wizard (Data Prep):** Создание нового узла `ETLAgent`. При загрузке пользователем любого грязного Excel/CSV файла (через `WorkspaceDBView`), агент сам поймет семантику колонок, очистит мусор, конвертирует даты в нужный формат ISO и зальет данные в ClickHouse, автоматически обновив `semantic_model.yaml`.
*   **Data Lineage (Происхождение данных):** Внедрение визуального графа происхождения для каждой цифры. По клику на KPI "Задолженность", интерфейс покажет дерево: из какой таблицы ClickHouse взята цифра, какие WHERE фильтры применены, и какая математическая формула использована.
*   **Глубокая Предиктивная Аналитика (Time-Series):** Расширение `ForecastAgent` за счет интеграции библиотек `Prophet` или `ARIMA`. Агент сможет строить доверительные интервалы, находить сезонность и отвечать на вопросы "What-If" (Что если мы увеличим налог на 2%?).

---

## 17. Как запустить

### 17.1 Требования

```bash
# Python
python 3.11+
pip install -r requirements.txt

# Node.js
node 18+
cd frontend_web && npm install

# Ollama (локально)
ollama serve
ollama pull qwen2.5-coder:7b-instruct

# ClickHouse (Docker)
docker compose up -d clickhouse
```

### 17.2 Запуск

```bash
# Бэкенд
cd prototip
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Фронтенд
cd frontend_web
npm run dev   # Открыть: http://localhost:5173
```

### 17.3 Переменные окружения (`.env`)

```env
OLLAMA_BASE_URL=http://localhost:11434
CLICKHOUSE_HOST=localhost
CLICKHOUSE_PORT=9000
CLICKHOUSE_DATABASE=default
JWT_SECRET_KEY=your-secret-key
EMAIL_HOST=smtp.example.com
EMAIL_PORT=587
```

### 17.4 Тестовые логины

| Логин | Пароль | Роль | Доступ |
|-------|--------|------|--------|
| `admin` | любой | `admin` | Весь датасет |
| `grodno_user` | любой | `grodno_manager` | Только г. Гродно |
| `minsk_user` | любой | `minsk_manager` | Только г. Минск |
| `analyst` | любой | `manager` | Весь датасет |

---

## Приложение: Диаграмма взаимодействия агентов

```
Пользователь
     │
     ▼
WebSocket /ws/chat
     │
     ▼
Orchestrator.ask()
     │
     ▼ (LangGraph StateGraph)
     │
     ├─[search_node]──────────────────────────────────┐
     │   SearchPastReportsTool (RAG history cache)     │
     │                                                 │
     ├─[planner_node]                                  │
     │   ├─ RagAgent (ChromaDB schema+docs)            │
     │   └─ TaskDecompositionAgent                     │
     │                                                 │
     ├─[supervisor_node]                               │
     │   └─ LLM: SupervisorDecision {route}            │
     │                                                 │
     ├─[data_node]                                     │
     │   └─ DataAgent                                  │
     │       ├─ SemanticCatalog.to_llm_prompt()        │
     │       ├─ LLM → SQL                              │
     │       ├─ ClickHouse EXPLAIN SYNTAX              │
     │       ├─ SQLGlot RLS injection                  │
     │       ├─ ClickHouse execute()                   │
     │       └─ SqlEvaluatorAgent (LLM-as-Judge)       │
     │                                                 │
     ├─[analyst_node]                                  │
     │   └─ AnalystAgent                               │
     │       ├─ Z-Score anomaly detection              │
     │       └─ LLM → AnalysisResult                   │
     │                                                 │
     ├─[reviewer_node]                                 │
     │   └─ ReviewerAgent (CDO critique)               │
     │       └─ (если плохо → retry к analyst)         │
     │                                                 │
     └─[presenter_node]                                │
         ├─ DashboardAgent ──────────────────────────┐ │
         │   ├─ AnalystAgent (insights)              │ │
         │   ├─ LLM → DashboardComposition           │ │
         │   └─ [Parallel] ChartAgent x4             │ │
         │                                           │ │
         ├─ ForecastAgent (если "прогноз")           │ │
         │                                           │ │
         └─ PresentationAgent (если "презентац")     │ │
             ├─ [Parallel] Orchestrator.ask() x N   │ │
             ├─ LLM → DeckNarrative                 │ │
             └─ SlidePipeline → python-pptx          │ │
                                                    │ │
AskResult ←─────────────────────────────────────────┘ │
     │                                               │
     ▼                                               │
WebSocket → Frontend ←──────────────────────────────┘
     │
     ├─ DynamicChart (Recharts)
     ├─ KpiCards
     ├─ AgentGraph (анимация)
     └─ Debate stream (живые сообщения агентов)
```

