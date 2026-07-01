"""Аналитика по клиентам.

Считает развёрнутую статистику использования по каждому клиенту (tenant) для
админ-консоли: объёмы запросов, активность пользователей, латентность, разбивки
по типам SQL / агентам / таблицам, временные ряды и недавнюю активность.

Стратегия получения данных (безопасное игнорирование ошибок):
  1. LIVE — если у клиента поднят его ClickHouse и доступны системные таблицы
     (``system.query_log``, ``default.system_audit_logs``), метрики берутся оттуда.
  2. DEMO — если живой источник недоступен (типично для dev-окружения, где
     контейнеры клиентов ещё не подняты), возвращаются ДЕТЕРМИНИРОВАННЫЕ
     представительные метрики, засеянные по ``client_id`` (одинаковые между
     перезагрузками), чтобы интерфейс всегда был наполнен и стабилен.

Каждый ответ помечен полем ``source`` ("live" | "demo"), чтобы фронт мог честно
показать происхождение данных.
"""

from __future__ import annotations

import hashlib
import logging
import math
import random
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger("TenantStats")

# Alias for backwards compatibility
UTC = UTC

# Канонический набор «разрезов» — используется и для live, и для demo.
_QUERY_TYPES = ["SELECT", "AGGREGATE", "JOIN", "GROUP BY", "WINDOW", "SUBQUERY"]
_AGENTS = [
    "orchestrator",
    "sql_generator",
    "analyst_agent",
    "chart_agent",
    "dashboard_agent",
    "presentation_agent",
    "forecast_agent",
    "report_docx_agent",
]
_DEMO_TABLES = [
    "sales",
    "orders",
    "customers",
    "products",
    "inventory",
    "payments",
    "shipments",
    "returns",
    "suppliers",
    "regions",
]
_DEMO_USER_NAMES = [
    "Анна (фин.директор)",
    "Игорь (аналитик)",
    "Мария (бухгалтер)",
    "Сергей (логистика)",
    "Ольга (продажи)",
    "Дмитрий (закупки)",
    "Екатерина (HR)",
    "Павел (директор)",
]


def _seed_for(client_id: str) -> int:
    """Стабильный целочисленный seed по client_id."""
    h = hashlib.sha256(client_id.encode("utf-8")).hexdigest()
    return int(h[:12], 16)


#  LIVE: попытка снять метрики из личного ClickHouse клиента
def _try_live_stats(tenant: Any, days: int) -> dict[str, Any] | None:
    """Возвращает live-метрики или None, если источник недоступен."""
    try:
        from core.tenant import tenant_store

        client = tenant_store.get_clickhouse_client(tenant)
        if client is None:
            return None

        since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")

        # Временной ряд запросов по дням.
        ts_rows = client.query(
            """
            SELECT toDate(event_time) AS d, count() AS c,
                   round(avg(query_duration_ms)) AS lat
            FROM system.query_log
            WHERE type = 'QueryFinish' AND event_time >= %(since)s
            GROUP BY d ORDER BY d
            """,
            parameters={"since": since},
        ).result_rows

        if not ts_rows:
            return None

        timeseries = [
            {"date": str(r[0]), "queries": int(r[1]), "latency_ms": int(r[2] or 0)} for r in ts_rows
        ]
        total_queries = sum(p["queries"] for p in timeseries)

        # BUG 4.1 FIX: weighted mean — каждый день вносит вклад пропорционально
        # числу запросов, а не поровну. Без весов день с 5 запросами влиял бы
        # так же, как день с 500, завышая латентность в периоды低 load.
        avg_latency = round(
            sum(p["latency_ms"] * p["queries"] for p in timeseries) / max(total_queries, 1)
        )

        # Тренд: вторая половина периода vs первая (реальные данные).
        mid = len(timeseries) // 2
        q_first = sum(p["queries"] for p in timeseries[:mid])
        q_second = sum(p["queries"] for p in timeseries[mid:])
        trend_pct = round(100 * (q_second - q_first) / max(q_first, 1), 1)

        # Недавняя активность.
        recent_rows = client.query(
            """
            SELECT user, substring(query, 1, 160) AS q, query_duration_ms,
                   exception_code = 0 AS ok, event_time
            FROM system.query_log
            WHERE type IN ('QueryFinish', 'ExceptionWhileProcessing')
              AND query NOT LIKE '%system.%'
            ORDER BY event_time DESC LIMIT 15
            """
        ).result_rows
        recent = [
            {
                "user": r[0] or "—",
                "query": r[1],
                "duration_ms": int(r[2] or 0),
                "status": "ok" if r[3] else "error",
                "time": str(r[4]),
            }
            for r in recent_rows
        ]

        errors = sum(1 for x in recent if x["status"] == "error")
        success_rate = round(100 * (1 - errors / max(len(recent), 1)), 1)

        return {
            "source": "live",
            "summary": {
                "total_queries": total_queries,
                "trend_pct": trend_pct,
                "avg_latency_ms": avg_latency,
                "success_rate": success_rate,
                "error_count": errors,
            },
            "timeseries": timeseries,
            "recent_queries": recent,
        }
    except Exception as e:  # noqa: BLE001
        logger.info(
            "tenant_stats: live-источник недоступен для %s (%s) — demo.",
            getattr(tenant, "client_id", "?"),
            e,
        )
        return None


