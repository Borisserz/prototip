"""Phase 9 — DAG'и ETL-оркестрации (Apache Airflow).

Создаёт ДВА вида DAG'ов:

1. ``etl_tenant_load`` — РУЧНОЙ параметризованный DAG. Запускается из админки
   (кнопка «Запустить синхронизацию» / «Инициализировать инстанс») через
   Airflow REST API с conf ``{"client_id": "...", "tables": [...]}``.
   Schedule = None (только по триггеру).

2. ``etl_tenant_<client_id>`` — по одному DAG на КАЖДОГО клиента из реестра,
   с его собственным cron-расписанием (``tenant.etl_schedule``). Включается,
   только если у клиента ``etl_enabled = true`` и настроено подключение Postgres.

Все DAG'и переиспользуют один task-колбэк ``run_tenant_etl_task`` (→ app.etl),
который делает: extract из Postgres клиента → load в ClickHouse → генерация
семантики → загрузка документации в RAG. Надёжность: retries, retry_delay,
SLA и on_failure_callback (email-алерт через app/services/email_service.py).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from airflow import DAG
from airflow.models.param import Param
from airflow.operators.python import PythonOperator

from etl_common import alert_on_failure, load_tenants, run_tenant_etl_task

# ─── базовые параметры надёжности для всех ETL-задач ───────────────────────────
DEFAULT_ARGS = {
    "owner": "prototip",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "retry_exponential_backoff": True,
    "max_retry_delay": timedelta(minutes=30),
    "execution_timeout": timedelta(hours=2),
    "on_failure_callback": alert_on_failure,
    "email_on_failure": False,  # уведомление шлём сами через email_service
}

TAGS = ["etl", "multitenant", "phase9"]


def _build_etl_dag(
    dag_id: str,
    schedule,
    client_id: str = "",
    *,
    is_manual: bool = False,
) -> DAG:
    """Фабрика DAG'а ETL для одного клиента (или ручного запуска по conf)."""
    params = {}
    doc_md = __doc__
    if is_manual:
        params = {
            "client_id": Param(
                "", type="string",
                description="client_id клиента, для которого запустить ETL",
            ),
            "tables": Param(
                [], type=["null", "array"],
                description="Список таблиц (пусто = все из allowed_tables/схемы)",
            ),
            "row_limit": Param(
                None, type=["null", "integer"],
                description="Лимит строк на таблицу (для тест-прогона)",
            ),
        }

    with DAG(
        dag_id=dag_id,
        description=(
            "Ручной ETL клиента (триггер из админки)" if is_manual
            else f"ETL по расписанию для клиента «{client_id}»"
        ),
        default_args=DEFAULT_ARGS,
        schedule=schedule,
        start_date=datetime(2024, 1, 1),
        catchup=False,
        max_active_runs=1,
        tags=TAGS + ([client_id] if client_id else ["manual"]),
        params=params,
        doc_md=doc_md,
        is_paused_upon_creation=False,
    ) as dag:
        PythonOperator(
            task_id="etl_tenant_load",
            python_callable=run_tenant_etl_task,
            op_kwargs={"client_id": client_id},
            sla=timedelta(hours=1),
            doc_md=(
                "extract (Postgres RO) → load (ClickHouse) → семантика (векторы) "
                "→ документация (RAG). Идемпотентно, full-refresh."
            ),
        )
    return dag


# ─── 1. Ручной параметризованный DAG (кнопка в админке) ────────────────────────
globals()["etl_tenant_load"] = _build_etl_dag(
    dag_id="etl_tenant_load",
    schedule=None,
    client_id="",
    is_manual=True,
)

# ─── 2. По DAG на каждого клиента с включённым расписанием ─────────────────────
for _t in load_tenants():
    _cid = _t.get("client_id")
    if not _cid:
        continue
    # генерируем расписанный DAG только если клиент включил автосинхронизацию
    if not _t.get("etl_enabled"):
        continue
    _schedule = _t.get("etl_schedule") or "0 3 * * *"
    _dag_id = f"etl_tenant_{_cid}"
    globals()[_dag_id] = _build_etl_dag(
        dag_id=_dag_id,
        schedule=_schedule,
        client_id=_cid,
        is_manual=False,
    )
