"""Реестр клиентов (Phase 6: Multi-tenant / B2B SaaS).

Каждый клиент («tenant») изолирован и привязан к:
  • своему ClickHouse (host/port/db/user/password — пароль шифруется at-rest);
  • своей векторной коллекции (ChromaDB/Qdrant) с семантикой его БД;
  • уникальному JWT-токену (claim client_id) и API-ключу;
  • списку разрешённых таблиц (allowed_tables) и опциональной row-isolation по client_id.

Хранилище реестра — JSON-файл data/tenants/registry.json (инспектируемый, не требует
запущенной БД). Пароли ClickHouse шифруются через app.security (Fernet).

Модуль устойчив: ошибки чтения/записи логируются, не роняя приложение.
"""

from __future__ import annotations

import json
import logging
import secrets
import threading
from dataclasses import asdict, dataclass, field
from datetime import UTC, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger("TenantStore")

REGISTRY_PATH = Path("data/tenants/registry.json")


@dataclass
class ClickHouseConfig:
    host: str = "localhost"
    port: int = 8123
    database: str = "default"
    user: str = "default"
    password_enc: str = ""  # зашифрованный пароль (Fernet)

    def to_public(self) -> dict[str, Any]:
        """Без секрета — для отдачи на фронт."""
        return {"host": self.host, "port": self.port, "database": self.database, "user": self.user}


@dataclass
class Tenant:
    client_id: str
    name: str
    clickhouse: ClickHouseConfig = field(default_factory=ClickHouseConfig)
    vector_collection: str = ""           # личная коллекция семантики
    allowed_tables: list[str] = field(default_factory=list)
    enforce_client_id: bool = False       # жёстко добавлять WHERE client_id = ...
    client_id_value: str = ""             # значение для row-isolation (по умолчанию = client_id)
    api_key: str = ""
    jwt_token: str = ""
    active: bool = True
    created_at: str = ""

    def to_public(self) -> dict[str, Any]:
        """Публичное представление (без зашифрованного пароля)."""
        d = asdict(self)
        d["clickhouse"] = self.clickhouse.to_public()
        return d


def _utcnow_iso() -> str:
    from datetime import datetime

    return datetime.now(UTC).isoformat()


