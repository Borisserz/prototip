# Backend — FastAPI API + LangGraph-агенты

Серверная часть платформы. Совмещает **веб-API сайта** и **движок агентов** (LangGraph).
Сейчас они работают в одном процессе: API вызывает оркестратор агентов in-process.

## Слои

| Слой | Где | Назначение |
|------|-----|-----------|
| **Веб / API** | `app/main.py`, `app/routers/`, `app/api/`, `app/auth.py`, `app/services/` | HTTP-эндпоинты: чат, дашборды, экспорт (PDF/DOCX/XLSX), рассылки, **админка клиентов (Phase 6)** |
| **Агенты (engine)** | `app/agents/`, `app/orchestrator.py`, `app/graph.py`, `app/crew/` | LangGraph: оркестратор → агенты (SQL, аналитик, графики, дашборды, презентации, прогноз) |
| **Промпты** | `app/config/agents.yaml` | Единый YAML всех агентов (правится из админки на лету) |
| **Общие сервисы** | `core/` | LLM-адаптер, объектное хранилище (MinIO), реестр клиентов, SQL-guard, память |
| **Доменные знания** | `domain/` | Метрики, playbook графиков, примеры SQL, схема |
| **Визуализация** | `viz/` | Рендеринг графиков (PNG/HTML) |
| **Скрипты** | `scripts/` | ETL, seed ClickHouse, сборка изолированного клиента (`build_tenant.py`) |

> 🔭 **Дальнейшее развитие:** слой агентов задуман как кандидат на вынос в отдельный
> сервис `backend-llm`. Сейчас веб-слой и агенты делят общие модули
> (`app.config`, `app.utils.*`, `app.services.*`), поэтому физический split требует
> вынесения этих модулей в общий пакет — это отдельная задача с прогоном на живой
> инфраструктуре (ClickHouse/MinIO/LLM).

## Запуск

### В Docker (рекомендуется)
Поднимается из корневого `docker-compose.yml`:
```bash
docker compose up -d --build backend
```

### Локально
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

API-документация (Swagger): http://localhost:8000/docs

## Переменные окружения

См. корневой `.env.example`. Ключевые: `CLICKHOUSE_*`, `QDRANT_*`, `MINIO_*`,
`USE_VERTEX` / `OLLAMA_*` (выбор LLM), `MEMORY_*`.

## Тесты
```bash
pytest tests/
```

## Секреты
Ключ сервис-аккаунта GCP для Vertex AI: `secrets/gcp.json` (см. `secrets/README.md`).
Не коммитится.