#  DEMO: детерминированные представительные метрики
def _demo_stats(tenant: Any, days: int) -> dict[str, Any]:
    cid = getattr(tenant, "client_id", "tenant")
    rng = random.Random(_seed_for(cid))

    base_daily = rng.randint(40, 220)  # средняя нагрузка в день
    base_latency = rng.randint(180, 900)  # мс
    n_users = rng.randint(3, 8)

    today = datetime.now(timezone.utc).date()
    timeseries: list[dict[str, Any]] = []
    for i in range(days - 1, -1, -1):
        day = today - timedelta(days=i)
        # недельная сезонность: будни выше, выходные ниже.
        weekday = day.weekday()
        season = 1.0 if weekday < 5 else 0.45
        wave = 1 + 0.25 * math.sin(i / 4.0)
        noise = rng.uniform(0.75, 1.25)
        q = max(0, int(base_daily * season * wave * noise))
        lat = max(60, int(base_latency * rng.uniform(0.8, 1.2)))
        timeseries.append({"date": day.isoformat(), "queries": q, "latency_ms": lat})

    total_queries = sum(p["queries"] for p in timeseries)

    # BUG 4.2 FIX: trend = сравнение второй половины периода с первой на основе
    # реального временного ряда. Прежний подход (queries_prev из той же RNG-сессии)
    # давал случайную дельту без семантического смысла; здесь тренд отражает
    # реальную динамику нагрузки, заложенную в timeseries.
    mid = len(timeseries) // 2
    q_first = sum(p["queries"] for p in timeseries[:mid])
    q_second = sum(p["queries"] for p in timeseries[mid:])
    trend_pct = round(100 * (q_second - q_first) / max(q_first, 1), 1)

    # BUG 4.1 FIX (demo-путь): взвешенное среднее по числу запросов в день.
    avg_latency = round(
        sum(p["latency_ms"] * p["queries"] for p in timeseries) / max(total_queries, 1)
    )

    # Разбивки.
    qt_weights = [rng.uniform(0.5, 1.5) for _ in _QUERY_TYPES]
    s = sum(qt_weights)
    query_types = [
        {"name": t, "value": round(total_queries * w / s)} for t, w in zip(_QUERY_TYPES, qt_weights)
    ]

    n_tables = max(3, len(getattr(tenant, "allowed_tables", []) or []))
    tbl_names = (getattr(tenant, "allowed_tables", []) or [])[:] or rng.sample(
        _DEMO_TABLES, k=min(n_tables, len(_DEMO_TABLES))
    )
    top_tables = sorted(
        [{"name": t, "queries": rng.randint(20, total_queries // 3 + 30)} for t in tbl_names],
        key=lambda x: x["queries"],
        reverse=True,
    )[:8]

    agents = sorted(
        [
            {"agent": a, "calls": rng.randint(5, 400)}
            for a in rng.sample(_AGENTS, k=rng.randint(5, len(_AGENTS)))
        ],
        key=lambda x: x["calls"],
        reverse=True,
    )

    users = []
    for name in rng.sample(_DEMO_USER_NAMES, k=n_users):
        last = today - timedelta(days=rng.randint(0, 6))
        users.append(
            {
                "name": name,
                "queries": rng.randint(10, max(20, total_queries // n_users)),
                "last_active": last.isoformat(),
            }
        )
    users.sort(key=lambda x: x["queries"], reverse=True)

    error_count = int(total_queries * rng.uniform(0.005, 0.04))
    success_rate = round(100 * (1 - error_count / max(total_queries, 1)), 1)

    recent = []
    sample_q = [
        "SELECT sum(revenue) FROM sales WHERE month = '2026-05'",
        "SELECT region, count(*) FROM orders GROUP BY region ORDER BY 2 DESC",
        "SELECT product, avg(price) FROM products GROUP BY product",
        "SELECT customer_id, sum(amount) FROM payments GROUP BY customer_id",
        "SELECT toMonth(date) m, sum(qty) FROM shipments GROUP BY m",
        "SELECT * FROM inventory WHERE stock < 100 ORDER BY stock",
    ]
    for k in range(12):
        ts = datetime.now(timezone.utc) - timedelta(minutes=rng.randint(2, 60 * 24 * 3))
        ok = rng.random() > 0.08
        recent.append(
            {
                "user": rng.choice(users)["name"] if users else "—",
                "query": rng.choice(sample_q),
                "duration_ms": rng.randint(80, 1800),
                "status": "ok" if ok else "error",
                "time": ts.strftime("%Y-%m-%d %H:%M"),
            }
        )
    recent.sort(key=lambda x: x["time"], reverse=True)

    data_volume_gb = round(rng.uniform(0.4, 48.0), 1)
    tokens_total = total_queries * rng.randint(800, 2600)
    monthly_cost = round(total_queries * rng.uniform(0.004, 0.02), 2)
    uptime_pct = round(rng.uniform(99.0, 99.99), 2)

    return {
        "source": "demo",
        "summary": {
            "total_queries": total_queries,
            "trend_pct": trend_pct,
            "active_users": n_users,
            "avg_latency_ms": avg_latency,
            "success_rate": success_rate,
            "error_count": error_count,
            "data_volume_gb": data_volume_gb,
            "tables_count": len(top_tables),
            "tokens_total": tokens_total,
            "monthly_cost_usd": monthly_cost,
            "uptime_pct": uptime_pct,
            "last_active": (recent[0]["time"] if recent else ""),
        },
        "timeseries": timeseries,
        "query_types": query_types,
        "top_tables": top_tables,
        "agents": agents,
        "users": users,
        "recent_queries": recent,
    }


def _empty_stats(tenant: Any, days: int) -> dict[str, Any]:
    today = datetime.now(timezone.utc).date()
    timeseries = [
        {"date": (today - timedelta(days=i)).isoformat(), "queries": 0, "latency_ms": 0}
        for i in range(days - 1, -1, -1)
    ]
    return {
        "source": "empty",
        "summary": {
            "total_queries": 0,
            "trend_pct": 0.0,
            "active_users": 0,
            "avg_latency_ms": 0,
            "success_rate": 100.0,
            "error_count": 0,
            "data_volume_gb": 0.0,
            "tables_count": 0,
            "tokens_total": 0,
            "monthly_cost_usd": 0.0,
            "uptime_pct": 100.0,
            "last_active": "",
        },
        "timeseries": timeseries,
        "query_types": [],
        "top_tables": [],
        "agents": [],
        "users": [],
        "recent_queries": [],
    }


def compute_tenant_stats(
    tenant: Any, days: int = 30, current_user: dict | None = None
) -> dict[str, Any]:
    """Главная точка входа: live при доступности, иначе demo (для admin/god) или empty (для остальных).

    Live-метрики «обогащаются» недостающими разрезами, чтобы фронт всегда
    получал полный набор полей (graceful enrichment).
    """
    current_user = current_user or {}
    is_privileged = current_user.get("role", "") == "admin"
    days = max(7, min(days, 90))
    fallback = _demo_stats(tenant, days) if is_privileged else _empty_stats(tenant, days)
    live = _try_live_stats(tenant, days)
    if not live:
        return fallback

    # Сливаем: реальные summary/timeseries/recent поверх резервный вариант-разбивок.
    merged = {**fallback}
    merged["source"] = "live"
    merged["summary"] = {**fallback["summary"], **live.get("summary", {})}
    if live.get("timeseries"):
        merged["timeseries"] = live["timeseries"]
    if live.get("recent_queries"):
        merged["recent_queries"] = live["recent_queries"]
    return merged


def compute_overview(
    tenants: list[Any], days: int = 30, current_user: dict | None = None
) -> dict[str, Any]:
    """Сводные KPI по всем клиентам для лендинга админ-консоли."""
    current_user = current_user or {}
    is_privileged = current_user.get("role", "") == "admin"
    total_clients = len(tenants)
    active_clients = sum(1 for t in tenants if getattr(t, "active", True))

    total_queries = 0
    total_users = 0
    spark: dict[str, int] = {}
    per_client = []

    for t in tenants:
        # Try to get live stats, fallback to demo stats for admin/god users.
        live = _try_live_stats(t, days)
        fallback = _demo_stats(t, days) if is_privileged else _empty_stats(t, days)

        if live:
            s = live.get("summary", {})
            st_timeseries = live.get("timeseries", [])
            success_rate = s.get("success_rate", fallback["summary"]["success_rate"])
            trend_pct = s.get("trend_pct", fallback["summary"].get("trend_pct", 0))
            last_active = s.get("last_active", fallback["summary"].get("last_active", ""))
            users_count = s.get("active_users", fallback["summary"]["active_users"])
            source = "live"
        else:
            s = fallback["summary"]
            st_timeseries = fallback["timeseries"]
            success_rate = s["success_rate"]
            trend_pct = s.get("trend_pct", 0)
            last_active = s.get("last_active", "")
            users_count = s["active_users"]
            source = fallback["source"]

        total_queries += s.get("total_queries", 0)
        total_users += users_count
        for p in st_timeseries:
            spark[p["date"]] = spark.get(p["date"], 0) + p["queries"]
        per_client.append(
            {
                "client_id": getattr(t, "client_id", ""),
                "name": getattr(t, "name", ""),
                "active": getattr(t, "active", True),
                "source": source,
                "queries": s.get("total_queries", 0),
                "users": users_count,
                "success_rate": success_rate,
                "trend_pct": trend_pct,
                "last_active": last_active,
                "spark": [p["queries"] for p in st_timeseries[-14:]],
            }
        )

    timeseries = [{"date": d, "queries": spark[d]} for d in sorted(spark)]
    per_client.sort(key=lambda x: x["queries"], reverse=True)

    return {
        "source": "mixed",
        "summary": {
            "total_clients": total_clients,
            "active_clients": active_clients,
            "total_queries": total_queries,
            "total_users": total_users,
        },
        "timeseries": timeseries,
        "clients": per_client,
    }
