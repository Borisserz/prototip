"""Центральный модуль хранения артефактов.

Идея: все сгенерированные файлы (PNG-графики, .pptx, .xlsx, PDF, шаблоны)
не только ложатся локально в out/, но и зеркалятся в объектное хранилище MinIO,
откуда их можно отдавать по ссылке (presigned URL).

Полностью опционален и неломающий: при STORAGE_BACKEND=local (по умолчанию)
или при любой ошибке модуль просто возвращает локальный путь и никогда не бросает исключение.

Переменные окружения:
    STORAGE_BACKEND   local | minio          (default: local)
    MINIO_ENDPOINT    host:port внутри сети (default: minio:9000)
    MINIO_ACCESS_KEY  (default: minioadmin)
    MINIO_SECRET_KEY  (default: minioadmin)
    MINIO_SECURE      true | false           (default: false)
    MINIO_BUCKET      базовый бакет          (default: artifacts)
    MINIO_PUBLIC_URL  база URL для браузера (default: http://localhost:9100)
"""

from __future__ import annotations

import logging
import os
from datetime import timedelta
from pathlib import Path

logger = logging.getLogger("Storage")

STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "local").lower()
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "artifacts")
MINIO_PUBLIC_URL = os.getenv("MINIO_PUBLIC_URL", "http://localhost:9100").rstrip("/")

# Стандартные бакеты/префиксы для разных типов артефактов
KNOWN_PREFIXES = ("charts", "presentations", "dashboards", "exports", "documents", "templates")

_client = None


def is_enabled() -> bool:
    return STORAGE_BACKEND == "minio"


def get_client():
    """Ленивая инициализация MinIO-клиента (import minio только при необходимости)."""
    global _client
    if _client is not None:
        return _client
    from minio import Minio  # lazy import

    _client = Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=MINIO_SECURE,
    )
    return _client


def ensure_buckets(buckets: list[str] | None = None) -> None:
    """Создаёт бакет(ы), если их нет. Безопасно при отключённом MinIO."""
    if not is_enabled():
        return
    target = buckets or [MINIO_BUCKET]
    try:
        client = get_client()
        for b in target:
            if not client.bucket_exists(b):
                client.make_bucket(b)
                logger.info("MinIO: создан бакет %s", b)
    except Exception as e:  # неломающее поведение
        logger.warning("MinIO: не удалось создать бакеты: %s", e)


def _guess_content_type(name: str) -> str:
    import mimetypes

    ctype, _ = mimetypes.guess_type(name)
    return ctype or "application/octet-stream"


def upload_file(
    local_path: str | Path,
    object_name: str | None = None,
    bucket: str | None = None,
    content_type: str | None = None,
) -> str | None:
    """Загружает локальный файл в MinIO. Возвращает presigned URL или None."""
    if not is_enabled():
        return None
    p = Path(local_path)
    bucket = bucket or MINIO_BUCKET
    object_name = object_name or p.name
    try:
        ensure_buckets([bucket])
        client = get_client()
        client.fput_object(
            bucket,
            object_name,
            str(p),
            content_type=content_type or _guess_content_type(p.name),
        )
        logger.info("MinIO: загружен %s -> %s/%s", p.name, bucket, object_name)
        return presigned_url(object_name, bucket)
    except Exception as e:
        logger.warning("MinIO: ошибка загрузки %s: %s", p, e)
        return None


def upload_bytes(
    data: bytes,
    object_name: str,
    bucket: str | None = None,
    content_type: str | None = None,
) -> str | None:
    """Загружает сырые байты в MinIO. Возвращает presigned URL или None."""
    if not is_enabled():
        return None
    import io

    bucket = bucket or MINIO_BUCKET
    try:
        ensure_buckets([bucket])
        client = get_client()
        stream = io.BytesIO(data)
        client.put_object(
            bucket,
            object_name,
            stream,
            length=len(data),
            content_type=content_type or _guess_content_type(object_name),
        )
        return presigned_url(object_name, bucket)
    except Exception as e:
        logger.warning("MinIO: ошибка put_object %s: %s", object_name, e)
        return None


def presigned_url(object_name: str, bucket: str | None = None, expires_days: int = 7) -> str | None:
    """Генерирует временную ссылку. Если задан MINIO_PUBLIC_URL — подменяет хост для браузера."""
    if not is_enabled():
        return None
    bucket = bucket or MINIO_BUCKET
    try:
        client = get_client()
        url = client.presigned_get_object(bucket, object_name, expires=timedelta(days=expires_days))
        # Внутри Docker endpoint = minio:9000, но браузеру нужен внешний хост
        if MINIO_PUBLIC_URL:
            scheme = "https://" if MINIO_SECURE else "http://"
            internal = f"{scheme}{MINIO_ENDPOINT}"
            if url.startswith(internal):
                url = MINIO_PUBLIC_URL + url[len(internal) :]
        return url
    except Exception as e:
        logger.warning("MinIO: ошибка presigned_url %s: %s", object_name, e)
        return None


def download_to_path(
    object_name: str,
    dest_path: str | Path,
    bucket: str | None = None,
) -> str | None:
    """Скачивает объект из MinIO в локальный файл. Возвращает путь или None (никогда не падает)."""
    if not is_enabled():
        return None
    bucket = bucket or MINIO_BUCKET
    dest = Path(dest_path)
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        client = get_client()
        client.fget_object(bucket, object_name, str(dest))
        logger.info("MinIO: скачан %s/%s -> %s", bucket, object_name, dest)
        return str(dest)
    except Exception as e:
        logger.warning("MinIO: ошибка fget_object %s: %s", object_name, e)
        return None


def fetch_bytes(object_name: str, bucket: str | None = None) -> bytes | None:
    """Читает объект из MinIO в память. Возвращает bytes или None."""
    if not is_enabled():
        return None
    bucket = bucket or MINIO_BUCKET
    resp = None
    try:
        client = get_client()
        resp = client.get_object(bucket, object_name)
        return resp.read()
    except Exception as e:
        logger.warning("MinIO: ошибка get_object %s: %s", object_name, e)
        return None
    finally:
        try:
            if resp is not None:
                resp.close()
                resp.release_conn()
        except Exception:
            pass


def mirror_artifact(local_path: str | Path, prefix: str = "") -> str:
    """Удобный хелпер для кода-генераторов.

    Если MinIO включён — зеркалит файл в бакет под prefix/ и возвращает URL.
    Иначе (или при ошибке) — возвращает исходный локальный путь (никогда не падает).
    """
    p = Path(local_path)
    if not is_enabled():
        return str(p)
    object_name = f"{prefix.strip('/')}/{p.name}" if prefix else p.name
    url = upload_file(p, object_name=object_name, bucket=MINIO_BUCKET)
    return url or str(p)
