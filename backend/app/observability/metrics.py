"""Кастомные бизнес-метрики Prometheus (Phase 8: Observability).

Все метрики регистрируются в глобальном реестре ``prometheus_client``,
который уже экспонируется через ``/metrics`` (prometheus_fastapi_instrumentator
в ``app/main.py``). Поэтому отдельный эндпоинт здесь не нужен — достаточно
импортировать этот модуль, чтобы метрики появились в выгрузке.

Экспонируемые метрики:
  * prototip_llm_call_duration_seconds   — гистограмма длительности вызова LLM
  * prototip_llm_calls_total             — счётчик вызовов LLM (по статусу)
  * prototip_llm_prompt_tokens_total     — суммарные prompt-токены
  * prototip_llm_completion_tokens_total — суммарные completion-токены
  * prototip_sql_validation_errors_total — ошибки валидации SQL (SqlGuard)
  * prototip_langgraph_node_duration_seconds — длительность узлов LangGraph

Модуль написан «защищённо»: при повторной регистрации метрики (например,
двойной импорт под другим именем пакета) переиспользуется уже существующий
коллектор, а не падает с ``Duplicated timeseries``.
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Iterator

from prometheus_client import Counter, Histogram
from prometheus_client.registry import REGISTRY

logger = logging.getLogger("observability")


def _get_or_create(factory, name: str, *args, **kwargs):
    """Создаёт метрику либо возвращает уже зарегистрированную (идемпотентно)."""
    try:
        return factory(name, *args, **kwargs)
    except ValueError:
        # Метрика с таким именем уже есть в реестре — переиспользуем её.
        existing = REGISTRY._names_to_collectors.get(name)  # noqa: SLF001
        if existing is not None:
            return existing
        raise


# ── Латентность и объёмы вызовов LLM ────────────────────────────────────────
_LLM_BUCKETS = (0.1, 0.25, 0.5, 1, 2, 5, 10, 20, 30, 60, 120)

LLM_CALL_DURATION = _get_or_create(
    Histogram,
    "prototip_llm_call_duration_seconds",
    "Длительность вызова LLM (секунды)",
    ["agent", "model", "status"],
    buckets=_LLM_BUCKETS,
)

LLM_CALLS_TOTAL = _get_or_create(
    Counter,
    "prototip_llm_calls_total",
    "Количество вызовов LLM",
    ["agent", "model", "status"],
)

LLM_PROMPT_TOKENS = _get_or_create(
    Counter,
    "prototip_llm_prompt_tokens_total",
    "Суммарное число prompt-токенов",
    ["agent", "model"],
)

LLM_COMPLETION_TOKENS = _get_or_create(
    Counter,
    "prototip_llm_completion_tokens_total",
    "Суммарное число completion-токенов",
    ["agent", "model"],
)

# ── Ошибки валидации SQL ────────────────────────────────────────────────────
SQL_VALIDATION_ERRORS = _get_or_create(
    Counter,
    "prototip_sql_validation_errors_total",
    "Количество отклонённых SqlGuard SQL-запросов",
    ["reason"],
)

# ── Длительность узлов LangGraph ────────────────────────────────────────────
_NODE_BUCKETS = (0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 20, 30, 60)

LANGGRAPH_NODE_DURATION = _get_or_create(
    Histogram,
    "prototip_langgraph_node_duration_seconds",
    "Длительность выполнения узла графа LangGraph (секунды)",
    ["node", "status"],
    buckets=_NODE_BUCKETS,
)


def observe_llm_call(
    *,
    agent: str,
    model: str,
    status: str,
    duration_s: float,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
) -> None:
    """Зафиксировать один вызов LLM в метриках Prometheus."""
    agent = agent or "unknown"
    model = model or "unknown"
    status = status or "ok"
    try:
        LLM_CALL_DURATION.labels(agent=agent, model=model, status=status).observe(max(0.0, duration_s))
        LLM_CALLS_TOTAL.labels(agent=agent, model=model, status=status).inc()
        if prompt_tokens:
            LLM_PROMPT_TOKENS.labels(agent=agent, model=model).inc(prompt_tokens)
        if completion_tokens:
            LLM_COMPLETION_TOKENS.labels(agent=agent, model=model).inc(completion_tokens)
    except Exception as exc:  # метрики никогда не должны ломать бизнес-логику
        logger.debug("observe_llm_call failed: %s", exc)


def record_sql_validation_error(reason: str = "unknown") -> None:
    """Учесть ошибку валидации SQL (нормализуя текст причины в короткий ярлык)."""
    try:
        SQL_VALIDATION_ERRORS.labels(reason=_normalize_reason(reason)).inc()
    except Exception as exc:
        logger.debug("record_sql_validation_error failed: %s", exc)


def _normalize_reason(reason: str) -> str:
    """Свести произвольный текст ошибки к ограниченному набору меток (low-cardinality)."""
    r = (reason or "").lower()
    if "select" in r and ("только" in r or "разреш" in r):
        return "not_select"
    if "несколько" in r or "multiple" in r:
        return "multiple_statements"
    if "функци" in r:
        return "forbidden_function"
    if "таблиц" in r:
        return "forbidden_table"
    if "пуст" in r or "empty" in r:
        return "empty"
    if "запрещ" in r or "операц" in r:
        return "forbidden_operation"
    return "other"


@contextmanager
def node_timer(node: str) -> Iterator[None]:
    """Контекст-менеджер для замера длительности узла LangGraph."""
    start = time.perf_counter()
    status = "ok"
    try:
        yield
    except Exception:
        status = "error"
        raise
    finally:
        try:
            LANGGRAPH_NODE_DURATION.labels(node=node, status=status).observe(
                time.perf_counter() - start
            )
        except Exception as exc:
            logger.debug("node_timer observe failed: %s", exc)
