# Prototip BI — AI-аналитическая платформа

Мультиагентная BI-платформа: пользователь задаёт вопрос на естественном языке —
система генерирует SQL, считает аналитику, строит графики, дашборды, презентации и
отчёты. Под капотом — оркестратор на **LangGraph**, аналитическое хранилище
**ClickHouse**, семантический слой на **Qdrant/Chroma** и веб-интерфейс на **React**.

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
├── docs/         # ARCHITECTURE.md, ROADMAP.md
├── docker-compose.yml             # оркестрация всего стека
└── docker-compose.tenant.template.yml  # шаблон изолированного клиента (Phase 6)
```

Каждая папка-сервис (`frontend`, `backend`, `db`) имеет свой **Dockerfile** и может
быть собрана/поднята как отдельно, так и вместе через корневой `docker-compose.yml`.

---

## 🚀 Быстрый старт

```bash
# 1. Конфигурация
cp .env.example .env          # при необходимости отредактируйте

# 2. Поднять весь стек (frontend + backend + ClickHouse + Qdrant + MinIO + Ollama)
docker compose up -d --build

# 3. Открыть
#    Frontend:        http://localhost:3000
#    Backend (API):   http://localhost:8000/docs
#    MinIO консоль:   http://localhost:9101
```

### Запуск отдельных частей

```bash
docker compose up -d clickhouse qdrant minio   # только базы/хранилища
docker compose up -d backend                   # только бэкенд
docker compose up -d frontend                  # только фронтенд
```

### Опциональные профили

```bash
docker compose --profile auth up -d    # Keycloak (внешняя аутентификация)
docker compose --profile etl  up -d    # Postgres + Airflow (ETL-пайплайны)
```

---

## 🧩 Сервисы и порты

| Сервис      | Порт (хост)        | Назначение                              |
|-------------|--------------------|-----------------------------------------|
| frontend    | 3000               | Веб-интерфейс (nginx)                   |
| backend     | 8000               | FastAPI API + Swagger `/docs`           |
| clickhouse  | 8123 / 9000        | Аналитическое хранилище                 |
| qdrant      | 6333 / 6334        | Векторное хранилище (семантика/RAG)     |
| minio       | 9100 (S3) / 9101   | Объектное хранилище артефактов          |
| ollama      | 11434              | Локальный LLM (по умолчанию)            |
| keycloak*   | 8080               | Аутентификация (профиль `auth`)         |
| airflow*    | 8081               | ETL (профиль `etl`)                     |

\* — опционально, поднимается только с соответствующим профилем.

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
- [`docs/ROADMAP.md`](docs/ROADMAP.md) — план развития (фазы)

## 🔐 Секреты

Ключи и токены **не коммитятся**. Для Vertex AI положите ключ в
`backend/secrets/gcp.json` (см. `backend/secrets/README.md`). Все секреты
конфигурируются через `.env` (шаблон — `.env.example`).
