import logging
import os
import threading

import clickhouse_connect

logger = logging.getLogger(__name__)

class ClickHouseClient:
    """Wrapper for ClickHouse connection following best practices."""
    
    def __init__(self):
        self.host = os.getenv("CLICKHOUSE_HOST", "localhost")
        self.port = int(os.getenv("CLICKHOUSE_PORT", "8123"))
        self.username = os.getenv("CLICKHOUSE_USER", "default")
        self.password = os.getenv("CLICKHOUSE_PASSWORD", "")
        self.database = os.getenv("CLICKHOUSE_DB", "default")
        import threading
        self._thread_local = threading.local()
        
    def get_client(self):
        if not hasattr(self._thread_local, "client") or self._thread_local.client is None:
            try:
                self._thread_local.client = clickhouse_connect.get_client(
                    host=self.host,
                    port=self.port,
                    username=self.username,
                    password=self.password,
                    database=self.database
                )
                logger.info(f"Успешное подключение к ClickHouse (поток: {threading.get_ident()}): {self.host}:{self.port}")
            except Exception as e:
                logger.error(f"Ошибка подключения к ClickHouse: {e}")
                raise
        return self._thread_local.client
        
    def execute(self, query: str, parameters: dict = None):
        """Выполняет запрос и возвращает результат."""
        client = self.get_client()
        return client.query(query, parameters=parameters)
        
    def execute_df(self, query: str, parameters: dict = None):
        """Возвращает результат как pandas DataFrame."""
        client = self.get_client()
        return client.query_df(query, parameters=parameters)
        
    def insert_df(self, table: str, df):
        """Batch insert from pandas DataFrame."""
        client = self.get_client()
        client.insert_df(table, df)

    def command(self, query: str, parameters: dict = None):
        """Выполняет DDL/DML команду (CREATE, ALTER, INSERT, etc)."""
        client = self.get_client()
        return client.command(query, parameters=parameters)

    def insert(self, table: str, data: list, column_names: list = None):
        """Вставляет данные в таблицу."""
        client = self.get_client()
        return client.insert(table, data, column_names=column_names)

# Инициализация глобального инстанса
ch_client = ClickHouseClient()
