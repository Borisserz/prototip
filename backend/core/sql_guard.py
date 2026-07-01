"""Жёсткая валидация и изоляция SQL.

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

# бизнес-метрики Prometheus (импорт защищён)
try:
    from app.observability.metrics import record_sql_validation_error
except Exception:  # pragma: no cover

    def record_sql_validation_error(reason: str = "unknown"):  # type: ignore
        return None


# Узлы, которые НИКОГДА не должны встречаться в пользовательском запросе
_FORBIDDEN_NODES = (
    exp.Drop,
    exp.Delete,
    exp.Insert,
    exp.Update,
    exp.Alter,
    exp.Create,
    exp.Command,  # TRUNCATE, GRANT, SYSTEM, OPTIMIZE, ATTACH, DETACH, RENAME, SET, USE...
    exp.Grant if hasattr(exp, "Grant") else exp.Command,
)

# Опасные табличные/исполняемые функции ClickHouse — запрещены
_FORBIDDEN_FUNCTIONS = {
    "file",
    "url",
    "remote",
    "remotesecure",
    "s3",
    "s3cluster",
    "hdfs",
    "jdbc",
    "odbc",
    "mysql",
    "postgresql",
    "sqlite",
    "mongodb",
    "redis",
    "executable",
    "cluster",
    "clusterallreplicas",
    "input",
    "deltalake",
    "hudi",
    "iceberg",
    "azureblobstorage",
    "gcs",
    "format",
    "infile",
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


def _check_allowed_columns(
    root: exp.Expression, allowed: list[str], extra_allowed: set[str] | None = None
) -> None:
    """Запрещает обращение к колонкам вне белого списка пользователя.

    Логика:
      • если список пуст — ограничений по колонкам нет (skip);
      • ``SELECT *`` и ``t.*`` запрещены — нельзя проверить, какие колонки раскрываются;
      • ``count(*)`` разрешён (Star внутри функции-агрегата, не проекция);
      • все ссылки на колонки должны входить в allowed (или в extra_allowed —
        колонки RLS/изоляции, которые мы добавляем сами).
    """
    if not allowed:
        return
    allowed_set = {a.lower() for a in allowed}
    if extra_allowed:
        allowed_set |= {c.lower() for c in extra_allowed}

    # 1. Запрет звёздочки в проекции (SELECT * / t.*) — иначе обойдём ограничение.
    for select in root.find_all(exp.Select):
        for projection in select.expressions:
            if isinstance(projection, exp.Star):
                raise SqlSecurityError(
                    "SELECT * запрещён: укажите конкретные колонки. "
                    f"Разрешены: {', '.join(sorted(allowed_set))}."
                )
            # t.* → Column с this=Star
            if isinstance(projection, exp.Column) and isinstance(projection.this, exp.Star):
                raise SqlSecurityError(
                    "SELECT t.* запрещён: укажите конкретные колонки. "
                    f"Разрешены: {', '.join(sorted(allowed_set))}."
                )

    # 2. Проверка всех ссылок на колонки.
    illegal: set[str] = set()
    for col in root.find_all(exp.Column):
        if isinstance(col.this, exp.Star):
            continue  # обработано выше
        name = (col.name or "").lower()
        if not name:
            continue
        if name not in allowed_set:
            illegal.add(col.name)
    if illegal:
        raise SqlSecurityError(
            "Доступ к колонкам запрещён вашими правами: "
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


def _inject_in_filter(root: exp.Expression, column: str, values: list[str]) -> None:
    """Добавляет AND column IN ('v1','v2',...) в КАЖДЫЙ SELECT с FROM-таблицей.

    Используется для RLS-фильтров «семейством» значений (напр. роль →
    несколько вариантов региона: область + город), чтобы не ронять выборку
    из-за рассогласования одного жёстко зашитого значения.
    """
    safe_vals = [str(v).replace("'", "''") for v in values if v is not None and str(v) != ""]
    if not safe_vals:
        return
    in_list = ", ".join(f"'{v}'" for v in safe_vals)
    for select in root.find_all(exp.Select):
        if select.find(exp.Table) is None:
            continue
        cond = exp.condition(f"{column} IN ({in_list})")
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
    extra_filters: dict[str, str | list[str]] | None = None,
    allowed_tables: list[str] | None = None,
    allowed_columns: list[str] | None = None,
    default_limit: int = 500,
) -> str:
    """Валидирует и «укрепляет» SQL под политику клиента. Бросает SqlSecurityError.

    Тонкая обёртка над ``_secure_sql_impl``: при любом нарушении политики
    инкрементирует Prometheus-счётчик ``prototip_sql_validation_errors_total``.

    ``allowed_tables`` / ``allowed_columns`` — персональные ограничения пользователя
    (поверх tenant.allowed_tables). Если заданы, агент не сможет выйти за их пределы.
    """
    try:
        return _secure_sql_impl(
            sql,
            tenant,
            extra_filters=extra_filters,
            allowed_tables=allowed_tables,
            allowed_columns=allowed_columns,
            default_limit=default_limit,
        )
    except SqlSecurityError as exc:
        record_sql_validation_error(str(exc))
        raise


def _secure_sql_impl(
    sql: str,
    tenant: Tenant | None = None,
    *,
    extra_filters: dict[str, str | list[str]] | None = None,
    allowed_tables: list[str] | None = None,
    allowed_columns: list[str] | None = None,
    default_limit: int = 500,
) -> str:
    sql = (sql or "").strip().rstrip(";")
    if not sql:
        raise SqlSecurityError("Пустой SQL-запрос.")

    root = _ensure_single_select(sql)
    _check_functions(root)

    if tenant is not None:
        _check_allowed_tables(root, tenant.allowed_tables)
        if tenant.enforce_client_id and tenant.client_id_value:
            _inject_equality_filter(root, "client_id", tenant.client_id_value)

    # Персональные ограничения пользователя (per-tenant user).
    # Таблицы: пересечение с tenant.allowed_tables (оба ограничения должны пройти).
    if allowed_tables:
        _check_allowed_tables(root, allowed_tables)

    # Колонки: проверяем ДО инъекции фильтров. Колонки RLS/изоляции, которые мы
    # добавляем сами, всегда разрешены (extra_allowed), чтобы не отклонить запрос.
    if allowed_columns:
        extra_allowed: set[str] = set(extra_filters.keys()) if extra_filters else set()
        if tenant is not None and tenant.enforce_client_id and tenant.client_id_value:
            extra_allowed.add("client_id")
        _check_allowed_columns(root, allowed_columns, extra_allowed)

    # дополнительные RLS-фильтры (например, region для роли).
    # Значение может быть строкой (равенство) или списком (IN — «семейство» значений).
    for col, val in (extra_filters or {}).items():
        if not val:
            continue
        if isinstance(val, (list, tuple, set)):
            _inject_in_filter(root, col, list(val))
        else:
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
