"""— тонкий клиент Airflow Stable REST API.

Backend дёргает Airflow, чтобы:
  • запустить ETL клиента по кнопке (trigger DAG ``etl_tenant_load`` с conf);
  • показать статус последних запусков в админке;
  • включить/выключить и (пере)настроить расписание per-tenant DAG'а.

Если Airflow недоступен (профиль etl не поднят), вызывающий код использует
inline-fallback (см. app/routers/etl.py) — фича работает и без Airflow.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import requests

logger = logging.getLogger("airflow_client")

API_URL = os.getenv("AIRFLOW_API_URL", "http://airflow-webserver:8080/api/v1").rstrip("/")
AUTH = (
    os.getenv("AIRFLOW_USERNAME", "admin"),
    os.getenv("AIRFLOW_PASSWORD", "admin"),
)
TIMEOUT = float(os.getenv("AIRFLOW_API_TIMEOUT", "8"))

MANUAL_DAG_ID = "etl_tenant_load"


class AirflowUnavailable(RuntimeError):
    """Airflow REST API недоступен (профиль etl не запущен или сеть)."""


def _req(method: str, path: str, **kw) -> Any:
    url = f"{API_URL}{path}"
    try:
        resp = requests.request(method, url, auth=AUTH, timeout=TIMEOUT, **kw)
    except requests.RequestException as e:
        raise AirflowUnavailable(str(e)) from e
    if resp.status_code >= 400:
        raise RuntimeError(f"Airflow API {resp.status_code}: {resp.text[:300]}")
    if resp.text:
        return resp.json()
    return {}


def is_available() -> bool:
    """Быстрая проверка доступности Airflow (health-маршрут)."""
    try:
        base = API_URL.rsplit("/api/", 1)[0]
        resp = requests.get(f"{base}/health", auth=AUTH, timeout=TIMEOUT)
        return resp.status_code == 200
    except requests.RequestException:
        return False


def trigger_etl(client_id: str, conf: dict[str, Any] | None = None) -> dict[str, Any]:
    """Запускает ручной DAG etl_tenant_load с conf={'client_id': ...}."""
    payload = {"conf": {"client_id": client_id, **(conf or {})}}
    return _req("POST", f"/dags/{MANUAL_DAG_ID}/dagRuns", json=payload)


def list_runs(client_id: str, limit: int = 10) -> list[dict[str, Any]]:
    """Возвращает последние запуски ETL клиента (ручной DAG + per-tenant DAG).

    Для ручного DAG фильтруем по conf.client_id на стороне backend.
    """
    runs: list[dict[str, Any]] = []
    # 1) per-tenant DAG (по расписанию)
    try:
        data = _req(
            "GET",
            f"/dags/etl_tenant_{client_id}/dagRuns",
            params={"limit": limit, "order_by": "-execution_date"},
        )
        runs.extend(data.get("dag_runs", []))
    except RuntimeError:
        pass  # DAG может ещё не существовать
    # 2) ручной DAG — фильтр по conf.client_id
    try:
        data = _req(
            "GET",
            f"/dags/{MANUAL_DAG_ID}/dagRuns",
            params={"limit": 50, "order_by": "-execution_date"},
        )
        for r in data.get("dag_runs", []):
            if (r.get("conf") or {}).get("client_id") == client_id:
                runs.append(r)
    except RuntimeError:
        pass
    runs.sort(key=lambda r: r.get("execution_date") or "", reverse=True)
    return runs[:limit]


def set_schedule(client_id: str, paused: bool) -> dict[str, Any]:
    """Ставит на паузу/снимает с паузы per-tenant DAG (вкл/выкл расписания)."""
    return _req("PATCH", f"/dags/etl_tenant_{client_id}", json={"is_paused": paused})
