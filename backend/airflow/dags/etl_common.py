"""Phase 9 — общие помощники Airflow-DAG'ов ETL.

Здесь только лёгкие функции (чтение реестра на этапе парсинга DAG'ов) и
тяжёлые операции, которые ВЫЗЫВАЮТСЯ ВНУТРИ ЗАДАЧ (импорт backend-кода —
``app.etl``, ``core.tenant`` — отложен в тело функций, чтобы парсинг DAG'ов
оставался быстрым и не падал при отсутствии тяжёлых зависимостей).

Backend смонтирован в контейнер Airflow по пути ``/opt/airflow/backend`` и
добавлен в PYTHONPATH (см. backend/airflow/Dockerfile + docker-compose etl).
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger("airflow.etl_common")

# Корень backend внутри контейнера Airflow (монтируется из ./backend).
BACKEND_ROOT = Path(os.getenv("BACKEND_ROOT", "/opt/airflow/backend"))
REGISTRY_PATH = Path(
    os.getenv("TENANT_REGISTRY_PATH", str(BACKEND_ROOT / "data" / "tenants" / "registry.json"))
)

# ClickHouse по умолчанию (общий инстанс стека). Можно переопределить env'ом.
DEFAULT_CH_HOST = os.getenv("CLICKHOUSE_HOST", "clickhouse")
DEFAULT_CH_PORT = int(os.getenv("CLICKHOUSE_PORT", "8123"))
ALERT_EMAIL = os.getenv("ETL_ALERT_EMAIL", os.getenv("ADMIN_EMAIL", "admin@prototip.local"))


def load_tenants() -> list[dict[str, Any]]:
    """Лёгкое чтение реестра тенантов (для генерации DAG'ов по расписанию).

    Никаких тяжёлых импортов и расшифровки — только сырой JSON.
    """
    try:
        if REGISTRY_PATH.exists():
            raw = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
            return raw.get("tenants", [])
    except Exception as e:  # noqa: BLE001
        logger.warning("etl_common.load_tenants: не удалось прочитать реестр (%s)", e)
    return []


def _ensure_backend_on_path() -> None:
    import sys

    if str(BACKEND_ROOT) not in sys.path:
        sys.path.insert(0, str(BACKEND_ROOT))


def run_tenant_etl_task(client_id: str, **context: Any) -> dict[str, Any]:
    """Задача Airflow: полный ETL одного клиента (extract→load→семантика→docs).

    Вызывается как из per-tenant DAG (по расписанию), так и из ручного
    ``etl_tenant_load`` (триггер из админки с conf={'client_id': ...}).
    """
    # client_id может прийти из dag_run.conf (ручной триггер)
    conf = (context.get("dag_run").conf or {}) if context.get("dag_run") else {}
    client_id = conf.get("client_id") or client_id
    if not client_id:
        raise ValueError("client_id не задан (ни в DAG, ни в dag_run.conf)")

    _ensure_backend_on_path()
    os.environ.setdefault("TENANT_REGISTRY_PATH", str(REGISTRY_PATH))

    from app.etl.tenant_pipeline import ingest_tenant_docs, run_tenant_etl
    from app.security import decrypt_data
    from core.tenant import tenant_store

    tenant = tenant_store.get_tenant(client_id)
    if not tenant:
        raise ValueError(f"Клиент '{client_id}' не найден в реестре")

    pg_dsn = tenant_store.get_pg_dsn(tenant)
    if not pg_dsn:
        raise ValueError(
            f"У клиента '{client_id}' не настроено подключение к Postgres (pg_dsn пуст)"
        )

    ch_password = decrypt_data(tenant.clickhouse.password_enc) if tenant.clickhouse.password_enc else ""
    ch_host = tenant.clickhouse.host or DEFAULT_CH_HOST
    ch_port = tenant.clickhouse.port or DEFAULT_CH_PORT

    tenant_store.set_etl_status(client_id, "running", "ETL запущен (Airflow)")

    # conf может переопределить список таблиц / лимит строк для ручного запуска
    tables = conf.get("tables") or tenant.allowed_tables or None
    row_limit = conf.get("row_limit")

    result = run_tenant_etl(
        client_id=client_id,
        pg_dsn=pg_dsn,
        pg_schema=tenant.pg_schema or "public",
        tables=tables,
        ch_host=ch_host,
        ch_port=ch_port,
        ch_database=tenant.clickhouse.database or f"tenant_{client_id}",
        ch_password=ch_password,
        add_client_id=bool(tenant.enforce_client_id),
        vector_collection=tenant.vector_collection or f"semantics_{client_id}",
        row_limit=row_limit,
    )

    # Документация клиента (если положена в общий volume backend/data/tenants/<id>/docs)
    docs_dir = BACKEND_ROOT / "data" / "tenants" / client_id / "docs"
    if docs_dir.is_dir():
        try:
            n = ingest_tenant_docs(
                client_id=client_id,
                docs_dir=str(docs_dir),
                ch_host=ch_host,
                ch_port=ch_port,
                ch_password=ch_password,
                ch_database=tenant.clickhouse.database or f"tenant_{client_id}",
                collection=tenant.docs_collection or f"docs_{client_id}",
            )
            result.docs_indexed = n
        except Exception as e:  # noqa: BLE001
            logger.warning("ingest_tenant_docs(%s): %s", client_id, e)

    if result.status != "success":
        tenant_store.set_etl_status(client_id, "failed", result.message or result.error)
        raise RuntimeError(result.error or "ETL завершился со статусом failed")

    tenant_store.set_etl_status(client_id, "success", result.message)
    logger.info("ETL клиента %s: %s", client_id, result.message)
    return result.as_dict()


def alert_on_failure(context: dict[str, Any]) -> None:
    """on_failure_callback: уведомление об аварии ETL через email_service.

    Telegram запрещён — используется только корпоративная почта (как в проекте).
    """
    _ensure_backend_on_path()
    try:
        from app.services.email_service import send_report_email
    except Exception as e:  # noqa: BLE001
        logger.error("alert_on_failure: email_service недоступен (%s)", e)
        return

    dag_id = context.get("dag").dag_id if context.get("dag") else "etl"
    task_id = context.get("task_instance").task_id if context.get("task_instance") else "?"
    exec_date = str(context.get("logical_date") or context.get("execution_date") or "")
    exc = context.get("exception")
    conf = (context.get("dag_run").conf or {}) if context.get("dag_run") else {}
    client_id = conf.get("client_id") or dag_id.replace("etl_tenant_", "")

    subject = f"[Prototip ETL] Сбой синхронизации клиента «{client_id}»"
    body = (
        f"DAG: {dag_id}\n"
        f"Задача: {task_id}\n"
        f"Клиент: {client_id}\n"
        f"Время запуска: {exec_date}\n"
        f"Ошибка: {exc}\n\n"
        "Проверьте подключение к Postgres клиента и доступность ClickHouse. "
        "Подробности — в Airflow UI (логи задачи)."
    )
    try:
        send_report_email(ALERT_EMAIL, subject, body)
        logger.info("alert_on_failure: уведомление отправлено на %s", ALERT_EMAIL)
        # помечаем статус клиента как failed
        try:
            from core.tenant import tenant_store

            tenant_store.set_etl_status(client_id, "failed", str(exc) if exc else "ETL failed")
        except Exception:  # noqa: BLE001
            pass
    except Exception as e:  # noqa: BLE001
        logger.error("alert_on_failure: ошибка отправки email (%s)", e)
