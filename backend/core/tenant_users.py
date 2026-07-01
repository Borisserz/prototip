"""Хранилище пользователей тенанта (per-tenant user management).

Каждый блок (tenant) может иметь собственных пользователей, которых заводит
администратор. Пользователь привязан к ``client_id`` и несёт гранулярные права:

  • ``role``               — роль (для RLS-маппинга по ролям, обратная совместимость);
  • ``allowed_tables``     — белый список таблиц (поверх tenant.allowed_tables);
  • ``allowed_columns``    — белый список колонок (агенты не выйдут за их пределы);
  • ``rls_filters``        — построчная изоляция {column: [values]} (напр. region);
  • ``can_dashboard``      — право на генерацию дашбордов;
  • ``can_presentation``   — право на генерацию презентаций.

Хранилище — таблица ClickHouse ``default.tenant_users`` (append-only, актуальное
состояние через argMax(updated_at), мягкое удаление флагом ``deleted``). Такой
подход согласован с ``core.rls`` (rls_role_filters) и переживает рестарты.

Модуль устойчив: при недоступности ClickHouse функции чтения возвращают пустые
значения, а не роняют приложение. Пароли хешируются через ``app.auth`` (bcrypt).
"""

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime
from typing import Any

logger = logging.getLogger("TenantUsers")

_TABLE = "default.tenant_users"
_CACHE_TTL = 15.0  # сек — короткий кэш чтения, правки видны почти сразу

_lock = threading.RLock()
# кэш: {client_id|"*": {"data": ..., "ts": ...}}
_cache: dict[str, dict[str, Any]] = {}

# Колонки таблицы (порядок важен для insert)
_COLUMNS = [
    "client_id",
    "username",
    "password_hash",
    "role",
    "allowed_tables",
    "allowed_columns",
    "rls_filters",
    "can_dashboard",
    "can_presentation",
    "active",
    "deleted",
    "updated_at",
]


# ─── ClickHouse helpers ──────────────────────────────────────────────────────
def _ch():
    from app.utils.clickhouse_client import ch_client

    return ch_client


def ensure_table() -> None:
    """Создаёт таблицу пользователей тенанта (idempotent)."""
    _ch().command(
        f"""
        CREATE TABLE IF NOT EXISTS {_TABLE} (
            client_id String,
            username String,
            password_hash String,
            role String DEFAULT 'manager',
            allowed_tables Array(String),
            allowed_columns Array(String),
            rls_filters String DEFAULT '{{}}',
            can_dashboard UInt8 DEFAULT 1,
            can_presentation UInt8 DEFAULT 1,
            active UInt8 DEFAULT 1,
            deleted UInt8 DEFAULT 0,
            updated_at DateTime DEFAULT now()
        ) ENGINE = MergeTree ORDER BY (client_id, username)
        """
    )


# Подзапрос с актуальным состоянием каждого пользователя (argMax по updated_at)
_LATEST_SELECT = f"""
    SELECT
        client_id,
        username,
        argMax(password_hash, updated_at)   AS password_hash,
        argMax(role, updated_at)            AS role,
        argMax(allowed_tables, updated_at)  AS allowed_tables,
        argMax(allowed_columns, updated_at) AS allowed_columns,
        argMax(rls_filters, updated_at)     AS rls_filters,
        argMax(can_dashboard, updated_at)   AS can_dashboard,
        argMax(can_presentation, updated_at) AS can_presentation,
        argMax(active, updated_at)          AS active,
        argMax(deleted, updated_at)         AS deleted
    FROM {_TABLE}
    GROUP BY client_id, username
"""


def _parse_filters(raw: str | None) -> dict[str, list[str]]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            return {}
        out: dict[str, list[str]] = {}
        for col, vals in data.items():
            if vals is None:
                continue
            if isinstance(vals, (str, int, float)):
                vals = [vals]
            cleaned = [str(v) for v in vals if v is not None and str(v) != ""]
            if cleaned:
                out[str(col)] = cleaned
        return out
    except Exception:  # noqa: BLE001
        return {}


def _row_to_public(r: dict[str, Any]) -> dict[str, Any]:
    """Публичное представление пользователя (без хеша пароля)."""
    return {
        "client_id": r.get("client_id", ""),
        "username": r.get("username", ""),
        "role": r.get("role", "manager"),
        "allowed_tables": list(r.get("allowed_tables") or []),
        "allowed_columns": list(r.get("allowed_columns") or []),
        "rls_filters": _parse_filters(r.get("rls_filters")),
        "can_dashboard": bool(r.get("can_dashboard", 1)),
        "can_presentation": bool(r.get("can_presentation", 1)),
        "active": bool(r.get("active", 1)),
    }


