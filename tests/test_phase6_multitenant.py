"""Тесты Phase 6: SQL-guard, реестр клиентов, build-утилиты."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import sql_guard  # noqa: E402


@dataclass
class _T:
    allowed_tables: list = field(default_factory=lambda: ["sales", "tax_data"])
    enforce_client_id: bool = True
    client_id_value: str = "pivzavod"


# ─── SQL guard ──────────────────────────────────────────────────────────────
def test_select_allowed_and_client_id_injected():
    out = sql_guard.secure_sql("SELECT region FROM tax_data", tenant=_T())
    assert "client_id = 'pivzavod'" in out
    assert "LIMIT" in out.upper()


def test_disallowed_table_blocked():
    with pytest.raises(sql_guard.SqlSecurityError):
        sql_guard.secure_sql("SELECT * FROM secret", tenant=_T())


@pytest.mark.parametrize("sql", [
    "DROP TABLE tax_data",
    "DELETE FROM sales",
    "INSERT INTO sales VALUES (1)",
    "UPDATE sales SET x = 1",
    "ALTER TABLE sales ADD COLUMN y Int32",
    "TRUNCATE TABLE sales",
    "SELECT 1; DROP TABLE sales",
])
def test_mutating_blocked(sql):
    with pytest.raises(sql_guard.SqlSecurityError):
        sql_guard.secure_sql(sql, tenant=_T())


@pytest.mark.parametrize("sql", [
    "SELECT * FROM file('/etc/passwd','CSV')",
    "SELECT * FROM url('http://evil','CSV','a String')",
    "SELECT * FROM remote('host','db.t')",
])
def test_dangerous_functions_blocked(sql):
    with pytest.raises(sql_guard.SqlSecurityError):
        sql_guard.secure_sql(sql, tenant=_T(allowed_tables=[]))


def test_no_tenant_still_validates():
    # без клиента — просто безопасный SELECT + LIMIT, без client_id
    out = sql_guard.secure_sql("SELECT 1 AS x FROM tax_data", tenant=None)
    assert "client_id" not in out
    assert sql_guard.is_safe_select("SELECT 1")
    assert not sql_guard.is_safe_select("DROP TABLE x")


def test_extra_region_filter_applied():
    out = sql_guard.secure_sql("SELECT paid FROM tax_data", tenant=None,
                               extra_filters={"region": "г. Минск"})
    assert "region = 'г. Минск'" in out


# ─── Tenant registry ──────────────────────────────────────────────────────────
def test_tenant_store_crud_and_encryption(tmp_path):
    from core.tenant import TenantStore

    store = TenantStore(path=tmp_path / "registry.json")
    t = store.create_tenant(
        client_id="acme", name="Acme", ch_password="s3cret",
        allowed_tables=["sales"], enforce_client_id=True,
    )
    assert t.client_id == "acme"
    assert t.api_key
    # пароль зашифрован at-rest (не равен исходному)
    assert t.clickhouse.password_enc and t.clickhouse.password_enc != "s3cret"

    # round-trip расшифровки
    from app.security import decrypt_data
    assert decrypt_data(t.clickhouse.password_enc) == "s3cret"

    # персистентность: новый стор читает с диска
    store2 = TenantStore(path=tmp_path / "registry.json")
    got = store2.get_tenant("acme")
    assert got is not None and got.name == "Acme"

    # резолв по api_key
    assert store2.resolve_by_api_key(t.api_key).client_id == "acme"

    # дубликат запрещён
    with pytest.raises(ValueError):
        store.create_tenant(client_id="acme", name="dup")

    # rotate меняет токены
    old_key = t.api_key
    rotated = store.rotate_token("acme")
    assert rotated.api_key != old_key

    # to_public не содержит секрет
    assert "password_enc" not in t.to_public()["clickhouse"]

    # delete
    assert store.delete_tenant("acme") is True
    assert store.get_tenant("acme") is None


# ─── build_tenant pure helpers ──────────────────────────────────────────────────
def test_build_tenant_helpers():
    import importlib.util

    spec = importlib.util.spec_from_file_location("build_tenant", ROOT / "scripts" / "build_tenant.py")
    bt = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bt)

    assert bt.pg_type_to_ch("integer", False) == "Int32"
    assert bt.pg_type_to_ch("bigint", False) == "Int64"
    assert bt.pg_type_to_ch("text", False) == "String"
    assert bt.pg_type_to_ch("numeric", True) == "Nullable(Float64)"

    cols = [{"name": "id", "type": "integer", "nullable": False},
            {"name": "amount", "type": "numeric", "nullable": True}]
    ddl = bt.build_ch_ddl("sales", cols, add_client_id=True)
    assert "client_id String" in ddl and "ORDER BY client_id" in ddl and "amount Nullable(Float64)" in ddl

    compose = bt.render_compose("pivzavod", 8201, "pw", 9201)
    assert "ch_pivzavod" in compose and "8201:8123" in compose

    sem = bt.build_semantics({"sales": cols}, add_client_id=False)
    assert any("amount" in s["content"] and "сумма" in s["content"] for s in sem)
