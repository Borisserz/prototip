"""SystemAuditLogger — асинхронная запись LLM-вызовов в ClickHouse.

SECURITY FIX: строки больше не интерполируются в SQL через f-string.
Используется ch_client.insert() с параметризованными данными.
"""

from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime

from app.utils.clickhouse_client import ch_client

logger = logging.getLogger("SystemAudit")


class SystemAuditLogger:
    """Логгер системного аудита — все LLM-вызовы пишутся в ClickHouse."""

    def __init__(self):
        # Lazy init: не вызываем CH при импорте — падает если CH не запущен.
        # _init_db() вызывается при первой попытке записи.
        self._initialized = False
        self._init_lock = threading.Lock()

    def _ensure_init(self):
        if self._initialized:
            return
        with self._init_lock:
            if self._initialized:
                return
            try:
                ddl = """
                CREATE TABLE IF NOT EXISTS default.system_audit_logs (
                    timestamp DateTime,
                    agent_name String,
                    model String,
                    prompt_tokens Int32,
                    completion_tokens Int32,
                    duration_ms Int32,
                    error_status String,
                    user_role String
                ) ENGINE = MergeTree()
                ORDER BY timestamp
                """
                ch_client.execute(ddl)
                logger.info("Таблица system_audit_logs успешно инициализирована.")
                self._initialized = True
            except Exception as e:
                logger.error(f"Ошибка создания system_audit_logs: {e}")
                # Не помечаем initialized=True — попробуем ещё раз при следующем вызове

    def log_llm_call_async(
        self,
        agent_name: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        duration_ms: int,
        error_status: str = "",
        user_role: str = "system",
    ):
        """Асинхронно записать LLM-вызов в audit log.

        SECURITY: данные передаются через параметризованный insert —
        никакой интерполяции строк в SQL.
        """

        def _insert():
            try:
                self._ensure_init()
                now = datetime.now(UTC).replace(tzinfo=None)
                # Параметризованный insert — безопасная передача данных
                ch_client.insert(
                    "default.system_audit_logs",
                    [
                        [
                            now,
                            (agent_name or "unknown")[:128],
                            (model or "unknown")[:128],
                            int(prompt_tokens),
                            int(completion_tokens),
                            int(duration_ms),
                            (error_status or "")[:512],
                            (user_role or "system")[:64],
                        ]
                    ],
                    column_names=[
                        "timestamp",
                        "agent_name",
                        "model",
                        "prompt_tokens",
                        "completion_tokens",
                        "duration_ms",
                        "error_status",
                        "user_role",
                    ],
                )
            except Exception as e:
                logger.error(f"Ошибка записи лога аудита в ClickHouse: {e}")

        threading.Thread(target=_insert, daemon=True).start()


audit_logger = SystemAuditLogger()
