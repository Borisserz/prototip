"""— переиспользуемый ETL-слой (extract PG → load ClickHouse → семантика → RAG).

Один и тот же код вызывается из:
  • Airflow-DAG  (backend/airflow/dags/etl_tenant_load.py)
  • backend API  (app/routers/etl.py — inline-fallback, когда Airflow не поднят)
  • CLI          (scripts/build_tenant.py — обёртка вокруг этого модуля)
"""

from app.etl.tenant_pipeline import (  # noqa: F401
    EtlResult,
    ingest_tenant_docs,
    run_tenant_etl,
    test_pg_connection,
)
