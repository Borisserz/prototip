"""RLS (Row-Level Security) маппинг роль → фильтры.

Единый источник правды для построчной изоляции по ролям. Заменяет жёстко
зашитый маппинг роль→регион, который раньше дублировался в DataAgent и
CrewAI-инструментах (и содержал баг: "г. Гродно" вместо "Гродненская область").

Хранилище (приоритет):
  1. Таблица ClickHouse ``default.rls_role_filters`` — редактируется админом
     из интерфейса (admin-консоль → вкладка «Доступ по ролям»). Append-only,
     актуальное значение берётся через argMax(updated_at).
  2. Fallback / seed — ``backend/domain/rls_config.yaml`` (используется, если
     таблицы ещё нет, ClickHouse недоступен, или для первичного заполнения).

Чтение кэшируется в памяти (TTL), запись инвалидирует кэш — поэтому правки из
интерфейса применяются агентами почти сразу, без перезапуска процесса.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from functools import lru_cache
from pathlib import Path

import yaml

logger = logging.getLogger("rls")

_CONFIG_PATH = Path(__file__).parent.parent / "domain" / "rls_config.yaml"
_TABLE = "default.rls_role_filters"
_CACHE_TTL = 30.0  # сек

_lock = threading.RLock()
_cache: dict[str, object] = {"data": None, "ts": 0.0}


# ─── YAML (fallback / seed) ──────────────────────────────────────────────────
@lru_cache(maxsize=1)
def _load_yaml() -> dict[str, dict[str, list[str]]]:
    try:
        with _CONFIG_PATH.open(encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        roles = data.get("roles", {}) or {}
        return {role: _normalize(cols) for role, cols in roles.items()}
    except FileNotFoundError:
        logger.warning("[RLS] Конфиг %s не найден.", _CONFIG_PATH)
        return {}
    except Exception as exc:  # noqa: BLE001
        logger.error("[RLS] Ошибка чтения %s: %s", _CONFIG_PATH, exc)
        return {}


def _normalize(cols: dict | None) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for column, values in (cols or {}).items():
        if values is None:
            continue
        if isinstance(values, (str, int, float)):
            values = [values]
        cleaned = [str(v) for v in values if v is not None and str(v) != ""]
        if cleaned:
            result[column] = cleaned
    return result


# ─── ClickHouse-хранилище ────────────────────────────────────────────────────
def _ch():
    from app.utils.clickhouse_client import ch_client

    return ch_client


def ensure_table(seed: bool = True) -> None:
    """Создаёт таблицу RLS (idempotent) и при пустой таблице засевает из YAML."""
    ch = _ch()
    ch.command(
        f"""
        CREATE TABLE IF NOT EXISTS {_TABLE} (
            role String,
            filter_column String,
            vals Array(String),
            updated_at DateTime DEFAULT now()
        ) ENGINE = MergeTree ORDER BY (role, filter_column)
        """
    )
    if not seed:
        return
    try:
        res = ch.execute(f"SELECT count() FROM {_TABLE}")
        count = res.result_rows[0][0] if res.result_rows else 0
    except Exception:  # noqa: BLE001
        count = 0
    if count == 0:
        yaml_rules = _load_yaml()
        rows = []
        now = datetime.now()
        for role, cols in yaml_rules.items():
            for column, values in cols.items():
                rows.append([role, column, list(values), now])
        if rows:
            ch.insert(_TABLE, rows, column_names=["role", "filter_column", "vals", "updated_at"])
            logger.info("[RLS] Таблица %s засеяна из YAML (%d строк).", _TABLE, len(rows))


def _load_db() -> dict[str, dict[str, list[str]]] | None:
    """Читает все правила из ClickHouse. None — если ClickHouse недоступен/таблицы нет."""
    try:
        ch = _ch()
        res = ch.execute(
            f"""
            SELECT role, filter_column, argMax(vals, updated_at) AS vals
            FROM {_TABLE}
            GROUP BY role, filter_column
            """
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("[RLS] ClickHouse недоступен для чтения правил: %s", exc)
        return None

    rules: dict[str, dict[str, list[str]]] = {}
    for role, column, vals in res.result_rows:
        cleaned = [str(v) for v in (vals or []) if v is not None and str(v) != ""]
        if not cleaned:
            continue
        rules.setdefault(role, {})[column] = cleaned
    return rules


# ─── Кэш + объединённое чтение ───────────────────────────────────────────────
def _all_rules(force: bool = False) -> dict[str, dict[str, list[str]]]:
    with _lock:
        now = time.time()
        if not force and _cache["data"] is not None and now - float(_cache["ts"]) < _CACHE_TTL:
            return _cache["data"]  # type: ignore[return-value]
        db = _load_db()
        data = db if db is not None else _load_yaml()
        _cache["data"] = data
        _cache["ts"] = now
        return data


# ─── Публичный API (горячий путь агентов) ────────────────────────────────────
def get_role_filters(role: str | None) -> dict[str, list[str]]:
    """Возвращает фильтры RLS для роли в виде {column: [values...]}.

    Пустой dict — ограничений нет (роль видит все данные). Значения всегда
    список → вызывающий код применяет их как `col IN (...)`. Никогда не бросает
    исключение (горячий путь): при любой ошибке возвращает {}.
    """
    if not role:
        return {}
    try:
        return dict(_all_rules().get(role, {}))
    except Exception as exc:  # noqa: BLE001
        logger.error("[RLS] get_role_filters упал, фильтры отключены: %s", exc)
        return {}


# ─── Admin API (используется маршрутами) ────────────────────────────────────
def list_rules() -> dict[str, dict[str, list[str]]]:
    """Все правила (для админ-консоли)."""
    return _all_rules(force=True)


def set_role_filter(role: str, column: str, values: list[str]) -> None:
    """Задаёт значения фильтра для роли (append-only, актуальное — последнее)."""
    role = (role or "").strip()
    column = (column or "").strip()
    if not role or not column:
        raise ValueError("role и column обязательны")
    cleaned = [str(v).strip() for v in (values or []) if v is not None and str(v).strip() != ""]
    ensure_table(seed=False)
    _ch().insert(
        _TABLE,
        [[role, column, cleaned, datetime.now()]],
        column_names=["role", "filter_column", "vals", "updated_at"],
    )
    reload_config()


import re


def _sanitize_identifier(name: str) -> str:
    if not re.match(r"^[a-zA-Z0-9_.]+$", name):
        raise ValueError(f"Invalid SQL identifier: {name}")
    return name


def list_region_values(
    column: str = "region", table: str = "default.enterprise_taxes"
) -> list[str]:
    """Доступные значения фильтра из DWH (для выпадающего списка в UI)."""
    try:
        col = _sanitize_identifier(column)
        tbl = _sanitize_identifier(table)
        res = _ch().execute(f"SELECT DISTINCT {col} FROM {tbl} WHERE {col} != '' ORDER BY {col}")
        return [r[0] for r in res.result_rows]
    except Exception as exc:  # noqa: BLE001
        logger.warning("[RLS] Не удалось получить значения '%s' из %s: %s", column, table, exc)
        return []


def reload_config() -> None:
    """Сбрасывает кэши (после правки админом из интерфейса)."""
    _load_yaml.cache_clear()
    with _lock:
        _cache["data"] = None
        _cache["ts"] = 0.0