def _fetch_all() -> list[dict[str, Any]]:
    """Все актуальные (не удалённые) пользователи. [] при недоступности ClickHouse."""
    with _lock:
        now = time.time()
        c = _cache.get("*")
        if c and now - c["ts"] < _CACHE_TTL:
            return c["data"]
    try:
        ensure_table()
        res = _ch().execute(_LATEST_SELECT)
        cols = res.column_names
        rows = [dict(zip(cols, row)) for row in res.result_rows]
        rows = [r for r in rows if not int(r.get("deleted", 0))]
    except Exception as exc:  # noqa: BLE001
        logger.debug("[TenantUsers] ClickHouse недоступен для чтения: %s", exc)
        rows = []
    with _lock:
        _cache["*"] = {"data": rows, "ts": time.time()}
    return rows


def _invalidate() -> None:
    with _lock:
        _cache.clear()


# ─── Публичный API ───────────────────────────────────────────────────────────
def list_users(client_id: str) -> list[dict[str, Any]]:
    """Активные (не удалённые) пользователи блока — публичное представление."""
    return [_row_to_public(r) for r in _fetch_all() if r.get("client_id") == client_id]


def count_active_users(client_id: str) -> int:
    """Число живых пользователей блока (active=1, deleted=0) — для лимита max_users."""
    return sum(
        1 for r in _fetch_all() if r.get("client_id") == client_id and int(r.get("active", 1))
    )


def get_user_record(username: str) -> dict[str, Any] | None:
    """Сырой актуальный рекорд пользователя по логину (с хешем) — для аутентификации.

    Логин уникален в пределах системы. Возвращает None, если пользователь не найден.
    """
    uname = (username or "").strip().lower()
    if not uname:
        return None
    for r in _fetch_all():
        if r.get("username", "").lower() == uname and int(r.get("active", 1)):
            return r
    return None


def get_user_auth(username: str) -> dict[str, Any] | None:
    """Данные для аутентификации: {username, role, client_id, password_hash}."""
    r = get_user_record(username)
    if not r:
        return None
    return {
        "username": r.get("username", ""),
        "role": r.get("role", "manager"),
        "client_id": r.get("client_id", ""),
        "password_hash": r.get("password_hash", ""),
    }


def get_user_permissions(client_id: str, username: str) -> dict[str, Any] | None:
    """Гранулярные права пользователя в блоке (для sql_guard / гейтинга фич)."""
    uname = (username or "").strip().lower()
    if not uname:
        return None
    for r in _fetch_all():
        if (
            r.get("client_id") == client_id
            and r.get("username", "").lower() == uname
            and not int(r.get("deleted", 0))
        ):
            pub = _row_to_public(r)
            return {
                "role": pub["role"],
                "allowed_tables": pub["allowed_tables"],
                "allowed_columns": pub["allowed_columns"],
                "rls_filters": pub["rls_filters"],
                "can_dashboard": pub["can_dashboard"],
                "can_presentation": pub["can_presentation"],
            }
    return None


def _insert(record: dict[str, Any]) -> None:
    ensure_table()
    row = [
        record["client_id"],
        record["username"],
        record.get("password_hash", ""),
        record.get("role", "manager"),
        list(record.get("allowed_tables") or []),
        list(record.get("allowed_columns") or []),
        json.dumps(record.get("rls_filters") or {}, ensure_ascii=False),
        int(bool(record.get("can_dashboard", 1))),
        int(bool(record.get("can_presentation", 1))),
        int(bool(record.get("active", 1))),
        int(bool(record.get("deleted", 0))),
        datetime.now(),
    ]
    _ch().insert(_TABLE, [row], column_names=_COLUMNS)
    _invalidate()


def create_user(
    client_id: str,
    username: str,
    password: str,
    *,
    role: str = "manager",
    allowed_tables: list[str] | None = None,
    allowed_columns: list[str] | None = None,
    rls_filters: dict[str, list[str]] | None = None,
    can_dashboard: bool = True,
    can_presentation: bool = True,
    max_users: int = 0,
) -> dict[str, Any]:
    """Создаёт пользователя в блоке. Бросает ValueError при нарушении правил.

    ``max_users`` (0 = без лимита) — лимит живых пользователей блока.
    """
    from app.auth import get_password_hash

    uname = (username or "").strip().lower()
    if not uname:
        raise ValueError("Логин обязателен")
    if not password or len(password) < 4:
        raise ValueError("Пароль обязателен (минимум 4 символа)")
    if not client_id:
        raise ValueError("client_id обязателен")

    # логин уникален в пределах системы (логин→client_id при входе)
    existing = get_user_record(uname)
    if existing:
        raise ValueError(f"Пользователь '{uname}' уже существует")

    # лимит пользователей блока
    if max_users and count_active_users(client_id) >= max_users:
        raise ValueError(
            f"Достигнут лимит пользователей блока ({max_users}). "
            "Увеличьте лимит в настройках клиента."
        )

    record = {
        "client_id": client_id,
        "username": uname,
        "password_hash": get_password_hash(password),
        "role": role or "manager",
        "allowed_tables": allowed_tables or [],
        "allowed_columns": allowed_columns or [],
        "rls_filters": rls_filters or {},
        "can_dashboard": can_dashboard,
        "can_presentation": can_presentation,
        "active": True,
        "deleted": False,
    }
    _insert(record)
    logger.info("[TenantUsers] создан пользователь '%s' в блоке '%s'", uname, client_id)
    return _row_to_public(record)


