"""Тесты per-tenant user store (core.tenant_users) на in-memory фейке ClickHouse."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import tenant_users  # noqa: E402


class _Res:
    def __init__(self, column_names, result_rows):
        self.column_names = column_names
        self.result_rows = result_rows


class _FakeCH:
    """Эмулирует insert + argMax-чтение актуального состояния пользователей."""

    def __init__(self):
        self.rows: list[dict] = []

    def command(self, *a, **k):
        return None

    def insert(self, table, data, column_names=None):
        for row in data:
            self.rows.append(dict(zip(column_names, row)))

    def execute(self, query, parameters=None):
        # последний рекорд на (client_id, username) по порядку вставки (=updated_at)
        latest: dict[tuple, dict] = {}
        for r in self.rows:
            latest[(r["client_id"], r["username"])] = r
        cols = [
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
        ]
        out = [[r.get(c) for c in cols] for r in latest.values()]
        return _Res(cols, out)


@pytest.fixture
def fake_ch(monkeypatch):
    ch = _FakeCH()
    monkeypatch.setattr(tenant_users, "_ch", lambda: ch)
    tenant_users._invalidate()
    yield ch
    tenant_users._invalidate()


def test_create_and_list_user(fake_ch):
    u = tenant_users.create_user(
        "pivzavod",
        "ivan",
        "secret123",
        role="manager",
        allowed_tables=["sales"],
        allowed_columns=["region", "paid"],
        rls_filters={"region": ["Гродненская область"]},
        can_dashboard=True,
        can_presentation=False,
    )
    assert u["username"] == "ivan"
    assert "password_hash" not in u
    users = tenant_users.list_users("pivzavod")
    assert len(users) == 1 and users[0]["username"] == "ivan"
    assert users[0]["can_presentation"] is False
    assert users[0]["rls_filters"] == {"region": ["Гродненская область"]}


def test_duplicate_username_blocked(fake_ch):
    tenant_users.create_user("pivzavod", "ivan", "secret123")
    with pytest.raises(ValueError):
        tenant_users.create_user("portnaya", "ivan", "secret123")


def test_max_users_limit(fake_ch):
    tenant_users.create_user("pivzavod", "u1", "secret123", max_users=2)
    tenant_users.create_user("pivzavod", "u2", "secret123", max_users=2)
    with pytest.raises(ValueError):
        tenant_users.create_user("pivzavod", "u3", "secret123", max_users=2)


def test_get_permissions(fake_ch):
    tenant_users.create_user(
        "pivzavod",
        "petr",
        "secret123",
        allowed_tables=["orders"],
        allowed_columns=["amount"],
        can_dashboard=False,
    )
    perms = tenant_users.get_user_permissions("pivzavod", "petr")
    assert perms["allowed_tables"] == ["orders"]
    assert perms["allowed_columns"] == ["amount"]
    assert perms["can_dashboard"] is False
    # для другого блока прав нет
    assert tenant_users.get_user_permissions("portnaya", "petr") is None


def test_authenticate_lookup(fake_ch):
    from app.auth import verify_password

    tenant_users.create_user("pivzavod", "anna", "topsecret")
    auth = tenant_users.get_user_auth("anna")
    assert auth["client_id"] == "pivzavod"
    assert verify_password("topsecret", auth["password_hash"])


def test_update_user(fake_ch):
    tenant_users.create_user("pivzavod", "kate", "secret123", role="manager")
    updated = tenant_users.update_user("pivzavod", "kate", role="analyst", can_presentation=False)
    assert updated["role"] == "analyst"
    assert updated["can_presentation"] is False
    perms = tenant_users.get_user_permissions("pivzavod", "kate")
    assert perms["role"] == "analyst"


def test_delete_user(fake_ch):
    tenant_users.create_user("pivzavod", "temp", "secret123")
    assert tenant_users.count_active_users("pivzavod") == 1
    assert tenant_users.delete_user("pivzavod", "temp") is True
    assert tenant_users.list_users("pivzavod") == []
    assert tenant_users.count_active_users("pivzavod") == 0
    # удаление несуществующего
    assert tenant_users.delete_user("pivzavod", "ghost") is False


def test_count_active_excludes_deactivated(fake_ch):
    tenant_users.create_user("pivzavod", "a", "secret123")
    tenant_users.create_user("pivzavod", "b", "secret123")
    tenant_users.update_user("pivzavod", "b", active=False)
    assert tenant_users.count_active_users("pivzavod") == 1
