# ETL-оркестрация (Apache Airflow)

Автоматический перенос данных клиентов в ClickHouse по расписанию + кнопочная
инициализация нового заказчика из админки.

## Что делает

Один DAG-таск (`run_tenant_etl_task`) выполняет полный конвейер клиента:

1. **EXTRACT** — read-only выборка схемы и данных из Postgres заказчика.
2. **LOAD** — DDL + INSERT в персональный ClickHouse клиента (БД `tenant_<id>`), full-refresh.
3. **SEMANTIC** — генерация семантических векторов колонок (понимание БД для LLM)
   в личную коллекцию `semantics_<id>`.
4. **DOCS** — индексация документации клиента (PDF/DOCX/TXT/MD) в его RAG-коллекцию `docs_<id>`.

Логика переиспользует `scripts/build_tenant.py`, `scripts/schema_discovery.py`
через общий модуль `app/etl/tenant_pipeline.py` — тот же код работает и в
backend (inline-fallback), и в Airflow, и в CLI.

## DAG'и

| DAG | Расписание | Назначение |
|-----|-----------|------------|
| `etl_tenant_load` | вручную (trigger) | Кнопка из админки. Принимает `conf={"client_id": "...", "tables": [...], "row_limit": N}` |
| `etl_tenant_<client_id>` | `tenant.etl_schedule` (cron) | По одному на каждого клиента с `etl_enabled=true` |

Надёжность: `retries=2`, экспоненциальный backoff, `execution_timeout=2h`,
`sla=1h`, `on_failure_callback` → email-алерт через `app/services/email_service.py`.

## Запуск

```bash
# 1. Задайте ОБЩИЙ ключ шифрования в .env (см. .env.example):
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
#    APP_SECRET_ENCRYPTION_KEY=<сгенерированный ключ>   # одинаковый для backend и Airflow

# 2. Поднимите профиль etl (соберёт кастомный образ Airflow):
docker compose --profile etl up -d --build

# 3. Airflow UI → http://localhost:8081  (admin / admin)
```

Сервисы профиля `etl`:
- `postgres` — метаданные Airflow (не путать с Postgres КЛИЕНТОВ — те внешние, read-only);
- `airflow-init` — одноразовая миграция БД + создание admin;
- `airflow-webserver` (порт 8081) + `airflow-scheduler` — на кастомном образе `prototip-airflow`.

## Как это работает с админкой

- **Создание клиента** (визард): шаг «Источник (PG)» — подключение read-only БД с
  проверкой соединения; галка «Запустить инициализацию сразу» → backend вызывает
  `POST /provision` → триггерит `etl_tenant_load` в Airflow (или inline, если Airflow не поднят).
- **Карточка клиента → вкладка «Данные / ETL»**: ручной запуск синхронизации,
  редактор cron-расписания (вкл/выкл), пересборка семантики, загрузка документации
  в RAG, история запусков (из Airflow REST API).

## Backend ↔ Airflow

- Backend триггерит DAG'и через **Airflow Stable REST API** (`app/services/airflow_client.py`,
  basic-auth). Если Airflow недоступен — backend выполняет тот же конвейер **inline**
  через `BackgroundTasks` (фича работает в любом окружении).
- Реестр клиентов и слепки/документы хранятся в общем volume `tenant_data`
  (`/app/data/tenants` у backend ↔ `/opt/airflow/backend/data/tenants` у Airflow).
- Backend-код смонтирован в Airflow по `/opt/airflow/backend` и добавлен в `PYTHONPATH`.

## Каталоги

```
backend/airflow/
├── Dockerfile                 # кастомный образ (apache/airflow + зависимости ETL)
├── requirements-airflow.txt   # clickhouse-connect, psycopg2, langchain, sentence-transformers, …
├── dags/
│   ├── etl_common.py          # помощники: чтение реестра, run_tenant_etl_task, alert_on_failure
│   └── etl_tenant_load.py     # фабрика DAG'ов (ручной + per-tenant по расписанию)
├── logs/                      # логи задач (volume)
└── plugins/                   # плагины Airflow (volume)
```