def update_user(
    client_id: str,
    username: str,
    *,
    password: str | None = None,
    role: str | None = None,
    allowed_tables: list[str] | None = None,
    allowed_columns: list[str] | None = None,
    rls_filters: dict[str, list[str]] | None = None,
    can_dashboard: bool | None = None,
    can_presentation: bool | None = None,
    active: bool | None = None,
) -> dict[str, Any] | None:
    """Обновляет пользователя (append-only: пишет новую версию). None если не найден."""
    from app.auth import get_password_hash

    uname = (username or "").strip().lower()
    cur = None
    for r in _fetch_all():
        if r.get("client_id") == client_id and r.get("username", "").lower() == uname:
            cur = r
            break
    if not cur:
        return None

    record = {
        "client_id": client_id,
        "username": cur.get("username", uname),
        "password_hash": get_password_hash(password) if password else cur.get("password_hash", ""),
        "role": role if role is not None else cur.get("role", "manager"),
        "allowed_tables": allowed_tables
        if allowed_tables is not None
        else list(cur.get("allowed_tables") or []),
        "allowed_columns": allowed_columns
        if allowed_columns is not None
        else list(cur.get("allowed_columns") or []),
        "rls_filters": rls_filters
        if rls_filters is not None
        else _parse_filters(cur.get("rls_filters")),
        "can_dashboard": can_dashboard
        if can_dashboard is not None
        else bool(cur.get("can_dashboard", 1)),
        "can_presentation": can_presentation
        if can_presentation is not None
        else bool(cur.get("can_presentation", 1)),
        "active": active if active is not None else bool(cur.get("active", 1)),
        "deleted": False,
    }
    _insert(record)
    logger.info("[TenantUsers] обновлён пользователь '%s' в блоке '%s'", uname, client_id)
    return _row_to_public(record)


def delete_user(client_id: str, username: str) -> bool:
    """Мягкое удаление пользователя (deleted=1). True если найден и удалён."""
    uname = (username or "").strip().lower()
    cur = None
    for r in _fetch_all():
        if r.get("client_id") == client_id and r.get("username", "").lower() == uname:
            cur = r
            break
    if not cur:
        return False
    record = {
        "client_id": client_id,
        "username": cur.get("username", uname),
        "password_hash": cur.get("password_hash", ""),
        "role": cur.get("role", "manager"),
        "allowed_tables": list(cur.get("allowed_tables") or []),
        "allowed_columns": list(cur.get("allowed_columns") or []),
        "rls_filters": _parse_filters(cur.get("rls_filters")),
        "can_dashboard": bool(cur.get("can_dashboard", 1)),
        "can_presentation": bool(cur.get("can_presentation", 1)),
        "active": False,
        "deleted": True,
    }
    _insert(record)
    logger.info("[TenantUsers] удалён пользователь '%s' из блока '%s'", uname, client_id)
    return True


def list_tenant_tables(tenant) -> dict[str, list[str]]:
    """Возвращает {table: [columns]} из персонального ClickHouse клиента.

    Для UI назначения прав. При недоступности БД — отдаёт allowed_tables без колонок.
    """
    tables = list(getattr(tenant, "allowed_tables", []) or [])
    result: dict[str, list[str]] = {t: [] for t in tables}
    try:
        from core.tenant import tenant_store

        client = tenant_store.get_clickhouse_client(tenant)
        db = tenant.clickhouse.database or "default"
        # если allowed_tables пуст — берём все таблицы базы клиента
        if not tables:
            res = client.query(
                "SELECT name FROM system.tables WHERE database = {db:String}",
                parameters={"db": db},
            )
            tables = [r[0] for r in res.result_rows]
            result = {t: [] for t in tables}
        for t in tables:
            try:
                res = client.query(
                    "SELECT name FROM system.columns "
                    "WHERE database = {db:String} AND table = {t:String} ORDER BY position",
                    parameters={"db": db, "t": t},
                )
                result[t] = [r[0] for r in res.result_rows]
            except Exception:  # noqa: BLE001
                result[t] = []
    except Exception as exc:  # noqa: BLE001
        logger.debug("[TenantUsers] не удалось получить схему клиента: %s", exc)
    return result
