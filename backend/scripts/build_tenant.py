#!/usr/bin/env python3
"""Сборка изолированного клиента (Phase 6: Multi-tenant B2B).

Принимает Read-Only креды Postgres клиента и автоматически:
  1. Делает выборку схемы и данных нужных таблиц из Postgres.
  2. Генерирует docker-compose для ПЕРСОНАЛЬНОГО ClickHouse-контейнера клиента
     (`docker init`) и поднимает его (если не --no-docker / --dry-run).
  3. Переливает данные в ClickHouse клиента (DDL + INSERT, с маппингом типов).
  4. Автоматически генерирует семантические вектора по названиям колонок
     (понимание БД для LLM) в личную коллекцию клиента.
  5. Регистрирует клиента в реестре (core.tenant): личный ClickHouse, личная
     коллекция семантики и уникальный JWT-токен.

Пример:
  python scripts/build_tenant.py \
      --client-id pivzavod --name "Пивзавод" \
      --pg-dsn "postgresql://ro_user:pwd@db.client:5432/erp" \
      --tables sales,products --ch-port 8201 --add-client-id --dry-run

Скрипт идемпотентен и поддерживает --dry-run (печатает план без выполнения).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# корень проекта в PYTHONPATH
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("build_tenant")

# ─── маппинг типов Postgres -> ClickHouse ──────────────────────────────────────
PG_TO_CH = {
    "smallint": "Int32", "integer": "Int32", "int": "Int32", "int2": "Int32", "int4": "Int32",
    "bigint": "Int64", "int8": "Int64",
    "numeric": "Float64", "decimal": "Float64", "real": "Float64", "double precision": "Float64",
    "float4": "Float64", "float8": "Float64", "money": "Float64",
    "boolean": "UInt8", "bool": "UInt8",
    "date": "Date",
    "timestamp": "DateTime", "timestamp without time zone": "DateTime",
    "timestamp with time zone": "DateTime", "timestamptz": "DateTime",
}


def pg_type_to_ch(pg_type: str, nullable: bool) -> str:
    base = PG_TO_CH.get(pg_type.lower().strip(), "String")
    return f"Nullable({base})" if nullable and base != "String" else base


# ─── Postgres: схема и данные ──────────────────────────────────────────────────
def connect_pg(dsn: str):
    try:
        import psycopg2

        return psycopg2.connect(dsn)
    except Exception:
        # fallback на чистый pg8000
        import urllib.parse as up

        import pg8000.dbapi

        u = up.urlparse(dsn)
        return pg8000.dbapi.connect(
            user=up.unquote(u.username or ""),
            password=up.unquote(u.password or ""),
            host=u.hostname or "localhost",
            port=u.port or 5432,
            database=(u.path or "/").lstrip("/"),
        )


def list_tables(conn, schema: str) -> list[str]:
    cur = conn.cursor()
    cur.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = %s AND table_type = 'BASE TABLE' ORDER BY table_name",
        (schema,),
    )
    return [r[0] for r in cur.fetchall()]


def get_columns(conn, schema: str, table: str) -> list[dict]:
    cur = conn.cursor()
    cur.execute(
        "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
        "WHERE table_schema = %s AND table_name = %s ORDER BY ordinal_position",
        (schema, table),
    )
    return [{"name": r[0], "type": r[1], "nullable": r[2] == "YES"} for r in cur.fetchall()]


def fetch_rows(conn, schema: str, table: str, limit: int | None) -> tuple[list[str], list[tuple]]:
    cur = conn.cursor()
    q = f'SELECT * FROM "{schema}"."{table}"'
    if limit:
        q += f" LIMIT {int(limit)}"
    cur.execute(q)
    cols = [d[0] for d in cur.description]
    return cols, cur.fetchall()


# ─── ClickHouse DDL и docker-compose ───────────────────────────────────────────
def build_ch_ddl(table: str, columns: list[dict], add_client_id: bool) -> str:
    cols_sql = []
    if add_client_id:
        cols_sql.append("    client_id String")
    for c in columns:
        cols_sql.append(f"    {c['name']} {pg_type_to_ch(c['type'], c['nullable'])}")
    order_key = "client_id" if add_client_id else (columns[0]["name"] if columns else "tuple()")
    return (
        f"CREATE TABLE IF NOT EXISTS {table} (\n"
        + ",\n".join(cols_sql)
        + f"\n) ENGINE = MergeTree() ORDER BY {order_key};"
    )


def render_compose(client_id: str, ch_port: int, password: str, native_port: int) -> str:
    return f"""# Авто-сгенерировано build_tenant.py для клиента '{client_id}'
