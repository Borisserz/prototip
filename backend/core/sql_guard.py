"""Жёсткая валидация и изоляция SQL (Phase 6: Multi-tenant security).

Раньше валидация лишь проверяла, что запрос начинается с SELECT. Теперь:
  1. Парсит запрос (sqlglot, диалект ClickHouse); невалидный/множественный → отказ.
  2. Разрешает ТОЛЬКО SELECT — блокирует DROP/DELETE/INSERT/UPDATE/ALTER/TRUNCATE/
     CREATE/GRANT/ATTACH/DETACH/OPTIMIZE/SYSTEM/RENAME и любые command-узлы.
  3. Блокирует опасные табличные функции ClickHouse (file/url/remote/s3/mysql/...).
  4. Проверяет, что все таблицы входят в allowed_tables клиента (если задан список).
  5. Жёстко добавляет WHERE client_id = '<value>' (row-isolation) во все SELECT,
     если у клиента включён enforce_client_id.
  6. Применяет дополнительные RLS-фильтры (например, region для роли) и LIMIT.

Возвращает безопасный SQL или бросает ValueError с понятным сообщением.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import sqlglot
from sqlglot import exp

if TYPE_CHECKING:
    from core.tenant import Tenant

logger = logging.getLogger("SqlGuard")

# Узлы, которые НИКОГДА не должны встречаться в пользовательском запросе
_FORBIDDEN_NODES = (
    exp.Drop, exp.Delete, exp.Insert, exp.Update, exp.Alter, exp.Create,
    exp.Command,  # TRUNCATE, GRANT, SYSTEM, OPTIMIZE, ATTACH, DETACH, RENAME, SET, USE...
    exp.Grant if hasattr(exp, "Grant") else exp.Command,
)

# Опасные табличные/исполняемые функции ClickHouse — запрещены
_FORBIDDEN_FUNCTIONS = {
    "file", "url", "remote", "remotesecure", "s3", "s3cluster", "hdfs", "jdbc",
    "odbc", "mysql", "postgresql", "sqlite", "mongodb", "redis", "executable",
    "cluster", "clusterallreplicas", "input", "deltalake", "hudi", "iceberg",
    "azureblobstorage", "gcs", "format", "infile",
}


class SqlSecurityError(ValueError):
    """Нарушение политики безопасности SQL."""


def _ensure_single_select(sql: str) -> exp.Expression:
    statements = [s for s in sqlglot.parse(sql, read="clickhouse") if s is not None]
    if len(statements) == 0:
        raise SqlSecurityError("Пустой SQL-запрос.")
    if len(statements) > 1:
        raise SqlSecurityError("Запрещено несколько SQL-операторов в одном запросе.")
    root = statements[0]

    # запрещаем любые мутирующие/DDL-узлы где угодно в дереве
    for node_type in _FORBIDDEN_NODES:
        if root.find(node_type) is not None:
            raise SqlSecurityError(
                f"Запрещённая операция в SQL: {node_type.__name__.upper()}. Разрешён только SELECT."
            )

    # корень должен быть SELECT/UNION/WITH(SELECT)
    select_types = (exp.Select, exp.Union, exp.Subquery)
    if not isinstance(root, select_types) and root.find(exp.Select) is None:
        raise SqlSecurityError("Разрешены только SELECT-запросы.")
    return root


def _check_functions(root: exp.Expression) -> None:
    for fn in root.find_all(exp.Anonymous):
        name = (fn.name or "").lower()
        if name in _FORBIDDEN_FUNCTIONS:
            raise SqlSecurityError(f"Запрещённая функция в SQL: {name}().")
    # некоторые функции парсятся как именованные узлы
    for fn in root.find_all(exp.Func):
        name = (fn.sql_name() or "").lower() if hasattr(fn, "sql_name") else ""
        if name in _FORBIDDEN_FUNCTIONS:
            raise SqlSecurityError(f"Запрещённая функция в SQL: {name}().")


def _referenced_tables(root: exp.Expression) -> set[str]:
    tables: set[str] = set()
    for tbl in root.find_all(exp.Table):
        if tbl.name:
            tables.add(tbl.name.lower())
    return tables


def _check_allowed_tables(root: exp.Expression, allowed: list[str]) -> None:
    if not allowed:
        return
    allowed_set = {a.lower() for a in allowed}
    used = _referenced_tables(root)
    illegal = used - allowed_set
    if illegal:
        raise SqlSecurityError(
            "Доступ к таблицам запрещён конфигурацией клиента: "
            + ", ".join(sorted(illegal))
            + f". Разрешены: {', '.join(sorted(allowed_set))}."
        )


def _inject_equality_filter(root: exp.Expression, column: str, value: str) -> None:
    """Добавляет AND column = 'value' в КАЖДЫЙ SELECT с FROM-таблицей."""
    safe_val = str(value).replace("'", "''")
    for select in root.find_all(exp.Select):
        # фильтр нужен только если select реально читает таблицу
        if select.find(exp.Table) is None:
            continue
        cond = exp.condition(f"{column} = '{safe_val}'")
        select.where(cond, append=True, copy=False)


def _ensure_limit(root: exp.Expression, default_limit: int = 500) -> None:
    # навешиваем LIMIT только на верхний SELECT, если его нет
    target = root
    if isinstance(root, exp.Subquery):
        target = root.this
    if isinstance(target, exp.Union):
        return  # у UNION limit трогать не будем
    if isinstance(target, exp.Select) and not target.args.get("limit"):
        target.limit(default_limit, copy=False)


def secure_sql(
    sql: str,
    tenant: Tenant | None = None,
    *,
    extra_filters: dict[str, str] | None = None,
    default_limit: int = 500,
) -> str:
    """Валидирует и «укрепляет» SQL под политику клиента. Бросает SqlSecurityError."""
    sql = (sql or "").strip().rstrip(";")
    if not sql:
        raise SqlSecurityError("Пустой SQL-запрос.")

    root = _ensure_single_select(sql)
    _check_functions(root)

    if tenant is not None:
        _check_allowed_tables(root, tenant.allowed_tables)
        if tenant.enforce_client_id and tenant.client_id_value:
            _inject_equality_filter(root, "client_id", tenant.client_id_value)

    # дополнительные RLS-фильтры (например, region для роли)
    for col, val in (extra_filters or {}).items():
        if val:
            _inject_equality_filter(root, col, val)

    _ensure_limit(root, default_limit)

    secured = root.sql(dialect="clickhouse")
    logger.info("[SqlGuard] secured SQL: %s", secured)
    return secured


def is_safe_select(sql: str) -> bool:
    """Быстрая проверка без модификации (True — это безопасный SELECT)."""
    try:
        root = _ensure_single_select((sql or "").strip().rstrip(";"))
        _check_functions(root)
        return True
    except Exception:  # noqa: BLE001
        return False
