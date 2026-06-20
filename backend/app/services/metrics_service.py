"""Агрегация системных метрик для страницы «Мониторинг» (Phase 8).

Источник данных — таблица ``default.system_audit_logs`` (её наполняет
``app/utils/system_logger.py`` на каждый вызов LLM). Сервис считает живые
агрегаты для нативной страницы мониторинга на ``recharts`` через эндпоинт
``/api/v1/admin/metrics``.

Если таблица недоступна или пуста — возвращаются демонстрационные данные
(``source = "demo"``), чтобы интерфейс оставался наглядным до появления
реального трафика. При наличии данных — ``source = "live"``.
"""

from __future__ import annotations

import logging
import math
import random
from datetime import UTC, datetime, timedelta

from app.utils.clickhouse_client import ch_client

logger = logging.getLogger("metrics_service")

_TABLE = "default.system_audit_logs"


def _rows(query: str):
    """Выполнить запрос и вернуть список кортежей (или пустой список при ошибке)."""
    res = ch_client.execute(query)
    return list(getattr(res, "result_rows", []) or [])


def _bucket_minutes(hours: int) -> int:
    """Подобрать шаг агрегации временного ряда под размер окна."""
    if hours <= 2:
        return 5
    if hours <= 12:
        return 15
    if hours <= 48:
        return 60
    return 180


def compute_metrics(hours: int = 24) -> dict:
    """Собрать сводку системных метрик за последние ``hours`` часов."""
    hours = max(1, min(int(hours), 24 * 30))
    step = _bucket_minutes(hours)
    window = f"timestamp >= now() - INTERVAL {hours} HOUR"

    try:
        summary_rows = _rows(
            f"""
            SELECT
                count()                              AS calls,
                countIf(error_status != '')          AS errors,
                round(avg(duration_ms), 1)           AS avg_ms,
                round(quantile(0.95)(duration_ms), 0) AS p95_ms,
                round(quantile(0.99)(duration_ms), 0) AS p99_ms,
                sum(prompt_tokens)                   AS prompt_tokens,
                sum(completion_tokens)               AS completion_tokens,
                uniqExact(agent_name)                AS agents
            FROM {_TABLE}
            WHERE {window}
            """
        )
    except Exception as exc:  # таблицы ещё нет / ClickHouse недоступен
        logger.warning("metrics: summary query failed (%s) → demo", exc)
        return _demo(hours, step)

    calls = int(summary_rows[0][0]) if summary_rows else 0
    if calls == 0:
        return _demo(hours, step)

    s = summary_rows[0]
    errors = int(s[1] or 0)
    summary = {
        "total_calls": calls,
        "errors": errors,
        "error_rate": round(errors / calls * 100, 2) if calls else 0.0,
        "avg_latency_ms": float(s[2] or 0),
        "p95_latency_ms": float(s[3] or 0),
        "p99_latency_ms": float(s[4] or 0),
        "prompt_tokens": int(s[5] or 0),
        "completion_tokens": int(s[6] or 0),
        "total_tokens": int((s[5] or 0) + (s[6] or 0)),
        "active_agents": int(s[7] or 0),
        "rps": round(calls / (hours * 3600.0), 4),
        "calls_per_min": round(calls / (hours * 60.0), 2),
    }

    timeseries = []
    for r in _rows(
        f"""
        SELECT
            toStartOfInterval(timestamp, INTERVAL {step} MINUTE) AS bucket,
            count()                          AS calls,
            round(avg(duration_ms), 1)       AS avg_ms,
            countIf(error_status != '')      AS errors,
            sum(prompt_tokens + completion_tokens) AS tokens
        FROM {_TABLE}
        WHERE {window}
        GROUP BY bucket ORDER BY bucket
        """
    ):
        timeseries.append({
            "time": _iso(r[0]),
            "calls": int(r[1] or 0),
            "latency_ms": float(r[2] or 0),
            "errors": int(r[3] or 0),
            "tokens": int(r[4] or 0),
            "rpm": round((r[1] or 0) / step, 2),
        })

    by_agent = []
    for r in _rows(
        f"""
        SELECT agent_name, count() AS calls, round(avg(duration_ms), 1) AS avg_ms,
               sum(prompt_tokens) AS pt, sum(completion_tokens) AS ct,
               countIf(error_status != '') AS errors
        FROM {_TABLE} WHERE {window}
        GROUP BY agent_name ORDER BY calls DESC LIMIT 20
        """
    ):
        c = int(r[1] or 0)
        by_agent.append({
            "agent": r[0] or "unknown",
            "calls": c,
            "avg_latency_ms": float(r[2] or 0),
            "prompt_tokens": int(r[3] or 0),
            "completion_tokens": int(r[4] or 0),
            "tokens": int((r[3] or 0) + (r[4] or 0)),
            "errors": int(r[5] or 0),
            "error_rate": round((r[5] or 0) / c * 100, 2) if c else 0.0,
        })

    by_model = []
    for r in _rows(
        f"""
        SELECT model, count() AS calls,
               sum(prompt_tokens + completion_tokens) AS tokens,
               round(avg(duration_ms), 1) AS avg_ms
        FROM {_TABLE} WHERE {window}
        GROUP BY model ORDER BY calls DESC LIMIT 20
        """
    ):
        by_model.append({
            "model": r[0] or "unknown",
            "calls": int(r[1] or 0),
            "tokens": int(r[2] or 0),
            "avg_latency_ms": float(r[3] or 0),
        })

    recent_errors = []
    for r in _rows(
        f"""
        SELECT timestamp, agent_name, model, error_status
        FROM {_TABLE}
        WHERE {window} AND error_status != ''
        ORDER BY timestamp DESC LIMIT 25
        """
    ):
        recent_errors.append({
            "time": _iso(r[0]),
            "agent": r[1] or "unknown",
            "model": r[2] or "unknown",
            "error": (r[3] or "")[:300],
        })

    return {
        "source": "live",
        "window_hours": hours,
        "bucket_minutes": step,
        "generated_at": datetime.now(UTC).isoformat(),
        "summary": summary,
        "timeseries": timeseries,
        "by_agent": by_agent,
        "by_model": by_model,
        "recent_errors": recent_errors,
    }


