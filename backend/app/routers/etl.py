"""Phase 9 — admin-роутер ETL-оркестрации (кнопочная инициализация клиента).

Эндпоинты (все под /api/v1/admin/tenants/{client_id}/...):
  • POST  /etl/test-connection  — проверить read-only доступ к Postgres клиента
  • POST  /provision            — «инициализировать инстанс» одной кнопкой:
                                  сохранить PG-подключение → запустить полный ETL
                                  (extract→load→семантика→документы)
  • POST  /etl/run              — запустить синхронизацию (Airflow, иначе inline)
  • GET   /etl/runs             — статус последних запусков
  • GET   /etl/status           — текущий статус ETL клиента (из реестра)
  • PATCH /etl/schedule         — расписание (cron) + вкл/выкл автосинхронизации
  • POST  /semantics            — пересобрать только семантический слой
  • POST  /docs                 — загрузить документацию клиента в его RAG
  • GET   /docs                 — список документов в RAG клиента

Если Airflow не поднят (профиль etl выключен) — запуск идёт inline через
BackgroundTasks, поэтому фича работает в любом окружении.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Body, File, HTTPException, UploadFile
from pydantic import BaseModel

logger = logging.getLogger("routers.etl")

router = APIRouter(prefix="/api/v1/admin/tenants", tags=["etl"])
# Отдельный роутер для проверки подключения ДО создания клиента (без client_id).
probe_router = APIRouter(prefix="/api/v1/admin/etl", tags=["etl"])

# Каталог слепков/документов клиента (общий volume tenant_data, виден Airflow).
TENANTS_DATA_DIR = Path(os.getenv("TENANTS_DATA_DIR", "data/tenants"))


# ─── Pydantic-модели ───────────────────────────────────────────────────────────
class PgConnRequest(BaseModel):
    pg_dsn: str
    pg_schema: str = "public"


class ProvisionRequest(BaseModel):
    """Инициализация инстанса клиента одной кнопкой."""

    pg_dsn: str | None = None         # read-only DSN Postgres клиента (если ещё не сохранён)
    pg_schema: str = "public"
    tables: list[str] | None = None   # пусто = все таблицы схемы
    row_limit: int | None = None
    run_async: bool = True            # выполнять в фоне (не блокировать ответ)


class ScheduleRequest(BaseModel):
    etl_schedule: str | None = None   # cron, напр. "0 3 * * *"
    etl_enabled: bool | None = None


@probe_router.post("/test-connection")
def probe_connection(payload: PgConnRequest):
    """Проверяет read-only доступ к Postgres ещё до создания клиента (для визарда)."""
    from app.etl.tenant_pipeline import test_pg_connection

    res = test_pg_connection(payload.pg_dsn, payload.pg_schema)
    if not res["ok"]:
        raise HTTPException(400, f"Не удалось подключиться: {res['error']}")
    return {"ok": True, "tables": res["tables"], "count": len(res["tables"])}


# ─── helpers ─────────────────────────────────────────────────────────────────
def _get_tenant_or_404(client_id: str):
    from core.tenant import tenant_store

    t = tenant_store.get_tenant(client_id)
    if not t:
        raise HTTPException(404, "Клиент не найден")
    return t


def _decrypt_ch_password(tenant) -> str:
    from app.security import decrypt_data

    return decrypt_data(tenant.clickhouse.password_enc) if tenant.clickhouse.password_enc else ""


def _run_inline_etl(client_id: str) -> None:
    """Полный ETL клиента в текущем процессе (fallback без Airflow)."""
    from app.etl.tenant_pipeline import ingest_tenant_docs, run_tenant_etl
    from core.tenant import tenant_store

    tenant = tenant_store.get_tenant(client_id)
    if not tenant:
        logger.error("inline ETL: клиент %s не найден", client_id)
        return
    pg_dsn = tenant_store.get_pg_dsn(tenant)
    if not pg_dsn:
        tenant_store.set_etl_status(client_id, "failed", "Не настроено подключение к Postgres")
        return

    tenant_store.set_etl_status(client_id, "running", "ETL запущен (inline)")
    ch_password = _decrypt_ch_password(tenant)
    ch_db = tenant.clickhouse.database or f"tenant_{client_id}"
    result = run_tenant_etl(
        client_id=client_id,
        pg_dsn=pg_dsn,
        pg_schema=tenant.pg_schema or "public",
        tables=tenant.allowed_tables or None,
        ch_host=tenant.clickhouse.host or os.getenv("CLICKHOUSE_HOST", "clickhouse"),
        ch_port=tenant.clickhouse.port or int(os.getenv("CLICKHOUSE_PORT", "8123")),
        ch_database=ch_db,
        ch_password=ch_password,
        add_client_id=bool(tenant.enforce_client_id),
        vector_collection=tenant.vector_collection or f"semantics_{client_id}",
    )
    # документация клиента (если положена в общий каталог)
    docs_dir = TENANTS_DATA_DIR / client_id / "docs"
    if docs_dir.is_dir():
        try:
            n = ingest_tenant_docs(
                client_id=client_id,
                docs_dir=str(docs_dir),
                ch_host=tenant.clickhouse.host or os.getenv("CLICKHOUSE_HOST", "clickhouse"),
                ch_port=tenant.clickhouse.port or int(os.getenv("CLICKHOUSE_PORT", "8123")),
                ch_password=ch_password,
                ch_database=ch_db,
                collection=tenant.docs_collection or f"docs_{client_id}",
            )
            result.docs_indexed = n
        except Exception as e:  # noqa: BLE001
            logger.warning("inline docs ingest %s: %s", client_id, e)

    status = "success" if result.status == "success" else "failed"
    tenant_store.set_etl_status(client_id, status, result.message or result.error)
    if status == "failed":
        _alert_failure(client_id, result.error or result.message)


def _alert_failure(client_id: str, error: str) -> None:
    try:
        from app.services.email_service import send_report_email

        send_report_email(
            os.getenv("ETL_ALERT_EMAIL", "admin@prototip.local"),
            f"[Prototip ETL] Сбой синхронизации клиента «{client_id}»",
            f"Inline ETL клиента {client_id} завершился ошибкой:\n\n{error}",
        )
    except Exception as e:  # noqa: BLE001
        logger.error("alert email failed: %s", e)


def _start_etl(client_id: str, background: BackgroundTasks, conf: dict | None = None) -> dict:
    """Пытается запустить через Airflow; при недоступности — inline в фоне."""
    from app.services import airflow_client

    try:
        if airflow_client.is_available():
            run = airflow_client.trigger_etl(client_id, conf=conf)
            from core.tenant import tenant_store

            tenant_store.set_etl_status(client_id, "running", "ETL поставлен в очередь (Airflow)")
            return {
                "mode": "airflow",
                "dag_run_id": run.get("dag_run_id"),
                "state": run.get("state"),
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("Airflow trigger недоступен (%s) — fallback inline", e)

    background.add_task(_run_inline_etl, client_id)
    return {"mode": "inline", "dag_run_id": None, "state": "queued"}


# ─── эндпоинты ───────────────────────────────────────────────────────────────
@router.post("/{client_id}/etl/test-connection")
def test_connection(client_id: str, payload: PgConnRequest):
    """Проверяет read-only доступ к Postgres клиента и возвращает список таблиц."""
    from app.etl.tenant_pipeline import test_pg_connection

    _get_tenant_or_404(client_id)
    res = test_pg_connection(payload.pg_dsn, payload.pg_schema)
    if not res["ok"]:
        raise HTTPException(400, f"Не удалось подключиться: {res['error']}")
    return {"ok": True, "tables": res["tables"], "count": len(res["tables"])}


@router.post("/{client_id}/provision")
def provision(client_id: str, payload: ProvisionRequest, background: BackgroundTasks):
    """Инициализация инстанса клиента одной кнопкой.

    1. Сохраняет/обновляет подключение к Postgres клиента (если передано).
    2. Запускает полный ETL (extract→load→семантика→документы).
    """
    from core.tenant import tenant_store

    tenant = _get_tenant_or_404(client_id)

    fields: dict = {}
    if payload.pg_dsn:
        fields["pg_dsn"] = payload.pg_dsn
    if payload.pg_schema:
        fields["pg_schema"] = payload.pg_schema
    if payload.tables is not None:
        fields["allowed_tables"] = payload.tables
    if fields:
        tenant_store.update_tenant(client_id, **fields)

    tenant = tenant_store.get_tenant(client_id)
    if not tenant_store.get_pg_dsn(tenant):
        raise HTTPException(400, "Не задан pg_dsn — подключение к Postgres клиента обязательно")

    conf = {}
    if payload.tables:
        conf["tables"] = payload.tables
    if payload.row_limit:
        conf["row_limit"] = payload.row_limit

    started = _start_etl(client_id, background, conf=conf or None)
    return {"status": "started", "client_id": client_id, **started}


@router.post("/{client_id}/etl/run")
def run_etl(client_id: str, background: BackgroundTasks, payload: dict = Body(default={})):
    """Запускает синхронизацию данных клиента (Airflow или inline)."""
    tenant = _get_tenant_or_404(client_id)
    from core.tenant import tenant_store

    if not tenant_store.get_pg_dsn(tenant):
        raise HTTPException(400, "Не настроено подключение к Postgres клиента")
    conf = {k: v for k, v in (payload or {}).items() if k in ("tables", "row_limit")}
    started = _start_etl(client_id, background, conf=conf or None)
    return {"status": "started", "client_id": client_id, **started}


@router.get("/{client_id}/etl/status")
def etl_status(client_id: str):
    """Текущий статус ETL клиента из реестра (быстро, без обращения к Airflow)."""
    t = _get_tenant_or_404(client_id)
    return {
        "client_id": client_id,
        "status": t.last_etl_status or "idle",
        "last_run_at": t.last_etl_at,
        "message": t.last_etl_message,
        "etl_enabled": t.etl_enabled,
        "etl_schedule": t.etl_schedule,
        "pg_configured": bool(t.pg_dsn_enc),
    }


@router.get("/{client_id}/etl/runs")
def etl_runs(client_id: str, limit: int = 10):
    """Последние запуски ETL (из Airflow, иначе — статус из реестра)."""
    t = _get_tenant_or_404(client_id)
    from app.services import airflow_client

    try:
        if airflow_client.is_available():
            runs = airflow_client.list_runs(client_id, limit=limit)
            return {"source": "airflow", "runs": runs}
    except Exception as e:  # noqa: BLE001
        logger.debug("etl_runs airflow err: %s", e)
    # fallback — единичный «псевдо-запуск» из реестра
    return {
        "source": "registry",
        "runs": [
            {
                "dag_run_id": "inline",
                "state": t.last_etl_status or "idle",
                "execution_date": t.last_etl_at,
                "note": t.last_etl_message,
            }
        ] if t.last_etl_at else [],
    }


@router.patch("/{client_id}/etl/schedule")
def set_schedule(client_id: str, payload: ScheduleRequest):
    """Настраивает cron-расписание и вкл/выкл автосинхронизации."""
    from core.tenant import tenant_store

    _get_tenant_or_404(client_id)
    fields: dict = {}
    if payload.etl_schedule is not None:
        fields["etl_schedule"] = payload.etl_schedule
    if payload.etl_enabled is not None:
        fields["etl_enabled"] = payload.etl_enabled
    if not fields:
        raise HTTPException(400, "Нет полей для обновления")
    t = tenant_store.update_tenant(client_id, **fields)

    # пытаемся синхронизировать паузу per-tenant DAG в Airflow
    airflow_synced = False
    if payload.etl_enabled is not None:
        try:
            from app.services import airflow_client

            if airflow_client.is_available():
                airflow_client.set_schedule(client_id, paused=not payload.etl_enabled)
                airflow_synced = True
        except Exception as e:  # noqa: BLE001
            logger.debug("set_schedule airflow err: %s", e)

    return {
        "client_id": client_id,
        "etl_schedule": t.etl_schedule,
        "etl_enabled": t.etl_enabled,
        "airflow_synced": airflow_synced,
        "note": (
            "DAG появится/обновится после следующего парсинга расписания Airflow (~30с)"
            if not airflow_synced else "Синхронизировано с Airflow"
        ),
    }


@router.post("/{client_id}/semantics")
def rebuild_semantics(client_id: str, background: BackgroundTasks):
    """Пересобирает только семантический слой клиента (по его данным/схеме)."""
    tenant = _get_tenant_or_404(client_id)
    from core.tenant import tenant_store

    if not tenant_store.get_pg_dsn(tenant):
        raise HTTPException(400, "Не настроено подключение к Postgres клиента")

    def _job():
        from app.etl.tenant_pipeline import run_tenant_etl

        t = tenant_store.get_tenant(client_id)
        tenant_store.set_etl_status(client_id, "running", "Пересборка семантики")
        res = run_tenant_etl(
            client_id=client_id,
            pg_dsn=tenant_store.get_pg_dsn(t),
            pg_schema=t.pg_schema or "public",
            tables=t.allowed_tables or None,
            ch_host=t.clickhouse.host or os.getenv("CLICKHOUSE_HOST", "clickhouse"),
            ch_port=t.clickhouse.port or int(os.getenv("CLICKHOUSE_PORT", "8123")),
            ch_database=t.clickhouse.database or f"tenant_{client_id}",
            ch_password=_decrypt_ch_password(t),
            add_client_id=bool(t.enforce_client_id),
            vector_collection=t.vector_collection or f"semantics_{client_id}",
        )
        tenant_store.set_etl_status(
            client_id,
            "success" if res.status == "success" else "failed",
            res.message or res.error,
        )

    background.add_task(_job)
    return {"status": "started", "client_id": client_id, "task": "semantics"}


@router.post("/{client_id}/docs")
async def upload_docs(client_id: str, background: BackgroundTasks, file: UploadFile = File(...)):
    """Загружает документ клиента и индексирует его в персональный RAG клиента."""
    tenant = _get_tenant_or_404(client_id)
    docs_dir = TENANTS_DATA_DIR / client_id / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    dest = docs_dir / os.path.basename(file.filename or "document")
    content = await file.read()
    dest.write_bytes(content)

    def _ingest():
        from app.etl.tenant_pipeline import ingest_tenant_docs
        from core.tenant import tenant_store

        try:
            n = ingest_tenant_docs(
                client_id=client_id,
                file_paths=[str(dest)],
                ch_host=tenant.clickhouse.host or os.getenv("CLICKHOUSE_HOST", "clickhouse"),
                ch_port=tenant.clickhouse.port or int(os.getenv("CLICKHOUSE_PORT", "8123")),
                ch_password=_decrypt_ch_password(tenant),
                ch_database=tenant.clickhouse.database or f"tenant_{client_id}",
                collection=tenant.docs_collection or f"docs_{client_id}",
            )
            logger.info("docs ingest %s: %s чанков из %s", client_id, n, dest.name)
            tenant_store.get_tenant(client_id)  # noop, держим импорт согласованным
        except Exception as e:  # noqa: BLE001
            logger.error("docs ingest %s failed: %s", client_id, e)

    background.add_task(_ingest)
    return {
        "status": "uploaded",
        "client_id": client_id,
        "filename": dest.name,
        "size": len(content),
        "note": "Файл индексируется в RAG в фоне",
    }


@router.get("/{client_id}/docs")
def list_docs(client_id: str):
    """Список документов в персональном RAG клиента (агрегировано по source)."""
    tenant = _get_tenant_or_404(client_id)
    collection = tenant.docs_collection or f"docs_{client_id}"
    try:
        import clickhouse_connect

        ch = clickhouse_connect.get_client(
            host=tenant.clickhouse.host or os.getenv("CLICKHOUSE_HOST", "clickhouse"),
            port=tenant.clickhouse.port or int(os.getenv("CLICKHOUSE_PORT", "8123")),
            username="default",
            password=_decrypt_ch_password(tenant),
            database=tenant.clickhouse.database or f"tenant_{client_id}",
        )
        exists = ch.command(f"EXISTS TABLE {collection}")
        if not exists:
            return {"documents": [], "collection": collection}
        rows = ch.query(
            f"SELECT source, count() AS chunks FROM {collection} GROUP BY source ORDER BY source"
        ).result_rows
        return {
            "collection": collection,
            "documents": [{"source": r[0], "chunks": int(r[1])} for r in rows],
        }
    except Exception as e:  # noqa: BLE001
        logger.warning("list_docs %s: %s", client_id, e)
        return {"documents": [], "collection": collection, "error": str(e)}
