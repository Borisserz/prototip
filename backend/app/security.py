"""Шифрование секретов.

Ключ Fernet берётся из окружения APP_SECRET_ENCRYPTION_KEY, иначе из файла
secrets/.fernet_key (создаётся при первом запуске). Это обеспечивает СТАБИЛЬНОСТЬ
ключа между перезапусками — иначе зашифрованные пароли ClickHouse клиентов нельзя
будет расшифровать после рестарта.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from cryptography.fernet import Fernet

logger = logging.getLogger("security")


def _load_or_create_key() -> bytes:
    # 1. Переменная окружения (приоритет для production)
    env_key = os.getenv("APP_SECRET_ENCRYPTION_KEY")
    if env_key:
        return env_key.encode() if isinstance(env_key, str) else env_key

    # 2. Файл (стабильный ключ между перезапусками в dev/on-prem)
    key_path = Path(os.getenv("SECRET_KEY_FILE", "secrets/.fernet_key"))
    try:
        if key_path.exists():
            return key_path.read_bytes().strip()
        key = Fernet.generate_key()
        key_path.parent.mkdir(parents=True, exist_ok=True)
        key_path.write_bytes(key)
        logger.info("Сгенерирован новый ключ шифрования: %s", key_path)
        return key
    except Exception as e:  # noqa: BLE001
        # 3. Fallback: эфемерный ключ (только на время процесса)
        logger.warning("Не удалось сохранить ключ шифрования (%s) — использую эфемерный.", e)
        return Fernet.generate_key()


SECRET_ENCRYPTION_KEY = _load_or_create_key()
cipher_suite = Fernet(SECRET_ENCRYPTION_KEY)


def encrypt_data(data: str) -> str:
    if data is None:
        return ""
    return cipher_suite.encrypt(data.encode()).decode()


def decrypt_data(encrypted_data: str) -> str:
    if not encrypted_data:
        return ""
    return cipher_suite.decrypt(encrypted_data.encode()).decode()
