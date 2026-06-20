"""Тесты периметра безопасности (P0/P1 hardening).

Покрывают:
- валидацию JWT и извлечение пользователя (P0-1 WS / P0-5 cookie разделяют этот путь);
- безопасный декод токена для WebSocket (get_user_from_token);
- RBAC-гард require_admin (P0 admin endpoints).

Эти тесты не требуют запущенных ClickHouse/Qdrant/LLM — только app.auth.
"""
from __future__ import annotations

import os

import pytest

# Детерминированный ключ для теста (иначе сгенерируется эфемерный).
os.environ.setdefault("SECRET_KEY", "test-secret-key-at-least-32-chars-long-000")
os.environ.setdefault("APP_ENV", "test")

from fastapi import HTTPException  # noqa: E402

from app.auth import (  # noqa: E402
    create_access_token,
    decode_token,
    get_user_from_token,
    require_admin,
)


def test_decode_token_roundtrip():
    token = create_access_token({"sub": "alice", "role": "admin", "client_id": "c1"})
    user = decode_token(token)
    assert user["username"] == "alice"
    assert user["role"] == "admin"
    assert user["client_id"] == "c1"


def test_decode_token_rejects_garbage():
    with pytest.raises(ValueError):
        decode_token("not-a-real-jwt")


def test_get_user_from_token_safe_none():
    # P0-1: на WS-хендшейке невалидный/пустой токен → None (а не исключение).
    assert get_user_from_token(None) is None
    assert get_user_from_token("") is None
    assert get_user_from_token("garbage.token.value") is None


def test_get_user_from_token_valid():
    token = create_access_token({"sub": "bob", "role": "manager"})
    user = get_user_from_token(token)
    assert user is not None
    assert user["username"] == "bob"
    assert user["role"] == "manager"


def test_require_admin_allows_admin():
    assert require_admin({"role": "admin", "username": "root"})["role"] == "admin"


def test_require_admin_blocks_non_admin():
    for role in ("manager", "grodno_manager", "analyst", None):
        with pytest.raises(HTTPException) as exc:
            require_admin({"role": role, "username": "u"})
        assert exc.value.status_code == 403
