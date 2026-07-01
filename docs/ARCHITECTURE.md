# Архитектура Prototip BI

> **Версия документа:** актуальна на 23 июня 2026  
> **Статус:** полностью синхронизирован с текущим состоянием кодовой базы

---

## Содержание

1. [Что это и зачем](#1-что-это-и-зачем)
2. [Технологический стек](#2-технологический-стек)
3. [Инфраструктура (Docker Compose)](#3-инфраструктура-docker-compose)
4. [Высокоуровневая архитектура](#4-высокоуровневая-архитектура)
5. [Граф агентов (LangGraph)](#5-граф-агентов-langgraph)
6. [Все агенты и их взаимодействия](#6-все-агенты-и-их-взаимодействия)
7. [Backend — модули и API](#7-backend--модули-и-api)
8. [ETL-подсистема (Airflow)](#8-etl-подсистема-airflow)
9. [Frontend — компоненты и UI-потоки](#9-frontend--компоненты-и-ui-потоки)
10. [Безопасность (RBAC / RLS)](#10-безопасность-rbac--rls)
11. [Семантический слой (MDL)](#11-семантический-слой-mdl)
12. [RAG-подсистема](#12-rag-подсистема)
13. [Observability (Prometheus + Grafana)](#13-observability-prometheus--grafana)
14. [Проактивная аналитика (WatcherService)](#14-проактивная-аналитика-watcherservice)
15. [Data Flow — от вопроса к ответу](#15-data-flow--от-вопроса-к-ответу)
16. [Pydantic-контракты между агентами](#16-pydantic-контракты-между-агентами)
17. [Реализованный функционал (Frontend)](#17-реализованный-функционал-frontend)
18. [Пути развития (Roadmap)](#18-пути-развития-roadmap)
19. [Как запустить](#19-как-запустить)

---

## 1. Что это и зачем

**Prototip** — мультиагентная платформа бизнес-аналитики для государственных организаций. Построена на принципах **локального развёртывания** (on-premise): все данные обрабатываются внутри контура, без передачи во внешние облака.

Сотрудник задаёт вопрос **на русском языке** (например: *«Покажи задолженность по регионам за 2024 год»*), а система:

1. **Понимает** запрос через Семантический Слой (MDL + RAG)
2. **Планирует** выполнение через LangGraph StateGraph
3. **Извлекает данные** через безопасный Text-to-SQL → ClickHouse
4. **Проверяет себя** через двухуровневый SQL Eval Pipeline (синтаксис + логика)
5. **Анализирует** через AnalystAgent с Z-Score аномалиями и Reviewer CDO
6. **Визуализирует** — дашборд с KPI-картами, 3–5 графиков, инсайты
7. **Формирует** презентацию PowerPoint, Word-документ (docx) или экспортирует в Excel

Поддерживаются два LLM-бэкенда: **Vertex AI / Gemini** (облако, по умолчанию `USE_VERTEX=true`) и **Ollama** (локальный запуск `qwen2.5-coder`).

---

## 2. Технологический стек

| Слой | Технология | Версия (зафиксирована) | Назначение |
|------|------------|------------------------|-----------|
| **LLM (local)** | Ollama + `qwen2.5-coder:7b-instruct` | `0.6.2` | Генерация SQL, аналитика, презентации (оффлайн-режим) |
| **LLM (cloud)** | Google Vertex AI / Gemini | `google-genai 2.9.0` | Облачный LLM-бэкенд (по умолчанию) |
| **Оркестрация** | LangGraph (`StateGraph`) | `1.2.6` | Граф агентов, циклы, retry, стриминг |
| **Агенты (крю)** | CrewAI | `1.14.7` | Дополнительный слой для crew-задач (docx, tenant) |
| **База данных** | ClickHouse | latest | DWH, выполнение SQL, векторный поиск (cosineDistance) |
| **Объектное хранилище** | MinIO | latest | S3-совместимое хранилище артефактов (pptx, xlsx, png) |
| **Бэкенд** | Python 3.11+ / FastAPI | `0.115.5` | REST + WebSocket + SSE |
| **Безопасность SQL** | SQLGlot | `30.11.0` | AST-парсинг, инъекция WHERE (RLS) |
| **Семантика** | Pydantic v2 + YAML | `2.12.5` | MDL-слой, бизнес-глоссарий |
| **RAG** | LangChain + HuggingFace Embeddings | `1.3.10` / `5.6.0` | Документы, схемы, дашборды |
| **ETL** | Apache Airflow + PostgreSQL | latest | DAG-процессы загрузки данных (профиль `etl`) |
| **Фронтенд** | React 18 + TypeScript + Vite | latest | SPA с WebSocket |
| **CSS** | TailwindCSS v3 | latest | Тёмная тема, glassmorphism |
| **Анимации** | Framer Motion | latest | Переходы, micro-animations |
| **Графики** | Recharts | latest | Bar, Line, Pie, Area, Radar, Treemap и др. |
| **Observability** | Prometheus + Grafana | `prometheus-client 0.25.0` | Метрики, мониторинг, дашборды |
| **PDF / Word** | PyMuPDF (fitz) + python-pptx + python-docx | `1.0.2` / `1.2.0` | Извлечение текста, генерация PPTX и DOCX |
| **Планировщик** | APScheduler | `3.11.2` | Email-расписание, WatcherService |
| **Email** | smtplib + APScheduler | — | Расписание доставки отчётов |
| **Аутентификация** | JWT (python-jose) + bcrypt | `3.5.0` | Токен-авторизация, хеширование паролей |
| **CI** | GitHub Actions | — | Lint (ruff) + pytest + frontend build |

---

## 3. Инфраструктура (Docker Compose)

Весь стек управляется одним файлом [`docker-compose.yml`](../docker-compose.yml) через систему **профилей**.

```
┌─────────────────────────────────────────────────┐
│  Ядро (всегда запускается)                       │
│  genbi_frontend    → localhost:3000              │
│  genbi_backend     → localhost:8000              │
│  genbi_clickhouse  → localhost:8123 / 9000       │
│  genbi_minio       → localhost:9100 (API)        │
│  genbi_minio       → localhost:9101 (Console)    │
└─────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────┐
│  Профиль: etl                                   │
│  genbi_postgres    → localhost:5434              │
│  airflow_webserver → localhost:8081              │
│  airflow_scheduler                               │
└─────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────┐
│  Профиль: observability                          │
│  genbi_prometheus  → localhost:9090              │
│  genbi_grafana     → localhost:3001              │
└─────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────┐
│  Профиль: ollama (опционально)                  │
│  genbi_ollama      → localhost:11434             │
└─────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────┐
│  Профиль: auth (опционально)                    │
│  genbi_keycloak    → localhost:8080              │
└─────────────────────────────────────────────────┘
```

Команды запуска:
```bash
# Ядро
docker compose up -d

# Ядро + ETL + Мониторинг
docker compose --profile etl --profile observability up -d
```

Также поставляется [`docker-compose.tenant.template.yml`](../docker-compose.tenant.template.yml) — шаблон для автоматического создания **изолированного ClickHouse-контейнера** на каждого нового клиента (multi-tenant). Файл генерируется скриптом `scripts/build_tenant.py` с подстановкой переменных `${CLIENT_ID}`, `${CH_HTTP_PORT}`, `${CH_PASSWORD}`.

---

## 4. Высокоуровневая архитектура

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                   FRONTEND (React 18 + TypeScript + Vite)                    │
│  ┌──────────┐  ┌──────────────┐  ┌──────────────────┐  ┌──────────────────┐  │
│  │   Chat   │  │  Dashboard│  │  Presentation    │  │  Workspace DB    │  │
│  │  (WS чат)│  │  (KPI+Charts)│  │  (PPTX просмотр) │  │  (CSV/XLSX)     │  │
│  └──────────┘  └──────────────┘  └──────────────────┘  └──────────────────┘  │
└─────────────────────────────┬────────────────────────────────────────────────┘
                              │ WebSocket ws://localhost:8000/ws/chat
                              │ REST API   http://localhost:8000
                              ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                        FASTAPI (app/main.py)                                 │
│  /ws/chat    /ask    /ask_stream    /generate_dashboard                      │
│  /generate_presentation    /api/v1/...    /auth/login    /metrics /health    │
└─────────────────────────────┬────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                   ORCHESTRATOR (app/orchestrator.py)                         │
│  ask() → LangGraph          dashboard() → DashboardAgent                     │
│  presentation() → PresentationAgent   crew() → CrewOrchestrator              │
└─────────────────────────────┬────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                   LANGGRAPH StateGraph (app/graph.py)                        │
│                                                                              │
│  START → [search] → [planner] → [supervisor] → [data] → [analyst]          │
│                       ↗                                        ↓             │
│              (RAG Cache)                                  [reviewer]         │
│                                                         ↙         ↘         │
│                                                 (retry)          [presenter]→END │
└─────────────────────┬──────────────────────────────────────────────────────┘
                      │
       ┌──────────────┼───────────────┬──────────────────┐
       ▼              ▼               ▼                  ▼
┌────────────┐  ┌──────────────┐ ┌────────────┐  ┌──────────────────┐
│ ClickHouse │  │ Vertex AI /  │ │ RAG (Lang- │  │ MinIO (S3)       │
│ (DWH+SQL+  │  │ Ollama LLM   │ │ Chain +    │  │ (PPTX,XLSX,PNG) │
│ векторы)   │  │              │ │ HuggingFace│  │                  │
└────────────┘  └──────────────┘ └────────────┘  └──────────────────┘
```

---

## 5. Граф агентов (LangGraph)

Файл: [`app/graph.py`](../backend/app/graph.py)

Граф построен на `StateGraph` из `langgraph`. Каждый **узел** — отдельная функция Python. **Переходы** управляются условными роутерами.

### 5.1 Состояние графа (`GraphState`)

```python
class GraphState(TypedDict):
    question: str                    # Вопрос пользователя (на русском)
    drilldown: Optional[DrilldownContext]  # Контекст детализация (фильтры)
    user_role: Optional[str]         # Роль RBAC (manager / admin / grodno_manager ...)
    business_context: Optional[str]  # Результат RAG-поиска
    sub_questions: Optional[list[str]] # Подзадачи (TaskDecomposer)
    raw_data: Optional[list]         # Данные из ClickHouse
    sql: Optional[str]               # Сгенерированный SQL
    analysis: Optional[str]          # Текстовый анализ от AnalystAgent
    chart_spec: Optional[dict]       # Спецификация графика
    final_result: Optional[Any]      # Итоговый результат для UI
    error: Optional[str]             # Ошибка, если произошла
    messages: Annotated[list, add_messages]  # История сообщений LangChain
    raw_analysis_dict: Optional[dict]  # Структурированный анализ (для Reviewer)
    eval_feedback: Optional[str]     # Обратная связь от ReviewerAgent
    eval_retry_count: Optional[int]  # Счётчик попыток пересмотра
    route: Optional[str]             # Маршрут из supervisor (data / direct_answer)
```

### 5.2 Топология графа

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

### 5.3 Роутинг

| Функция | Условие | Куда |
|---------|---------|------|
| `route_after_search` | `drilldown` есть → skip cache | `planner` |
| `route_after_search` | `final_result` заполнен | `END` |
| `route_after_supervisor` | `drilldown` есть | `data` (всегда) |
| `route_after_supervisor` | route = `direct_answer` | `END` |
| `route_after_reviewer` | `eval_feedback` есть | `analyst` (retry) |
| `route_after_reviewer` | feedback = None | `presenter` |

**Ключевая особенность:** при детализации кэш полностью пропускается и `final_result` принудительно очищается в `supervisor_node`, чтобы избежать возврата устаревшего результата.

---

## 6. Все агенты и их взаимодействия

### 6.1 Полный реестр агентов

| Агент | Файл | Роль в системе |
|-------|------|----------------|
| **RagAgent** | `agents/rag_agent.py` | Поиск бизнес-контекста (LangChain + HuggingFace) |
| **TaskDecompositionAgent** | `agents/task_decomposer.py` | Декомпозиция запроса на подзадачи |
| **DataAgent** | `agents/data_agent.py` | Text-to-SQL → ClickHouse (ядро системы) |
| **SqlEvaluatorAgent** | `agents/sql_evaluator.py` | LLM-as-Judge для проверки SQL-логики |
| **AnalystAgent** | `agents/analyst_agent.py` | Инсайты на русском + Z-Score аномалии |
| **ReviewerAgent** | `agents/reviewer_agent.py` | CDO-критик (обратная связь) |
| **ChartAgent** | `agents/chart_agent.py` | Выбор типа и спецификации графика |
| **ForecastAgent** | `agents/forecast_agent.py` | Предиктивный анализ |
| **ForecastAnalystAgent** | `agents/forecast_analyst_agent.py` | Расширенный аналитик для прогнозов (statsmodels) |
| **DashboardAgent** | `agents/dashboard_agent.py` | Полный дашборд (KPI + N графиков) |
| **PresentationAgent** | `agents/presentation_agent.py` | Генерация PPTX-презентации |
| **ReportDocxAgent** | `agents/report_docx_agent.py` | Генерация отчётов в формате Word (DOCX) |
| **CrewAgents** | `crew/agents.py` | CrewAI-агенты для crew-задач (docx, tenant) |

---

### 6.2 DataAgent — Сердце системы

**Файл:** [`app/agents/data_agent.py`](../backend/app/agents/data_agent.py)

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
   - Если role = "minsk_manager"  → WHERE region = 'г. Минск'

8. SqlEvaluatorAgent (LLM-as-Judge) → проверка логики
   → Если ошибка → retry с фидбеком

9. Сохранить в SemanticCache (если нет drilldown)
```

**Ключевые защиты:**
- Auto-LIMIT 500 если отсутствует
- Whitelist: только SELECT
- EXPLAIN SYNTAX перед выполнением
- SQLGlot RLS (AST-инъекция WHERE)
- LLM-as-Judge проверка логики (SqlEvaluator)

---

### 6.3 AnalystAgent

**Файл:** [`app/agents/analyst_agent.py`](../backend/app/agents/analyst_agent.py)

**Задача:** Данные → 3–4 русских инсайта + ключевой вывод + аномалии/тренды.

**Особенности:**
- **Z-Score аномалии:** математическое обнаружение выбросов (порог 2.5σ) по всем числовым колонкам до вызова LLM — затем аномалии вставляются в промпт
- **Chart Context:** если передан `chart_spec`, аналитик обязан упомянуть визуализацию в инсайтах
- **Обогащение детализации:** при активной детализации фокус на конкретном сегменте
- **Follow-up questions:** всегда возвращает 2–3 следующих вопроса
- **безопасное игнорирование ошибок:** при пустых данных — информативная ошибка, не падение
- **ReviewerAgent feedback loop:** если Reviewer отклонил, AnalystAgent получает критику и переписывает анализ

---

### 6.4 ReviewerAgent (CDO)

**Файл:** [`app/agents/reviewer_agent.py`](../backend/app/agents/reviewer_agent.py)

**Задача:** Независимая проверка качества аналитики перед финальным ответом.

**Роль:** Условный «Chief Data Officer» — строгий критик, который проверяет:
- Опираются ли выводы на реальные числа из данных?
- Нет ли галлюцинаций в аналитике?
- Достаточно ли глубоки инсайты?

**Ограничение:** максимум 1 итерация пересмотра (`retry_count < 1`), чтобы не зациклить граф.

---

### 6.5 DashboardAgent

**Файл:** [`app/agents/dashboard_agent.py`](../backend/app/agents/dashboard_agent.py)

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

**безопасное игнорирование ошибок:** при любой ошибке возвращает минимальный рабочий дашборд.

---

### 6.6 PresentationAgent

**Файл:** [`app/agents/presentation_agent.py`](../backend/app/agents/presentation_agent.py)

**Задача:** Список вопросов → PPTX-файл со слайдами + PNG-превью.

**процесс генерации:**
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

### 6.7 ReportDocxAgent

**Файл:** [`app/agents/report_docx_agent.py`](../backend/app/agents/report_docx_agent.py)

**Задача:** Генерация полноценных Word-документов (DOCX) с аналитическими отчётами. Использует `python-docx`. Рендерер реализован в `services/docx_renderer.py`.

---

### 6.8 ChartAgent

**Файл:** [`app/agents/chart_agent.py`](../backend/app/agents/chart_agent.py)

**Задача:** Вопрос + данные → `ChartSpec` (тип графика + оси + заголовок + данные).

**Поддерживаемые типы:** `bar`, `line`, `pie`, `donut`, `horizontal_bar`, `area`, `scatter`, `radar`, `kpi`, `composed`, `table`, `treemap`

---

### 6.9 ForecastAgent + ForecastAnalystAgent

**Файлы:** [`forecast_agent.py`](../backend/app/agents/forecast_agent.py) / [`forecast_analyst_agent.py`](../backend/app/agents/forecast_analyst_agent.py)

**Задача:** Исторические данные → предиктивный анализ + тренды + прогнозный ChartSpec. Расширенный вариант использует `scipy` и `statsmodels` для статистически обоснованных прогнозов.

Активируется в `presenter_node` при наличии слова «прогноз» в запросе.

---

### 6.10 CrewAI-слой

**Папка:** [`app/crew/`](../backend/app/crew/)

Дополнительный слой поверх основного LangGraph-процесса. Используется для:
- Генерации сложных DOCX-отчётов через `CrewOrchestrator`
- Специализированных задач по обработке тенантных данных

| Файл | Назначение |
|------|-----------|
| `agents.py` | Определения CrewAI-агентов (ролей) |
| `tasks.py` | Определения задач для агентов |
| `tools.py` | Инструменты (ClickHouse-запросы, форматирование) |
| `crew_orchestrator.py` | Точка входа в CrewAI-процесс |

---

## 7. Backend — модули и API

### 7.1 Структура модулей

```
backend/
├── app/
│   ├── main.py                    # FastAPI — все маршруты (95 KB)
│   ├── orchestrator.py            # Единая точка входа (ask/dashboard/presentation)
│   ├── graph.py                   # LangGraph StateGraph (26 KB)
│   ├── auth.py                    # JWT аутентификация + управление пользователями
│   ├── security.py                # Password hashing (bcrypt)
│   ├── config.py                  # Конфигурация приложения (env vars)
│   ├── schemas.py                 # Pydantic-схемы для API (re-export из agents/models)
│   │
│   ├── agents/
│   │   ├── models.py              # ВСЕ Pydantic-контракты между агентами (21 KB)
│   │   ├── data_agent.py          # Text-to-SQL (core)
│   │   ├── analyst_agent.py       # Инсайты на русском
│   │   ├── chart_agent.py         # Визуализация
│   │   ├── dashboard_agent.py     # Комплексный дашборд
│   │   ├── presentation_agent.py  # PPTX генерация
│   │   ├── report_docx_agent.py   # DOCX генерация
│   │   ├── forecast_agent.py      # Предиктивный анализ (базовый)
│   │   ├── forecast_analyst_agent.py  # Предиктивный анализ (statsmodels)
│   │   ├── reviewer_agent.py      # CDO-критик
│   │   ├── rag_agent.py           # RAG-контекст
│   │   ├── sql_evaluator.py       # LLM-as-Judge для SQL
│   │   ├── task_decomposer.py     # Декомпозиция запросов
│   │   ├── base_agent.py          # Базовый класс агента
│   │   ├── executor.py            # AgentExecutor (6 KB)
│   │   ├── factory.py             # Синглтон AgentExecutor
│   │   ├── config_loader.py       # Загрузка конфигов из YAML
│   │   └── db_schema_extractor.py # Динамическое извлечение схемы БД
│   │
│   ├── crew/                      # CrewAI слой
│   │   ├── agents.py              # Роли CrewAI-агентов
│   │   ├── tasks.py               # Задачи для CrewAI
│   │   ├── tools.py               # Инструменты (8 KB)
│   │   └── crew_orchestrator.py   # CrewAI оркестратор
│   │
│   ├── config/
│   │   └── agents.yaml            # Промпты, роли, few-shot примеры для всех агентов
│   │
│   ├── services/
│   │   ├── watcher_service.py     # Фоновое сканирование аномалий
│   │   ├── email_scheduler.py     # Расписание email доставки
│   │   ├── email_service.py       # Отправка email
│   │   ├── rag_service.py         # RAG ingestion + retrieval
│   │   ├── anomaly_detector.py    # Детектирование аномалий
│   │   ├── excel_renderer.py      # Генерация Excel файлов
│   │   ├── docx_renderer.py       # Генерация Word-документов
│   │   ├── subscription_service.py # Управление подписками
│   │   ├── metrics_service.py     # Бизнес-метрики (10 KB)
│   │   ├── tenant_stats.py        # Статистика по тенантам (13 KB)
│   │   ├── airflow_client.py      # HTTP-клиент для Airflow REST API
│   │   ├── schema_scanner.py      # Сканирование схемы БД
│   │   └── wrenai_client.py       # Клиент WrenAI (семантический слой)
│   │
│   ├── utils/
│   │   ├── clickhouse_client.py   # ClickHouse клиент (clickhouse-connect)
│   │   ├── clickhouse_optimization.py  # Оптимизация запросов ClickHouse
│   │   ├── clickhouse_rbac.py     # Управление ролями ClickHouse
│   │   ├── memory.py              # Conversation Memory (история диалогов)
│   │   ├── semantic_cache.py      # Кэш SQL-запросов (in-memory)
│   │   ├── schema_crawler.py      # Автогенерация semantic_model.yaml
│   │   ├── excel_exporter.py      # Красивый Excel export
│   │   ├── etl_worker.py          # ETL из Dropzone
│   │   ├── pdf_presentation.py    # PDF → PPTX
│   │   ├── anonymizer.py          # Анонимизация данных
│   │   ├── rag_indexer.py         # Индексирование документов в RAG
│   │   ├── init_schema_knowledge.py  # Инициализация Schema RAG
│   │   ├── init_clickhouse_knowledge.py  # Инициализация ClickHouse RAG
│   │   └── system_logger.py       # Системный логгер в ClickHouse
│   │
│   ├── etl/
│   │   └── tenant_pipeline.py     # ETL-процесс для тенантных данных (13 KB)
│   │
│   ├── routers/
│   │   ├── auth.py                # /auth/* роутер
│   │   └── etl.py                 # /api/v1/etl/* роутер (19 KB)
│   │
│   ├── api/
│   │   ├── email.py               # Email API
│   │   └── export.py              # Export API
│   │
│   ├── observability/
│   │   └── metrics.py             # Prometheus-метрики (custom + FastAPI instrumentator)
│   │
│   ├── semantic/
│   │   └── catalog.py             # Загрузка MDL YAML → LLM Prompt
│   │
│   ├── middleware/
│   │   └── logging.py             # HTTP-логирование запросов
│   │
│   ├── domain/
│   │   └── constants.py           # Константы домена (роли, регионы и т.д.)
│   │
│   ├── pipeline_progress.py       # Стриминг прогресса через WebSocket
│   ├── agent_context.py           # Context vars (роль, debate queue, events)
│   ├── presentation_renderer.py   # python-pptx рендерер слайдов (48 KB)
│   ├── slide_pipeline.py          # процесс сборки слайдов
│   ├── drilldown.py               # Обработка детализирующих запросов
│   ├── chart_repair.py            # Авто-исправление битых ChartSpec
│   ├── chart_data_profile.py      # Профилирование данных для выбора типа графика
│   ├── data_sampling.py           # Сэмплирование больших наборов данных
│   ├── storytelling.py            # Генерация нарративов для слайдов
│   ├── kpi_utils.py               # Утилиты расчёта KPI
│   ├── planner_utils.py           # Утилиты планировщика
│   ├── logger_setup.py            # Настройка логирования
│   └── logging_utils.py           # Утилиты логирования
│
├── airflow/                       # Apache Airflow для ETL-процессов
│   ├── Dockerfile
│   ├── dags/
│   │   ├── etl_common.py          # Общие DAG-утилиты
│   │   └── etl_tenant_load.py     # DAG загрузки тенантных данных
│   └── requirements-airflow.txt
│
├── data/                          # Семантические модели, конфиги
├── scripts/                       # Вспомогательные скрипты
├── tests/                         # Тесты (pytest)
└── requirements.txt               # Зафиксированные зависимости
```

### 7.2 Конфигурация агентов (Hot Reload)

Файл: [`app/config/agents.yaml`](../backend/app/config/agents.yaml)

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

### 7.3 REST / WebSocket API

| маршрут | Метод | Назначение |
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
| `/api/v1/pipeline/status` | GET | Прогресс процесса |
| `/api/v1/sql-logs` | GET | SQL логи из ClickHouse system |
| `/api/user/dashboard` | GET/POST | Сохранение закреплённых графиков |
| `/api/v1/etl/*` | GET/POST | ETL роутер (управление процессами, тенантами) |
| `/auth/login` | POST | JWT аутентификация |
| `/health` | GET | Health-check |
| `/metrics` | GET | Prometheus метрики |

### 7.4 Startup (Lifespan Events)

При запуске FastAPI автоматически:
1. `start_scheduler()` — запускает APScheduler для Email доставки
2. `generate_semantic_model()` — автогенерация `semantic_model.yaml` из схемы ClickHouse
3. `init_schema_knowledge()` — инициализация Smart Schema RAG
4. `initialize_dashboard_rag()` — загрузка дашбордов в RAG-индекс

---

## 8. ETL-подсистема (Airflow)

Файл: [`backend/airflow/`](../backend/airflow/)

Запускается через профиль `etl` (Docker Compose). Обеспечивает управляемую загрузку и трансформацию данных.

### 8.1 Компоненты

| Компонент | Роль |
|-----------|------|
| **PostgreSQL** | Метадата-база Airflow (состояние DAG'ов, логи) |
| **Airflow Webserver** | UI → `localhost:8081` (admin/admin) |
| **Airflow Scheduler** | Запуск задач по расписанию |
| **airflow-init** | Одноразовый контейнер: `db migrate` + создание пользователя |

### 8.2 DAG'и

| DAG | Файл | Назначение |
|-----|------|-----------|
| `etl_tenant_load` | `dags/etl_tenant_load.py` | Загрузка данных нового тенанта в ClickHouse |
| `etl_common` | `dags/etl_common.py` | Утилиты и вспомогательные операторы |

### 8.3 Интеграция с Backend

Backend (через `services/airflow_client.py`) может триггерить DAG'и через **Airflow REST API** (`POST /api/v1/dags/{dag_id}/dagRuns`). Аутентификация: Basic Auth.

```python
# airflow_client.py
airflow_client.trigger_dag("etl_tenant_load", conf={"tenant_id": "..."})
```

Внутри DAG'ов используется `etl/tenant_pipeline.py` — основной Python-процесс загрузки тенантных данных.

---

## 9. Frontend — компоненты и UI-потоки

### 9.1 Структура компонентов

```
frontend/src/
├── App.tsx                    # Корневой компонент, роутинг views (39 KB)
├── main.tsx                   # Точка входа React
├── store/
│   └── useChatStore.ts        # Zustand store (глобальное состояние)
├── hooks/
│   └── useChatSocket.ts       # WebSocket хук
├── utils/                     # Утилиты
├── lib/                       # Библиотечные утилиты
├── components/
│   ├── layout/
│   │   └── Header.tsx         # Верхняя панель навигации
│   ├── chat/
│   │   ├── ChatContainer.tsx  # Список сообщений
│   │   ├── ChatInput.tsx      # Поле ввода + кнопка отправки
│   │   ├── MessageBubble.tsx  # Сообщение (текст + графики + SQL) [13 KB]
│   │   ├── DynamicChart.tsx   # Recharts рендер (13+ типов) [34 KB]
│   │   ├── AgentGraph.tsx     # Анимированный граф агентов
│   │   └── widgets/           # KPI карточки, инсайты
│   ├── dashboard/
│   │   ├── AIDashboardView.tsx         # Полный просмотр дашборда
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

### 9.2 Виды (Views) главного экрана

| View | Активация | Содержимое |
|------|-----------|-----------| 
| `chat` | по умолчанию | Основной чат + ChatInput |
| `ai_dashboard` | клик на дашборд в sidebar | AIDashboardView (KPI + Charts) |
| `presentation` | клик на презентацию в sidebar | PresentationView (слайды + скачать) |
| `workspace_db` | кнопка «Workspace БД» | WorkspaceDBView |
| `profile` | кнопка профиля в Header | UserProfile |
| `subscriptions` | кнопка подписок | SubscriptionsView |

### 9.3 WebSocket Flow

```
1. Frontend (useChatSocket.ts) → отправляет:
   {question, session_id, drilldown?: {key, value, action}}

2. Backend (main.py) → разбирает drilldown, создаёт DrilldownContext

3. Запускает orchestrator.ask() в executor (не блокируя event loop)

4. Параллельно шлёт в WebSocket:
   - {type: "status"}          — статусы ("Анализирую данные...")
   - {type: "debate"}          — "дебаты" агентов (живая трансляция)
   - {type: "node_event"}      — текущий активный узел
   - {type: "pipeline_update"} — прогресс стейджей

5. По завершении → {type: "result", content, sql?, pptx_path?, excel_path?}

6. Frontend → парсит JSON-блоки из content → рендерит DynamicChart
```

### 9.4 механизм детализации

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

## 10. Безопасность (RBAC / RLS)

### 10.1 Аутентификация

- **JWT токены** через `/auth/login`
- Токен кодирует: `{username, role}`
- Поддерживаемые роли: `manager`, `admin`, `grodno_manager`, `minsk_manager`
- Хранится в `localStorage`; срок действия — 24 часа
- Хеширование паролей: **bcrypt** (`security.py`)

```
Логин: "grodno_admin" → role = "grodno_manager"
Логин: "minsk_user"  → role = "minsk_manager"
Логин: "admin_..."   → role = "admin"
```

### 10.2 Row-Level Security (RLS) через SQLGlot

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

### 10.3 SQL Whitelist

Запрещённые операции в промпте + явная проверка:
```python
for bad in ("insert", "update", "delete", "drop", "create", "alter", ";--"):
    if bad in sql.lower():
        raise ValueError(f"Запрещённая операция в SQL: {bad}")
```

### 10.4 Rate Limiting

Используется `slowapi` (Starlette-совместимый) для ограничения частоты запросов к API.

---

## 11. Семантический слой (MDL)

### 11.1 Структура

Файл: [`data/semantic_model.yaml`](../backend/data/semantic_model.yaml)

Бизнес-описание всех таблиц и метрик в YAML-формате (аналог WrenAI MDL / Cube.js). Содержит:
- Описания таблиц на русском
- Описания каждой колонки (что значит, примеры значений)
- Бизнес-метрики (`debt_ratio`, `collection_rate` и т.д.)
- Связи между таблицами

### 11.2 Загрузка при старте

```python
# utils/schema_crawler.py
generate_semantic_model()  # Автоматическая генерация из ClickHouse schema

# semantic/catalog.py
catalog = SemanticCatalog.load(schema_path)
# Преобразует YAML → строгий LLM-промпт
llm_prompt = catalog.to_llm_prompt()
```

---

## 12. RAG-подсистема

### 12.1 Три RAG-индекса

| Индекс | Назначение | Когда используется |
|--------|------------|-------------------|
| **Schema RAG** | Описания колонок, типы данных | `planner_node` / `DataAgent` |
| **Dashboard RAG** | История прошлых дашбордов | `DashboardAgent` (шаблоны) |
| **Document RAG** | PDF документы, аналитика | Полнотекстовый поиск |

### 12.2 Технология

Векторный поиск реализован поверх **ClickHouse** (`cosineDistance`). Эмбеддинги генерируются через **HuggingFace `sentence-transformers`** (`langchain-huggingface==1.2.2`).

> **Примечание:** отдельный сервис Qdrant был удалён из стека как неиспользуемый. При росте объёмов знаний до сотен миллионов документов — возможен возврат к выделенному векторному хранилищу с HNSW-индексами.

### 12.3 Semantic Cache (SQL-уровень)

```python
# utils/semantic_cache.py — in-memory словарь
cached_sql = semantic_cache.get_sql(question)
semantic_cache.set_sql(question, sql)
```

**Ограничение:** drilldown-запросы НИКОГДА не кэшируются (содержат фильтры конкретного сегмента).

---

## 13. Observability (Prometheus + Grafana)

Запускается через профиль `observability`.

### 13.1 Метрики

Файл: [`app/observability/metrics.py`](../backend/app/observability/metrics.py)

- **Стандартные HTTP-метрики** — через `prometheus-fastapi-instrumentator` (автоматически)
- **Бизнес-метрики** — кастомные `prototip_*` метрики (кол-во запросов к агентам, latency LLM, размер данных и т.д.)
- **Prometheus endpoint:** `/metrics`

### 13.2 Prometheus Config

Файл: [`ops/prometheus/prometheus.yml`](../ops/prometheus/prometheus.yml)

```yaml
global:
  scrape_interval: 15s
scrape_configs:
  - job_name: 'backend'
    static_configs:
      - targets: ['backend:8000']
```

### 13.3 Grafana

- **URL:** `localhost:3001` (admin/admin)
- Дашборды хранятся в `ops/grafana/dashboards/` и загружаются автоматически через provisioning
- Datasource (Prometheus) прописан в `ops/grafana/provisioning/datasources/datasource.yml`

---

## 14. Проактивная аналитика (WatcherService)

**Файл:** [`app/services/watcher_service.py`](../backend/app/services/watcher_service.py)

### 14.1 Что делает

Система сама (без запроса пользователя) периодически:
1. Сканирует данные ClickHouse на аномалии
2. Если найдено → формирует тревожный отчёт
3. Отправляет email руководителю

### 14.2 Запуск

- **Автоматически** по расписанию через APScheduler (`email_scheduler.py`)
- **Вручную** через API: `POST /api/v1/trigger_watcher`
- **Из UI** через кнопку «Запустить сканирование» в сайдбаре

### 14.3 Email доставка

```
Расписание: APScheduler (cron-like)
Формат: JSON в out/mock_emails/ (dev), SMTP (prod)
Endpoint: POST /api/v1/send-email
```

---

## 15. Data Flow — от вопроса к ответу

### 15.1 Основной чат-запрос

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
    ├── search_node:   SearchPastReportsTool → нет совпадений → продолжаем
    │
    ├── planner_node:  RagAgent → context ("Задолженность = debt поле...")
    │                  TaskDecomposer → [вопрос не разбивается]
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
    │       └── LLM → {insights: [...], key_conclusion: "...", follow_up_questions: [...]}
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

### 15.2 Генерация дашборда (прямой путь)

```
POST /generate_dashboard {question, max_charts=4, include_kpi=true}
    │
    ▼
orchestrator.dashboard() → AgentExecutor.run("dashboard_agent", req)
    │
    ▼
DashboardResult → JSON → Frontend → AIDashboardView
```

### 15.3 Генерация презентации

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

## 16. Pydantic-контракты между агентами

Файл: [`app/agents/models.py`](../backend/app/agents/models.py) — **единственный источник истины** для всех типов данных.

```
AgentResult (base)
    ├── SqlResult            ← DataAgent output
    ├── AnalysisResult       ← AnalystAgent output
    ├── ChartAgentResult     ← ChartAgent output
    ├── RagResult            ← RagAgent output
    ├── DashboardResult      ← DashboardAgent output
    ├── PresentationResult   ← PresentationAgent output
    ├── DeckNarrative        ← PresentationAgent internal
    └── AskResult            ← Orchestrator final output

Планировщик (Task Planner):
    ├── Task                 ← Единица плана
    ├── Plan                 ← Полный план выполнения
    ├── AgentCall            ← Запись вызова агента (трассировка)
    ├── PlanExecutionStep    ← Шаг выполнения (для UI trace)
    └── PlannerTrace         ← Трассировка (Plan + AgentCall[])

Вспомогательные:
    ├── DrilldownContext      ← UI → Backend (фильтры детализация)
    ├── DashboardRequest      ← API → DashboardAgent input
    ├── PresentationRequest   ← API → PresentationAgent input
    ├── KpiCard               ← KPI-карточка
    ├── DashboardLayout       ← Рекомендация расположения
    ├── SupervisorDecision    ← Маршрутизатор (data/direct_answer)
    ├── SlideData             ← Данные одного слайда
    ├── SlideUpdate           ← Частичное обновление слайда
    └── QuestionBlock         ← Блок вопроса из UI-формы
```

**Принцип:** агенты общаются ТОЛЬКО через Pydantic-модели, никаких голых `dict`. Базовый класс `AgentResult` включает поля `confidence_score` и `recommendations` для интеграции с PlannerAgent.

---

## 17. Реализованный функционал (Frontend)

| Функция | Где | Статус |
|---------|-----|--------|
| Авторизация (JWT + bcrypt) | `LoginScreen` → `App.tsx` | ✅ |
| Чат с LLM агентами (WebSocket) | `ChatContainer` + `useChatSocket` | ✅ |
| Парсинг и рендер графиков (13+ типов) | `DynamicChart.tsx` [34 KB] | ✅ |
| Live Прогресс процесса | `MessageBubble` → pipeline stages | ✅ |
| Дебаты агентов в реальном времени | `debate` events в WS | ✅ |
| Анимированный граф агентов | `AgentGraph.tsx` | ✅ |
| детализация (клик по графику → детализация) | `handleChartClick` | ✅ |
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

## 18. Пути развития (Roadmap)

### 18.1 Инфраструктура и MLOps (Наблюдаемость ИИ)

- **LLM-Трейсинг (Langfuse / LangSmith):** Визуализация каждого шага LangGraph, точное потребление токенов, latency каждого узла, «Cost per Query».
- **Стриминг токенов (Token-by-Token):** Сейчас стримятся статусы прогресса; следующий шаг — транслировать ответы AnalystAgent посимвольно для снижения Time-To-First-Token.
- **DPO Feedback Loop:** Кнопки 👍/👎 под ответами → автосохранение в ClickHouse (JSONL) → датасет для Fine-Tuning локальной модели на специфику предприятия.

### 18.2 Ядро данных и ClickHouse

- **Self-Healing SQL & Materialized Views:** DataAgent анализирует `system.query_log` и автоматически предлагает создание MV или индексов.
- **Интеграция dbt:** Вынос трансформаций в dbt-слой; агенты генерируют SQL поверх чистых dbt-витрин.
- **Масштабирование RAG:** При росте до сотен миллионов документов — возврат к выделенному Qdrant с HNSW-индексами.

### 18.3 Безопасность и интеграции

- **Полноценная миграция на Keycloak (SSO / OIDC):** Контейнер уже заложен в Docker Compose; нужен полный OAuth2 flow с поддержкой LDAP, 2FA.
- **Column-Level Security:** Фильтрация на уровне колонок (маскирование ФИО для ролей без полного доступа).
- **Telegram-интеграция:** Бот, позволяющий запрашивать KPI и дашборды текстом со смартфона.

### 18.4 Пользовательский опыт (Frontend)

- **Коллаборативный режим (Multiplayer):** CRDT (Yjs) на дашбордах — несколько пользователей одновременно (аналог Figma).
- **Progressive Web App (PWA):** Service Workers для офлайн-кэширования дашбордов.
- **Voice-to-SQL:** Кнопка микрофона + Web Speech API / Whisper → текст → Orchestrator.

### 18.5 Расширенные аналитические возможности

- **AI ETL Wizard:** `ETLAgent` автоматически разбирает колонки CSV/Excel, чистит данные и обновляет `semantic_model.yaml`.
- **Data Lineage:** Визуальный граф происхождения каждой цифры (из какой таблицы, с какими фильтрами).
- **Глубокая предиктивная аналитика:** Расширение ForecastAnalystAgent за счёт `Prophet` / `ARIMA` с доверительными интервалами и «What-If» анализом.

---

## 19. Как запустить

> **Подробное руководство:** [`STARTUP_GUIDE.md`](../STARTUP_GUIDE.md)

### 19.1 Быстрый старт (Docker Compose)

```bash
cd prototip

# Ядро: Frontend + Backend + ClickHouse + MinIO
docker compose up -d

# Со всеми профилями (ETL + мониторинг)
docker compose --profile etl --profile observability up -d

# С локальным LLM (Ollama)
docker compose --profile ollama up -d
```

### 19.2 Переменные окружения (`.env`)

Создайте `.env` на основе [`.env.example`](../.env.example):

```env
# LLM (выберите один режим)
USE_VERTEX=true                              # true = Vertex AI, false = Ollama
AI_MODEL=gemini-3.5-flash
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_APPLICATION_CREDENTIALS=/app/secrets/gcp.json
OLLAMA_MODEL=qwen2.5-coder:7b-instruct

# Безопасность
APP_SECRET_ENCRYPTION_KEY=your-32-char-key

# ClickHouse
CLICKHOUSE_HOST=localhost
CLICKHOUSE_PORT=8123
CLICKHOUSE_PASSWORD=

# MinIO (S3)
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin

# Airflow
AIRFLOW_USERNAME=admin
AIRFLOW_PASSWORD=admin

# Email
SMTP_HOST=smtp.example.com
SMTP_PORT=587
```

### 19.3 Локальная разработка (без Docker)

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Frontend
cd frontend
npm install
npm run dev   # http://localhost:5173
```

### 19.4 Тестовые логины

| Логин | Пароль | Роль | Доступ |
|-------|--------|------|--------|
| `admin` | любой | `admin` | Весь датасет |
| `grodno_user` | любой | `grodno_manager` | Только г. Гродно |
| `minsk_user` | любой | `minsk_manager` | Только г. Минск |
| `analyst` | любой | `manager` | Весь датасет |

### 19.5 CI (GitHub Actions)

Конфигурация: [`.github/workflows/ci.yml`](../.github/workflows/ci.yml)

Запускается автоматически при push/PR в `main`:
1. **backend-lint** — `ruff check`
2. **backend-test** — `pytest -m "not live"`
3. **frontend-build** — `tsc + vite build`

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
     ├─[search_node]────────────────────────────────────┐
     │   SearchPastReportsTool (RAG history cache)       │
     │                                                   │
     ├─[planner_node]                                    │
     │   ├─ RagAgent (HuggingFace embeddings + CH)       │
     │   └─ TaskDecompositionAgent                       │
     │                                                   │
     ├─[supervisor_node]                                 │
     │   └─ LLM: SupervisorDecision {route}              │
     │                                                   │
     ├─[data_node]                                       │
     │   └─ DataAgent                                    │
     │       ├─ SemanticCatalog.to_llm_prompt()          │
     │       ├─ LLM (Vertex AI / Ollama) → SQL           │
     │       ├─ ClickHouse EXPLAIN SYNTAX                │
     │       ├─ SQLGlot RLS injection                    │
     │       ├─ ClickHouse execute()                     │
     │       └─ SqlEvaluatorAgent (LLM-as-Judge)         │
     │                                                   │
     ├─[analyst_node]                                    │
     │   └─ AnalystAgent                                 │
     │       ├─ Z-Score anomaly detection (scipy)        │
     │       └─ LLM → AnalysisResult                     │
     │                                                   │
     ├─[reviewer_node]                                   │
     │   └─ ReviewerAgent (CDO critique)                 │
     │       └─ (если плохо → retry к analyst)           │
     │                                                   │
     └─[presenter_node]                                  │
         ├─ DashboardAgent ─────────────────────────┐    │
         │   ├─ AnalystAgent (insights)             │    │
         │   ├─ LLM → DashboardComposition          │    │
         │   └─ [Parallel] ChartAgent x4            │    │
         │                                          │    │
         ├─ ForecastAgent / ForecastAnalystAgent    │    │
         │   └─ (если "прогноз", statsmodels)       │    │
         │                                          │    │
         ├─ PresentationAgent (если "презентац")    │    │
         │   ├─ [Parallel] Orchestrator.ask() x N  │    │
         │   ├─ LLM → DeckNarrative                │    │
         │   └─ SlidePipeline → python-pptx         │    │
         │                                          │    │
         └─ ReportDocxAgent (если "отчёт docx")     │    │
             └─ python-docx → .docx                 │    │
                                                    │    │
AskResult ──────────────────────────────────────────┘    │
     │                                                    │
     ▼                                                    │
WebSocket → Frontend ←───────────────────────────────────┘
     │
     ├─ DynamicChart (Recharts, 13+ типов)
     ├─ KpiCards
     ├─ AgentGraph (анимация)
     └─ Debate stream (живые сообщения агентов)
```