services:
  clickhouse_{client_id}:
    image: clickhouse/clickhouse-server:latest
    container_name: ch_{client_id}
    ports:
      - "{ch_port}:8123"
      - "{native_port}:9000"
    environment:
      - CLICKHOUSE_DB=tenant_{client_id}
      - CLICKHOUSE_USER=default
      - CLICKHOUSE_PASSWORD={password}
    volumes:
      - ch_{client_id}_data:/var/lib/clickhouse
    healthcheck:
      test: ["CMD", "wget", "--no-verbose", "--tries=1", "--spider", "http://localhost:8123/ping"]
      interval: 10s
      timeout: 5s
      retries: 10

volumes:
  ch_{client_id}_data:
"""


def docker_up(compose_path: Path) -> None:
    import subprocess
    import time

    logger.info("docker compose up для %s ...", compose_path)
    subprocess.run(["docker", "compose", "-f", str(compose_path), "up", "-d"], check=True)
    time.sleep(8)  # дать контейнеру подняться


# ─── семантика по названиям колонок ────────────────────────────────────────────
SEMANTIC_HINTS = {
    "amount": "сумма", "sum": "сумма", "total": "итого", "price": "цена", "cost": "стоимость",
    "qty": "количество", "quantity": "количество", "count": "количество",
    "date": "дата", "period": "период", "created": "дата создания", "ts": "временная метка",
    "region": "регион", "city": "город", "tax": "налог", "debt": "задолженность",
    "paid": "оплачено", "accrued": "начислено", "name": "наименование", "id": "идентификатор",
    "product": "продукт", "client": "клиент", "customer": "покупатель", "revenue": "выручка",
}


def describe_column(table: str, col: str, ch_type: str) -> str:
    low = col.lower()
    hint = next((ru for en, ru in SEMANTIC_HINTS.items() if en in low), "")
    suffix = f" — {hint}" if hint else ""
    return f"Таблица '{table}', колонка '{col}' (тип {ch_type}){suffix}."


def build_semantics(tables: dict[str, list[dict]], add_client_id: bool) -> list[dict]:
    out = []
    for table, columns in tables.items():
        prefix = [{"name": "client_id", "type": "text", "nullable": False}] if add_client_id else []
        cols = prefix + columns
        for c in cols:
            ch_type = pg_type_to_ch(c["type"], c["nullable"])
            desc = describe_column(table, c["name"], ch_type)
            out.append({"table": table, "column": c["name"], "content": desc})
    return out


def index_semantics(semantics: list[dict], collection: str, ch_client_obj) -> str:
    """Индексирует семантику колонок в личную коллекцию клиента (ClickHouse-вектора).

    Использует ту же модель эмбеддингов, что и основной RAG (all-MiniLM-L6-v2 с
    fallback). Возвращает строку-резюме. Полностью устойчив к отсутствию модели.
    """
    try:
        from app.services.rag_service import get_embeddings_model

        emb_model = get_embeddings_model()
    except Exception as e:  # noqa: BLE001
        logger.warning("Эмбеддинги недоступны (%s) — пропускаю индексацию семантики.", e)
        return "skipped (no embeddings)"

    ch_client_obj.command(
        f"CREATE TABLE IF NOT EXISTS {collection} ("
        "id String, table_name String, column_name String, content String, embedding Array(Float32)"
        ") ENGINE = MergeTree() ORDER BY id"
    )
    import uuid

    data = []
    for s in semantics:
        emb = emb_model.embed_query(s["content"])
        data.append([uuid.uuid4().hex, s["table"], s["column"], s["content"], emb])
    if data:
        ch_client_obj.insert(
            collection, data,
            column_names=["id", "table_name", "column_name", "content", "embedding"]
        )
    return f"{len(data)} колонок проиндексировано в '{collection}'"


# ─── основной поток ─────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(description="Сборка изолированного B2B-клиента (Phase 6)")
    ap.add_argument("--client-id", required=True, help="Слаг клиента (например, pivzavod)")
    ap.add_argument("--name", required=True, help="Отображаемое имя клиента")
    ap.add_argument("--pg-dsn", required=True, help="Read-Only DSN Postgres клиента")
    ap.add_argument("--schema", default="public", help="Схема Postgres (по умолч. public)")
    ap.add_argument("--tables", default="", help="Список таблиц через запятую (пусто = все)")
    ap.add_argument("--row-limit", type=int, default=None, help="Лимит строк на таблицу")
    ap.add_argument("--ch-host", default="localhost", help="Хост ClickHouse клиента")
    ap.add_argument("--ch-port", type=int, default=8201, help="Host-порт HTTP ClickHouse клиента")
    ap.add_argument("--ch-native-port", type=int, default=9201, help="Host-порт native ClickHouse")
    ap.add_argument("--ch-password", default="", help="Пароль ClickHouse клиента")
    ap.add_argument("--add-client-id", action="store_true", help="Колонка client_id (RLS)")
    ap.add_argument("--no-docker", action="store_true", help="Не поднимать docker-контейнер")
    ap.add_argument("--dry-run", action="store_true", help="Только показать план, без выполнения")
    args = ap.parse_args()

    cid = args.client_id
    ch_db = f"tenant_{cid}"
    collection = f"semantics_{cid}"
    out_dir = ROOT / "data" / "tenants"
    out_dir.mkdir(parents=True, exist_ok=True)
    compose_path = out_dir / f"docker-compose.{cid}.yml"

    # 1. Postgres: схема и данные
    logger.info("Подключение к Postgres клиента ...")
    conn = connect_pg(args.pg_dsn)
    requested = [t.strip() for t in args.tables.split(",") if t.strip()]
    tables = requested or list_tables(conn, args.schema)
    logger.info("Таблицы для слепка: %s", ", ".join(tables))

    schema_map: dict[str, list[dict]] = {}
    data_map: dict[str, tuple[list[str], list[tuple]]] = {}
    for tbl in tables:
        schema_map[tbl] = get_columns(conn, args.schema, tbl)
        if not args.dry_run:
            data_map[tbl] = fetch_rows(conn, args.schema, tbl, args.row_limit)

    # 2. docker-compose ClickHouse клиента
    compose_yaml = render_compose(
        cid, args.ch_port, args.ch_password or "ch_pass", args.ch_native_port)
    ddls = {t: build_ch_ddl(t, cols, args.add_client_id) for t, cols in schema_map.items()}
    semantics = build_semantics(schema_map, args.add_client_id)

    if args.dry_run:
        print("\n===== DRY-RUN: план сборки клиента =====")
        print(f"client_id={cid}  name={args.name}  ch_db={ch_db}  collection={collection}")
        print(f"\n--- {compose_path} ---\n{compose_yaml}")
        for t, ddl in ddls.items():
            print(f"\n--- DDL ClickHouse: {t} ---\n{ddl}")
        print(f"\n--- Семантика ({len(semantics)} колонок) ---")
        for s in semantics[:30]:
            print("  •", s["content"])
        print("\n(dry-run: ничего не выполнено, контейнер не поднят, клиент не зарегистрирован)")
        return 0

    # запись compose
    compose_path.write_text(compose_yaml, encoding="utf-8")
    logger.info("docker-compose записан: %s", compose_path)
    if not args.no_docker:
        docker_up(compose_path)

    # 3. Перелив данных в ClickHouse клиента
    import clickhouse_connect

    ch = clickhouse_connect.get_client(
        host=args.ch_host, port=args.ch_port, username="default",
        password=args.ch_password, database="default",
    )
    ch.command(f"CREATE DATABASE IF NOT EXISTS {ch_db}")
    ch.close()
    ch = clickhouse_connect.get_client(
        host=args.ch_host, port=args.ch_port, username="default",
        password=args.ch_password, database=ch_db,
    )
    for tbl in tables:
        ch.command(ddls[tbl])
        cols, rows = data_map[tbl]
        if args.add_client_id:
            cols = ["client_id", *cols]
            rows = [(cid, *r) for r in rows]
        if rows:
            ch.insert(tbl, [list(r) for r in rows], column_names=cols)
        logger.info("Таблица %s: загружено %d строк", tbl, len(rows))

    # 4. Семантические вектора
    sem_summary = index_semantics(semantics, collection, ch)
    logger.info("Семантика: %s", sem_summary)
    (out_dir / f"{cid}_semantics.json").write_text(
        json.dumps(semantics, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 5. Регистрация клиента
    from core.tenant import tenant_store

    tenant = tenant_store.create_tenant(
        client_id=cid, name=args.name,
        ch_host=args.ch_host, ch_port=args.ch_port, ch_database=ch_db,
        ch_password=args.ch_password, vector_collection=collection,
        allowed_tables=tables, enforce_client_id=args.add_client_id, client_id_value=cid,
    )
    print("\n===== Клиент собран и зарегистрирован =====")
    print(f"client_id   : {tenant.client_id}")
    print(f"ClickHouse  : {args.ch_host}:{args.ch_port}/{ch_db}")
    print(f"collection  : {collection}")
    print(f"allowed     : {', '.join(tables)}")
    print(f"api_key     : {tenant.api_key}")
    print(f"JWT token   : {tenant.jwt_token}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
