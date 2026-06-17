import logging

import clickhouse_connect

logger = logging.getLogger(__name__)

class DbSchemaExtractor:
    """
    Утилита для динамического извлечения плоской схемы ClickHouse.
    """
    
    def __init__(self, host: str = "localhost", port: int = 8123, username: str = "default", password: str = ""):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self._client = None

    def _get_client(self):
        if not self._client:
            self._client = clickhouse_connect.get_client(
                host=self.host,
                port=self.port,
                username=self.username,
                password=self.password
            )
        return self._client

    def extract_schema(self) -> str:
        """
        Подключается к ClickHouse, считывает таблицы и поля.
        Возвращает текстовое представление (Markdown/String),
        которое можно передавать в промпт SqlAgent.
        """
        client = self._get_client()
        logger.info("Extracting ClickHouse schema dynamically...")
        
        # Получаем список пользовательских таблиц
        tables_query = "SELECT name FROM system.tables WHERE database = 'default' AND is_temporary = 0 AND engine != 'View'"
        try:
            tables_result = client.query(tables_query)
            tables = [row[0] for row in tables_result.result_rows]
            
            if not tables:
                return "База данных пуста (нет таблиц)."

            schema_lines = []
            for table in tables:
                schema_lines.append(f"### Таблица: {table}")
                cols_query = f"SELECT name, type, comment FROM system.columns WHERE table = '{table}' AND database = 'default'"
                cols_result = client.query(cols_query)
                
                for row in cols_result.result_rows:
                    col_name = row[0]
                    col_type = row[1]
                    col_comment = row[2] if row[2] else ""
                    
                    line = f"- `{col_name}` ({col_type})"
                    if col_comment:
                        line += f" : {col_comment}"
                    schema_lines.append(line)
                schema_lines.append("")

            return "\n".join(schema_lines)
            
        except Exception as e:
            logger.error(f"Error extracting schema: {e}")
            return f"Ошибка получения схемы БД: {e}"

def get_schema_prompt() -> str:
    """Convenience func to be called by SqlAgent/DataAgent."""
    extractor = DbSchemaExtractor()
    return extractor.extract_schema()