class TenantStore:
    """Singleton-реестр клиентов с JSON-персистентностью."""

    def __init__(self, path: Path = REGISTRY_PATH) -> None:
        self._path = path
        self._lock = threading.RLock()
        self._cache: dict[str, Tenant] = {}
        self._ch_clients: dict[str, Any] = {}
        self._loaded = False

    # ─── персистентность ─────────────────────────────────────────────────────
    def _load(self) -> None:
        if self._loaded:
            return
        try:
            if self._path.exists():
                raw = json.loads(self._path.read_text(encoding="utf-8"))
                for item in raw.get("tenants", []):
                    t = self._from_dict(item)
                    self._cache[t.client_id] = t
            self._loaded = True
        except Exception as e:  # noqa: BLE001
            logger.error("TenantStore: ошибка загрузки реестра: %s", e)
            self._loaded = True

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            data = {"tenants": [self._to_dict(t) for t in self._cache.values()]}
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self._path)
        except Exception as e:  # noqa: BLE001
            logger.error("TenantStore: ошибка сохранения реестра: %s", e)

    @staticmethod
    def _to_dict(t: Tenant) -> dict[str, Any]:
        d = asdict(t)
        d["clickhouse"] = asdict(t.clickhouse)
        return d

    @staticmethod
    def _from_dict(item: dict[str, Any]) -> Tenant:
        ch_raw = item.get("clickhouse")
        ch = ClickHouseConfig(**ch_raw) if ch_raw else ClickHouseConfig()
        return Tenant(
            client_id=item["client_id"],
            name=item.get("name", item["client_id"]),
            clickhouse=ch,
            vector_collection=item.get("vector_collection", ""),
            allowed_tables=item.get("allowed_tables", []),
            enforce_client_id=item.get("enforce_client_id", False),
            client_id_value=item.get("client_id_value", ""),
            api_key=item.get("api_key", ""),
            jwt_token=item.get("jwt_token", ""),
            active=item.get("active", True),
            created_at=item.get("created_at", ""),
        )

    # ─── токены ──────────────────────────────────────────────────────────────
    @staticmethod
    def _issue_jwt(client_id: str) -> str:
        """Долгоживущий JWT с claim client_id (привязка к клиенту)."""
        try:
            from app.auth import create_access_token

            return create_access_token(
                data={"sub": f"tenant:{client_id}", "role": "client", "client_id": client_id},
                expires_delta=timedelta(days=365),
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("TenantStore: не удалось выпустить JWT (%s) — токен пуст.", e)
            return ""

    # ─── CRUD ──────────────────────────────────────────────────────────────────
    def create_tenant(
        self,
        client_id: str,
        name: str,
        ch_host: str = "localhost",
        ch_port: int = 8123,
        ch_database: str = "default",
        ch_user: str = "default",
        ch_password: str = "",
        vector_collection: str | None = None,
        allowed_tables: list[str] | None = None,
        enforce_client_id: bool = False,
        client_id_value: str | None = None,
    ) -> Tenant:
        from app.security import encrypt_data

        with self._lock:
            self._load()
            if client_id in self._cache:
                raise ValueError(f"Клиент '{client_id}' уже существует")

            ch = ClickHouseConfig(
                host=ch_host,
                port=ch_port,
                database=ch_database,
                user=ch_user,
                password_enc=encrypt_data(ch_password) if ch_password else "",
            )
            tenant = Tenant(
                client_id=client_id,
                name=name,
                clickhouse=ch,
                vector_collection=vector_collection or f"semantics_{client_id}",
                allowed_tables=allowed_tables or [],
                enforce_client_id=enforce_client_id,
                client_id_value=client_id_value or client_id,
                api_key=secrets.token_urlsafe(24),
                jwt_token=self._issue_jwt(client_id),
                active=True,
                created_at=_utcnow_iso(),
            )
            self._cache[client_id] = tenant
            self._save()
            logger.info("TenantStore: создан клиент '%s' (%s)", client_id, name)
            return tenant

    def get_tenant(self, client_id: str | None) -> Tenant | None:
        if not client_id:
            return None
        with self._lock:
            self._load()
            return self._cache.get(client_id)

    def resolve_by_api_key(self, api_key: str) -> Tenant | None:
        if not api_key:
            return None
        with self._lock:
            self._load()
            for t in self._cache.values():
                if t.api_key == api_key:
                    return t
        return None

    def list_tenants(self) -> list[Tenant]:
        with self._lock:
            self._load()
            return list(self._cache.values())

    def update_tenant(self, client_id: str, **fields: Any) -> Tenant | None:
        from app.security import encrypt_data

        with self._lock:
            self._load()
            t = self._cache.get(client_id)
            if not t:
                return None
            if "ch_password" in fields:
                pwd = fields.pop("ch_password")
                if pwd:
                    t.clickhouse.password_enc = encrypt_data(pwd)
            for ch_key in ("host", "port", "database", "user"):
                if ch_key in fields:
                    setattr(t.clickhouse, ch_key, fields.pop(ch_key))
            for k, v in fields.items():
                if hasattr(t, k):
                    setattr(t, k, v)
            self._ch_clients.pop(client_id, None)  # сбросить кэш клиента CH
            self._save()
            return t

    def rotate_token(self, client_id: str) -> Tenant | None:
        with self._lock:
            self._load()
            t = self._cache.get(client_id)
            if not t:
                return None
            t.jwt_token = self._issue_jwt(client_id)
            t.api_key = secrets.token_urlsafe(24)
            self._save()
            return t

    def delete_tenant(self, client_id: str) -> bool:
        with self._lock:
            self._load()
            if client_id in self._cache:
                del self._cache[client_id]
                self._ch_clients.pop(client_id, None)
                self._save()
                return True
            return False

    # ─── ClickHouse клиента ──────────────────────────────────────────────────
    def get_clickhouse_client(self, tenant: Tenant):
        """Возвращает clickhouse_connect клиент к ПЕРСОНАЛЬНОМУ ClickHouse клиента."""
        from app.security import decrypt_data

        with self._lock:
            if tenant.client_id in self._ch_clients:
                return self._ch_clients[tenant.client_id]
            import clickhouse_connect

            enc = tenant.clickhouse.password_enc
            pwd = decrypt_data(enc) if enc else ""
            client = clickhouse_connect.get_client(
                host=tenant.clickhouse.host,
                port=tenant.clickhouse.port,
                username=tenant.clickhouse.user,
                password=pwd,
                database=tenant.clickhouse.database,
            )
            self._ch_clients[tenant.client_id] = client
            return client


# Глобальный singleton
tenant_store = TenantStore()
