"""Сид демо-окружения: один блок (tenant) + «богоподобный» пользователь.

Создаёт:
  • один блок-клиент (по умолчанию client_id="demo"), указывающий на основной
    ClickHouse (CLICKHOUSE_* из окружения) — без построчной изоляции, со всеми таблицами;
  • пользователя блока "god" с ПОЛНЫМ доступом ко всей БД (allowed_tables=[] и
    allowed_columns=[] => без ограничений), с правами на дашборды и презентации.

Полезно для локального тестирования: вход god/god123 → видит весь DWH блока.

Запуск (внутри backend-контейнера или venv):
    python -m scripts.seed_demo                 # создать/обновить блок + god
    python -m scripts.seed_demo --wipe-users    # + удалить всех прочих юзеров блоков
    GOD_PASSWORD=secret python -m scripts.seed_demo

Локальные демо-логины приложения (auth.py): admin/admin123, user1/user123.
Их трогать не нужно — они вне ClickHouse.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Сид демо-блока и god-пользователя")
    parser.add_argument("--client-id", default=os.getenv("DEMO_CLIENT_ID", "demo"))
    parser.add_argument("--name", default=os.getenv("DEMO_CLIENT_NAME", "Демо-блок"))
    parser.add_argument("--god-username", default=os.getenv("GOD_USERNAME", "god"))
    parser.add_argument("--god-password", default=os.getenv("GOD_PASSWORD", "god123"))
    parser.add_argument(
        "--wipe-users",
        action="store_true",
        help="Удалить всех прочих пользователей блоков (оставить только god)",
    )
    args = parser.parse_args()

    from core import tenant_users
    from core.tenant import tenant_store

    ch_host = os.getenv("CLICKHOUSE_HOST", "localhost")
    ch_port = int(os.getenv("CLICKHOUSE_PORT", "8123"))
    ch_db = os.getenv("CLICKHOUSE_DB", "default")
    ch_user = os.getenv("CLICKHOUSE_USER", "default")
    ch_pass = os.getenv("CLICKHOUSE_PASSWORD", "")

    # 1. Блок-клиент: один, указывает на основной ClickHouse, без изоляции.
    tenant = tenant_store.get_tenant(args.client_id)
    if tenant is None:
        tenant = tenant_store.create_tenant(
            client_id=args.client_id,
            name=args.name,
            ch_host=ch_host,
            ch_port=ch_port,
            ch_database=ch_db,
            ch_user=ch_user,
            ch_password=ch_pass,
            allowed_tables=[],  # пусто = все таблицы блока
            enforce_client_id=False,  # без построчной изоляции — god видит всё
            max_users=50,
        )
        print(f"[seed] создан блок '{tenant.client_id}' ({tenant.name})")
    else:
        tenant_store.update_tenant(
            args.client_id,
            host=ch_host,
            port=ch_port,
            database=ch_db,
            user=ch_user,
            allowed_tables=[],
            enforce_client_id=False,
            active=True,
        )
        if ch_pass:
            tenant_store.update_tenant(args.client_id, ch_password=ch_pass)
        print(f"[seed] блок '{args.client_id}' уже существует — обновлён")

    # 2. ClickHouse-таблица пользователей блоков.
    tenant_users.ensure_table()

    # 3. (опц.) удалить всех прочих пользователей блоков.
    if args.wipe_users:
        removed = 0
        for t in tenant_store.list_tenants():
            for u in tenant_users.list_users(t.client_id):
                if (
                    u["username"].lower() == args.god_username.lower()
                    and t.client_id == args.client_id
                ):
                    continue
                if tenant_users.delete_user(t.client_id, u["username"]):
                    removed += 1
        print(f"[seed] удалено прочих пользователей блоков: {removed}")

    # 4. God-пользователь: полный доступ ко всей БД блока.
    existing = tenant_users.get_user_permissions(args.client_id, args.god_username)
    if existing is None:
        tenant_users.create_user(
            client_id=args.client_id,
            username=args.god_username,
            password=args.god_password,
            role="manager",
            allowed_tables=[],  # все таблицы
            allowed_columns=[],  # все колонки
            rls_filters={},  # без построчных ограничений
            can_dashboard=True,
            can_presentation=True,
            max_users=0,  # лимит не применяем для сид-юзера
        )
        print(f"[seed] создан god-пользователь '{args.god_username}' (пароль: {args.god_password})")
    else:
        tenant_users.update_user(
            args.client_id,
            args.god_username,
            allowed_tables=[],
            allowed_columns=[],
            rls_filters={},
            can_dashboard=True,
            can_presentation=True,
            active=True,
            password=args.god_password,
        )
        print(
            f"[seed] god-пользователь '{args.god_username}' обновлён (пароль: {args.god_password})"
        )

    print(f"\n[seed] Готово. Вход god/<пароль> → доступ ко всей БД блока '{args.client_id}'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
