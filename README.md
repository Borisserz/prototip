# Prototip BI — AI-аналитическая платформа

Мультиагентная BI-платформа: пользователь задаёт вопрос на естественном языке —
система генерирует SQL, считает аналитику, строит графики, дашборды, презентации и
отчёты. Под капотом — оркестратор на **LangGraph**, аналитическое хранилище
**ClickHouse** (включая векторное хранилище знаний/RAG поверх ClickHouse) и веб-интерфейс на **React**.

> Поддерживается мультитенантность (B2B): один экземпляр обслуживает несколько
> изолированных клиентов, у каждого — свой ClickHouse, своя семантика и свой токен.

---

## 📂 Структура репозитория

```
prototip/
├── frontend/     # React + Vite + Tailwind + nginx   (веб-интерфейс)
├── backend/      # FastAPI API + LangGraph-агенты      (сервер + работа с агентами)
│   ├── app/         # веб-слой: роутеры, auth, экспорт, дашборды, админка клиентов
│   ├── app/agents/  # агенты LangGraph (engine: SQL, графики, отчёты, прогноз…)
│   ├── app/orchestrator.py, app/graph.py  # оркестрация агентов
│   ├── core/        # общие сервисы: LLM, хранилище (MinIO), реестр клиентов, SQL-guard
│   ├── domain/      # бизнес-знания: метрики, playbook графиков, примеры SQL
│   ├── viz/         # рендеринг графиков
│   └── scripts/     # ETL/seed/сборка тенантов
├── db/           # ClickHouse (Dockerfile + init.sql + seed)  — аналитическое хранилище
├── docs/         # ARCHITECTURE.md
├── docker-compose.yml             # оркестрация всего стека
└── docker-compose.tenant.template.yml  # шаблон изолированного клиента
```

Каждая папка-сервис (`frontend`, `backend`, `db`) имеет свой **Dockerfile** и может
быть собрана/поднята как отдельно, так и вместе через корневой `docker-compose.yml`.

---

## 🚀 Быстрый старт

```bash
# 1. Конфигурация
cp .env.example .env          # при необходимости отредактируйте

# 2. Поднять весь стек (frontend + backend + ClickHouse + MinIO + Ollama)
docker compose up -d --build

# 3. Открыть
#    Frontend:        http://localhost:3000
#    Backend (API):   http://localhost:8000/docs
#    MinIO консоль:   http://localhost:9101
```

### Запуск отдельных частей

```bash
docker compose up -d clickhouse minio   # только базы/хранилища
docker compose up -d backend                   # только бэкенд
docker compose up -d frontend                  # только фронтенд
```

### Опциональные профили

```bash
docker compose --profile auth up -d    # Keycloak (внешняя аутентификация)
docker compose --profile etl  up -d --build  # Postgres + Airflow (ETL-оркестрация → backend/airflow/README.md)
docker compose --profile observability up -d   # Prometheus + Grafana
```

---

## 🧩 Сервисы и порты

| Сервис      | Порт (хост)        | Назначение                              |
|-------------|--------------------|-----------------------------------------|
| frontend    | 3000               | Веб-интерфейс (nginx)                   |
| backend     | 8000               | FastAPI API + Swagger `/docs`           |
| clickhouse  | 8123 / 9000        | Аналитическое хранилище                 |
| minio       | 9100 (S3) / 9101   | Объектное хранилище артефактов          |
| ollama      | 11434              | Локальный LLM (по умолчанию)            |
| keycloak*   | 8080               | Аутентификация (профиль `auth`)         |
| airflow*    | 8081               | ETL (профиль `etl`)                     |
| prometheus* | 9090               | Сбор метрик (профиль `observability`)   |
| grafana*    | 3001               | Дашборды метрик (профиль `observability`) |

\* — опционально, поднимается только с соответствующим профилем.

---

## 📈 Observability

Метрики собираются на бэкенде (`prometheus_fastapi_instrumentator` + кастомные
`prototip_*`) и доступны двумя способами:

1. **Внутри приложения** — раздел **«Мониторинг»** в админке (нативная страница на
   `recharts`): RPS, латентность LLM (avg/p95/p99), error-rate, расход токенов и
   разбивка по агентам. Источник — маршрут `GET /api/v1/admin/metrics`
   (живые агрегаты из ClickHouse `system_audit_logs`).
2. **Grafana + Prometheus** (профиль `observability`):
   ```bash
   docker compose --profile observability up -d
   # Grafana    → http://localhost:3001  (admin/admin, см. GRAFANA_* в .env)
   # Prometheus → http://localhost:9090
   ```
   Преднастроенный дашборд **«Prototip BI — Observability»** грузится автоматически
   (provisioning из `ops/grafana/`). Scrape-конфиг — `ops/prometheus/prometheus.yml`.

**Кастомные бизнес-метрики бэкенда:**

| Метрика                                      | Тип        | Где собирается                |
|----------------------------------------------|------------|-------------------------------|
| `prototip_llm_call_duration_seconds`         | Histogram  | `core/llm.py`                 |
| `prototip_llm_calls_total`                   | Counter    | `core/llm.py`                 |
| `prototip_llm_prompt_tokens_total`           | Counter    | `core/llm.py`                 |
| `prototip_llm_completion_tokens_total`       | Counter    | `core/llm.py`                 |
| `prototip_sql_validation_errors_total`       | Counter    | `core/sql_guard.py`           |
| `prototip_langgraph_node_duration_seconds`   | Histogram  | `app/graph.py` (узлы графа)   |

---

## 🛠 Локальная разработка (без Docker)

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev          # http://localhost:5173
```

Подробности — в `backend/README.md`, `frontend/README.md`, `db/README.md`.

---

## 📚 Документация

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — архитектура системы


## 🔐 Секреты

Ключи и токены **не коммитятся**. Для Vertex AI положите ключ в
`backend/secrets/gcp.json` (см. `backend/secrets/README.md`). Все секреты
конфигурируются через `.env` (шаблон — `.env.example`).
