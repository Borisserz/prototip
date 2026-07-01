"""Аутентификация и авторизация. SECRET_KEY из енва, пароли проверяются через bcrypt."""

from __future__ import annotations

import logging
import os
import secrets as _secrets
from datetime import UTC, datetime, timedelta

import bcrypt
import requests
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt

logger = logging.getLogger("auth")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))
APP_ENV = os.getenv("APP_ENV", "development").lower()


def _load_secret_key() -> str:
    """Загружает SECRET_KEY из окружения.

    В production ключ обязателен и должен быть ≥32 символов, иначе RuntimeError.
    В dev генерируем эфемерный ключ (не переживёт рестарт).
    """
    key = os.getenv("SECRET_KEY", "").strip()
    if not key:
        if APP_ENV == "production":
            raise RuntimeError(
                "SECRET_KEY не задан. В production задайте переменную окружения "
                "SECRET_KEY длиной ≥32 символов (например: `openssl rand -hex 32`)."
            )
        key = _secrets.token_urlsafe(48)
        logger.warning(
            "SECRET_KEY не задан — сгенерирован эфемерный ключ для dev. "
            "JWT-токены станут невалидными после рестарта. Задайте SECRET_KEY в .env."
        )
        return key

    if len(key) < 32:
        msg = (
            f"SECRET_KEY слишком короткий ({len(key)} симв.). Требуется ≥32 символов "
            "(≥256 бит). Сгенерируйте: `openssl rand -hex 32`."
        )
        if APP_ENV == "production":
            raise RuntimeError(msg)
        logger.warning(msg)
    return key


SECRET_KEY = _load_secret_key()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


# демо-пользователи для окружения dev. Задать свои хеши через LOCAL_USERS в .env (JSON).
# admin / admin123, user1 / user123  — тестовые учётки, не в проде
_DEMO_USERS: dict[str, dict[str, str]] = {
    "admin": {
        "hash": "$2b$12$uBqLz9xmxVqv5HOVB.nsD.oSHKiuwEv8qXkVrFe30j6adBmyOcjLK",
        "role": "admin",
    },
    "user1": {
        "hash": "$2b$12$h7iJS6JRnrKfOxGD6n7S9ekniXhYlqRtTdu/oFDe/4qbVH94AN2GS",
        "role": "manager",
    },
}


def _load_users() -> dict[str, dict[str, str]]:
    raw = os.getenv("LOCAL_USERS", "").strip()
    if raw:
        import json

        try:
            data = json.loads(raw)
            return {
                k.lower(): {"hash": v["hash"], "role": v.get("role", "manager")}
                for k, v in data.items()
            }
        except Exception as e:  # noqa: BLE001
            logger.error("LOCAL_USERS невалиден (%s) — использую демо-пользователей.", e)
    if APP_ENV == "production":
        logger.warning(
            "LOCAL_USERS не задан в production — активны демо-пользователи с известными "
            "паролями. Это небезопасно: задайте LOCAL_USERS или интеграцию с Keycloak."
        )
    return dict(_DEMO_USERS)


LOCAL_USERS_DB = _load_users()


def list_known_roles() -> list[str]:
    """Список ролей пользователей (для админ-консоли RLS). Без служебных admin/manager."""
    roles = {u.get("role", "manager") for u in LOCAL_USERS_DB.values()}
    roles.discard("admin")
    return sorted(roles)


def authenticate_user(username: str, password: str) -> dict | None:
    """Проверяет логин/пароль. Возвращает {username, role, client_id?} или None.

    Порядок проверки:
      1. Пользователи блоков (per-tenant users в ClickHouse) — приоритет: они привязаны
         к конкретному client_id, и токен должен нести этот client_id.
      2. Локальная БД (LOCAL_USERS / демо) — глобальные пользователи без привязки к блоку.

    При недоступности ClickHouse инициализация БД тихо пропускается (безопасное игнорирование ошибок).
    """
    uname = (username or "").lower()

    # 1. Пользователи блока (tenant users)
    try:
        from core.tenant_users import get_user_auth

        tu = get_user_auth(uname)
        if tu and tu.get("password_hash") and verify_password(password, tu["password_hash"]):
            return {
                "username": tu.get("username", uname),
                "role": tu.get("role", "manager"),
                "client_id": tu.get("client_id", ""),
            }
    except Exception as exc:  # noqa: BLE001
        logger.debug("authenticate_user: проверка tenant_users пропущена (%s)", exc)

    # 2. Локальная БД (глобальные пользователи)
    user = LOCAL_USERS_DB.get(uname)
    if not user or not verify_password(password, user["hash"]):
        return None
    return {"username": uname, "role": user["role"]}


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(UTC) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


KEYCLOAK_URL = os.getenv("KEYCLOAK_URL", "http://localhost:8080")
REALM = os.getenv("KEYCLOAK_REALM", "master")
JWKS_URL = f"{KEYCLOAK_URL}/realms/{REALM}/protocol/openid-connect/certs"

# auto_error=False: токен может прийти из Authorization-заголовка, httpOnly-cookie или WS query-параметра
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login", auto_error=False)

# Имя httpOnly-cookie с access-токеном (используется и backend'ом, и WS).
COOKIE_NAME = "access_token"


def decode_token(token: str) -> dict:
    """Валидирует JWT и возвращает {username, role, client_id}.

    Сначала пытается проверить как Keycloak RS256 (через JWKS), затем —
    как локальный HS256. Бросает ``ValueError`` при невалидном токене.
    """
    payload: dict | None = None
    try:
        # 1. Попытка проверить токен через Keycloak (RS256).
        jwks = requests.get(JWKS_URL, timeout=2).json()
        unverified_header = jwt.get_unverified_header(token)
        rsa_key = {}
        for key in jwks.get("keys", []):
            if key["kid"] == unverified_header["kid"]:
                rsa_key = {
                    "kty": key["kty"],
                    "kid": key["kid"],
                    "use": key["use"],
                    "n": key["n"],
                    "e": key["e"],
                }
        if rsa_key:
            payload = jwt.decode(token, rsa_key, algorithms=["RS256"], audience="account")
        else:
            raise ValueError("Key not found in JWKS")
    except (requests.RequestException, KeyError, ValueError, JWTError):
        # 2. резервный вариант на локальный HS256-JWT (dev/прототип).
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        except JWTError as exc:
            raise ValueError("Не удалось валидировать токен") from exc

    username = payload.get("sub", payload.get("preferred_username"))
    if username is None:
        raise ValueError("В токене отсутствует subject (sub)")

    return {
        "username": username,
        "role": payload.get("role", "manager"),
        "client_id": payload.get("client_id"),
    }


def get_user_from_token(token: str | None) -> dict | None:
    """Безопасный декод токена для WebSocket: возвращает None вместо исключения.

    Используется в `/ws/chat` до `accept()` — позволяет отклонить неавторизованное
    подключение, не роняя соединение исключением.
    """
    if not token:
        return None
    try:
        return decode_token(token)
    except Exception:  # noqa: BLE001 — намеренно не пускаем дальше на WS-хендшейке
        return None


def get_current_user(
    request: Request,
    token: str | None = Depends(oauth2_scheme),
) -> dict:
    """Зависимость FastAPI: достаёт токен из Authorization-заголовка или httpOnly-cookie."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    raw_token = token or request.cookies.get(COOKIE_NAME)
    if not raw_token:
        raise credentials_exception
    try:
        return decode_token(raw_token)
    except ValueError:
        raise credentials_exception from None


def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """Гард: пропускает только пользователей с ролью admin."""
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступ только для администратора.",
        )
    return current_user
