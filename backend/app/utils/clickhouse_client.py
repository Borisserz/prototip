"""ClickHouse connection wrapper с автоматическим переподключением.

Ключевые свойства:
  - Thread-local соединение: каждый поток имеет свой экземпляр (ThreadPoolExecutor-friendly)
  - Ping-health-check: перед возвратом существующего соединения проверяет живость
  - Инвалидация при ошибке: execute/execute_df/command/insert/insert_df при любой
    ошибке устанавливают client=None, чтобы следующий вызов создал свежее соединение
  - Retry для SELECT: SELECT-операции (execute/execute_df) делают одну повторную
    попытку после переподключения; INSERT/command не ретраятся (защита от дублей)
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any

import clickhouse_connect

logger = logging.getLogger(__name__)


class ClickHouseClient:
    """Wrapper for ClickHouse connection с автоматическим reconnect.

    Жизненный цикл соединения:
      get_client()
        → если нет или ping упал → _connect() → сохраняем в thread_local
        → если есть и ping OK    → возвращаем
      execute*():
        → get_client() → query → если ошибка → _invalidate() → [retry для SELECT]
    """

    def __init__(self) -> None:
        self.host = os.getenv("CLICKHOUSE_HOST", "localhost")
        self.port = int(os.getenv("CLICKHOUSE_PORT", "8123"))
        self.username = os.getenv("CLICKHOUSE_USER", "default")
        self.password = os.getenv("CLICKHOUSE_PASSWORD", "")
        self.database = os.getenv("CLICKHOUSE_DB", "default")
        self._thread_local = threading.local()


    def _connect(self) -> Any:
        """Создаёт новое соединение с ClickHouse и кэширует в thread_local."""
        client = clickhouse_connect.get_client(
            host=self.host,
            port=self.port,
            username=self.username,
            password=self.password,
            database=self.database,
        )
        logger.info(
            "ClickHouse connected (thread=%s): %s:%s/%s",
            threading.get_ident(),
            self.host,
            self.port,
            self.database,
        )
        return client

    def _invalidate(self) -> None:
        """Инвалидирует соединение текущего потока.

        После вызова следующий get_client() создаст свежее соединение.
        Попытка явно закрыть старый клиент — best-effort (ошибки игнорируются).
        """
        old = getattr(self._thread_local, "client", None)
        self._thread_local.client = None
        if old is not None:
            try:
                old.close()
            except Exception:  # noqa: BLE001
                pass


    def get_client(self) -> Any:
        """Возвращает активный клиент ClickHouse для текущего потока.

        Логика:
        1. Есть кэшированный клиент → проверяем ping().
           - Ping OK  → возвращаем.
           - Ping упал → инвалидируем, создаём новый.
        2. Нет клиента → создаём новый.
        """
        client = getattr(self._thread_local, "client", None)

        if client is not None:
            try:
                client.ping()
            except Exception as ping_err:  # noqa: BLE001
                logger.warning(
                    "[ClickHouseClient] Stale connection (thread=%s), reconnecting: %s",
                    threading.get_ident(),
                    ping_err,
                )
                self._invalidate()
                client = None

        if client is None:
            try:
                self._thread_local.client = self._connect()
            except Exception as conn_err:
                logger.error("[ClickHouseClient] Connection failed: %s", conn_err)
                raise

        return self._thread_local.client

    def execute(self, query: str, parameters: dict | None = None) -> Any:
        """Выполняет SELECT-запрос и возвращает QueryResult.

        При ошибке: инвалидирует соединение и делает **одну повторную попытку**
        (retry безопасен для SELECT — нет риска дублирования данных).
        """
        try:
            return self.get_client().query(query, parameters=parameters)
        except Exception as first_err:
            logger.warning(
                "[ClickHouseClient] execute failed, reconnecting for retry: %s", first_err
            )
            self._invalidate()
            try:
                return self.get_client().query(query, parameters=parameters)
            except Exception as retry_err:
                logger.error("[ClickHouseClient] execute retry also failed: %s", retry_err)
                self._invalidate()  # retry тоже упал → сбрасываем чтобы следующий вызов был чистым
                raise retry_err from first_err

    def execute_df(self, query: str, parameters: dict | None = None) -> Any:
        """Выполняет SELECT-запрос и возвращает pandas DataFrame.

        При ошибке: инвалидирует соединение и делает одну повторную попытку.
        """
        try:
            return self.get_client().query_df(query, parameters=parameters)
        except Exception as first_err:
            logger.warning(
                "[ClickHouseClient] execute_df failed, reconnecting for retry: %s", first_err
            )
            self._invalidate()
            try:
                return self.get_client().query_df(query, parameters=parameters)
            except Exception as retry_err:
                logger.error("[ClickHouseClient] execute_df retry also failed: %s", retry_err)
                self._invalidate()  # retry тоже упал → сбрасываем
                raise retry_err from first_err

    def insert_df(self, table: str, df: Any) -> None:
        """Batch insert from pandas DataFrame.

        При ошибке: инвалидирует соединение и НЕ делает retry (защита от дублей).
        Следующий вызов автоматически получит свежее соединение через get_client().
        """
        try:
            self.get_client().insert_df(table, df)
        except Exception as err:
            logger.error(
                "[ClickHouseClient] insert_df failed (table=%s), invalidating connection: %s",
                table,
                err,
            )
            self._invalidate()  # следующий вызов получит свежее соединение
            raise

    def command(self, query: str, parameters: dict | None = None) -> Any:
        """Выполняет DDL/DML команду (CREATE, ALTER, INSERT VALUES, etc).

        При ошибке: инвалидирует соединение и НЕ делает retry (DML может дублировать).
        """
        try:
            return self.get_client().command(query, parameters=parameters)
        except Exception as err:
            logger.error("[ClickHouseClient] command failed, invalidating connection: %s", err)
            self._invalidate()
            raise

    def insert(
        self,
        table: str,
        data: list,
        column_names: list | None = None,
    ) -> Any:
        """Вставляет данные в таблицу.

        При ошибке: инвалидирует соединение и НЕ делает retry (защита от дублей).
        """
        try:
            return self.get_client().insert(table, data, column_names=column_names)
        except Exception as err:
            logger.error(
                "[ClickHouseClient] insert failed (table=%s), invalidating connection: %s",
                table,
                err,
            )
            self._invalidate()
            raise


# Инициализация глобального инстанса
ch_client = ClickHouseClient()
