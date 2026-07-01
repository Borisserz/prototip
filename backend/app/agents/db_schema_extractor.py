import logging

import clickhouse_connect

logger = logging.getLogger(__name__)


class DbSchemaExtractor:
    """
    Утилита для динамического извлечения плоской схемы ClickHouse.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8123,
        username: str = "default",
        password: str = "",
    ):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self._client = None

    def _get_client(self):
        if not self._client:
            self._client = clickhouse_connect.get_client(
                host=self.host, port=self.port, username=self.username, password=self.password
            )
        return self._client

    def extract_schema(self) -> str:
        """
        Подключается к ClickHouse, считывает таблицы и поля.
        Возвращает текстовое представление (Markdown/String),
        которое можно передавать в промпт SqlAgent.
        """
        logger.info("Extracting ClickHouse schema dynamically...")

        # Получаем список пользовательских таблиц
        tables_query = "SELECT name FROM system.tables WHERE database = 'default' AND is_temporary = 0 AND engine != 'View'"
        try:
            # Подключение тоже внутри try: при недоступности ClickHouse
            # деградируем gracefully (возвращаем текст ошибки), а не роняем агента.
            client = self._get_client()
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


def get_schema_prompt(tenant=None) -> str:
    """Convenience func to be called by SqlAgent/DataAgent.

    FIX 2.4: accepts an optional Tenant so that in multi-tenant mode the schema
    is read from the *tenant's* ClickHouse instance, not always from the shared
    default. Without a tenant the behaviour is unchanged (default ClickHouse).
    """
    if tenant is not None:
        # используем ClickHouse-клиент конкретного тенанта
        try:
            from app.security import decrypt_data

            ch = tenant.clickhouse
            extractor = DbSchemaExtractor(
                host=ch.host,
                port=ch.port,
                username=ch.user,
                password=decrypt_data(ch.password_enc) if ch.password_enc else "",
            )
            logger.info(
                "[DbSchemaExtractor] Extracting schema for tenant '%s' (%s:%s/%s)",
                tenant.client_id,
                ch.host,
                ch.port,
                ch.database,
            )
            return extractor.extract_schema()
        except Exception as e:
            logger.warning(
                "[DbSchemaExtractor] Could not extract tenant '%s' schema: %s — falling back to default",
                getattr(tenant, "client_id", "?"),
                e,
            )
    # фолбэк: шаред ClickHouse по умолчанию
    extractor = DbSchemaExtractor()
    return extractor.extract_schema()