def _iso(value) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


# ───────────────────────── Демо-данные (fallback) ──────────────────────────
def _demo(hours: int, step: int) -> dict:
    """Синтетические, но правдоподобные метрики, пока нет реального трафика."""
    rnd = random.Random(42)
    agents = ["planner", "data", "analyst", "reviewer", "presenter", "forecast", "rag"]
    models = ["qwen2.5-coder:7b-instruct", "gemini-3.5-flash"]
    now = datetime.now(UTC)

    n_buckets = max(6, min(int(hours * 60 / step), 200))
    timeseries = []
    total_calls = 0
    for i in range(n_buckets):
        t = now - timedelta(minutes=step * (n_buckets - 1 - i))
        base = 18 + 10 * math.sin(i / 6.0)
        calls = max(1, int(base + rnd.uniform(-4, 6)))
        total_calls += calls
        timeseries.append({
            "time": t.isoformat(),
            "calls": calls,
            "latency_ms": round(820 + 240 * math.sin(i / 4.0) + rnd.uniform(-80, 120), 1),
            "errors": rnd.choice([0, 0, 0, 1]),
            "tokens": calls * rnd.randint(380, 720),
            "rpm": round(calls / step, 2),
        })

    by_agent = []
    for a in agents:
        c = rnd.randint(40, 320)
        pt, ct = c * rnd.randint(180, 420), c * rnd.randint(60, 180)
        err = rnd.randint(0, max(1, c // 40))
        by_agent.append({
            "agent": a, "calls": c, "avg_latency_ms": round(rnd.uniform(600, 1600), 1),
            "prompt_tokens": pt, "completion_tokens": ct, "tokens": pt + ct,
            "errors": err, "error_rate": round(err / c * 100, 2),
        })
    by_agent.sort(key=lambda x: x["calls"], reverse=True)

    by_model = [
        {"model": models[0], "calls": int(total_calls * 0.7),
         "tokens": int(total_calls * 0.7 * 540), "avg_latency_ms": 980.0},
        {"model": models[1], "calls": int(total_calls * 0.3),
         "tokens": int(total_calls * 0.3 * 610), "avg_latency_ms": 740.0},
    ]

    errors = sum(b["errors"] for b in by_agent)
    calls = sum(b["calls"] for b in by_agent)
    prompt_tokens = sum(b["prompt_tokens"] for b in by_agent)
    completion_tokens = sum(b["completion_tokens"] for b in by_agent)

    recent_errors = [
        {"time": (now - timedelta(minutes=rnd.randint(1, hours * 60))).isoformat(),
         "agent": rnd.choice(agents), "model": rnd.choice(models),
         "error": rnd.choice([
             "Разрешены только SELECT-запросы.",
             "LLM structured call failed after 3 attempts",
             "Доступ к таблицам запрещён конфигурацией клиента",
         ])}
        for _ in range(min(8, errors or 4))
    ]

    return {
        "source": "demo",
        "window_hours": hours,
        "bucket_minutes": step,
        "generated_at": now.isoformat(),
        "summary": {
            "total_calls": calls,
            "errors": errors,
            "error_rate": round(errors / calls * 100, 2) if calls else 0.0,
            "avg_latency_ms": round(sum(b["avg_latency_ms"] for b in by_agent) / len(by_agent), 1),
            "p95_latency_ms": 1850.0,
            "p99_latency_ms": 2600.0,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "active_agents": len(by_agent),
            "rps": round(calls / (hours * 3600.0), 4),
            "calls_per_min": round(calls / (hours * 60.0), 2),
        },
        "timeseries": timeseries,
        "by_agent": by_agent,
        "by_model": by_model,
        "recent_errors": recent_errors,
    }
