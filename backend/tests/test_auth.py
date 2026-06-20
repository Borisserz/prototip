"""Тесты безопасности аутентификации (CRITICAL-фиксы).

Покрывают: реальную проверку пароля, отсутствие угадывания роли по имени,
round-trip JWT, require_admin и валидацию SECRET_KEY.
"""
from __future__ import annotations

import importlib

import pytest
from fastapi import HTTPException


@pytest.fixture
def auth(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.delenv("LOCAL_USERS", raising=False)
    import app.auth as _auth
    importlib.reload(_auth)
    return _auth


def test_correct_credentials(auth):
    user = auth.authenticate_user("admin", "admin123")
    assert user is not None
    assert user["role"] == "admin"


def test_wrong_password_rejected(auth):
    # Главный фикс: неверный пароль больше НЕ выдаёт токен.
    assert auth.authenticate_user("admin", "wrong-password") is None


def test_role_not_guessed_by_name(auth):
    # "administrator" не существует в БД → доступ запрещён (раньше давал admin).
    assert auth.authenticate_user("administrator", "anything") is None
    assert auth.authenticate_user("superadmin", "anything") is None


def test_regional_roles(auth):
    assert auth.authenticate_user("grodno", "grodno123")["role"] == "grodno_manager"
    assert auth.authenticate_user("minsk", "minsk123")["role"] == "minsk_manager"


def test_token_round_trip(auth):
    from jose import jwt

    token = auth.create_access_token({"sub": "admin", "role": "admin"})
    decoded = jwt.decode(token, auth.SECRET_KEY, algorithms=[auth.ALGORITHM])
    assert decoded["sub"] == "admin"
    assert decoded["role"] == "admin"
    assert "exp" in decoded


def test_require_admin_blocks_non_admin(auth):
    with pytest.raises(HTTPException) as exc:
        auth.require_admin({"username": "u", "role": "manager"})
    assert exc.value.status_code == 403


def test_require_admin_allows_admin(auth):
    user = {"username": "admin", "role": "admin"}
    assert auth.require_admin(user) == user


def test_production_requires_secret_key(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    import app.auth as _auth
    with pytest.raises(RuntimeError):
        importlib.reload(_auth)
    # вернуть модуль в рабочее состояние для остальных тестов
    monkeypatch.setenv("APP_ENV", "development")
    importlib.reload(_auth)


def test_password_hash_roundtrip(auth):
    h = auth.get_password_hash("s3cret")
    assert auth.verify_password("s3cret", h)
    assert not auth.verify_password("nope", h)
