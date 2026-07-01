import logging
import os

logger = logging.getLogger(__name__)


def scan_clickhouse_schema() -> str:
    """
    Динамическое сканирование схемы ClickHouse.
    Вместо хардкода полей в промпте агента, скрипт "ходит" в базу
    и собирает реальную структуру таблиц.
    """
    logger.info("Сканирование схемы базы данных ClickHouse...")
    try:
        import clickhouse_connect

        client = clickhouse_connect.get_client(
            host=os.getenv("CLICKHOUSE_HOST", "localhost"),
            port=int(os.getenv("CLICKHOUSE_PORT", "8123")),
            username=os.getenv("CLICKHOUSE_USER", "default"),
            password=os.getenv("CLICKHOUSE_PASSWORD", ""),
        )
        res_tables = client.query("SHOW TABLES")
        tables = [
            row[0]
            for row in res_tables.result_rows
            if row[0] in ("enterprise_taxes", "saas_metrics", "ecommerce_sales")
        ]

        schema_lines = ["Найдена схема базы данных:"]
        for table in tables:
            schema_lines.append(f"Таблица: {table}")
            res = client.query(f"DESCRIBE TABLE {table}")
            for row in res.result_rows:
                col_name = row[0]
                col_type = row[1]
                schema_lines.append(f"    - {col_name} ({col_type})")
        return "\n".join(schema_lines)
    except Exception as e:
        logger.error(f"Failed to scan schema: {e}")
        # Fallback
        mock_schema = """
        Найдена схема базы данных:
        Таблица: enterprise_taxes
        - transaction_id (UUID)
        - date (Date)
        - taxpayer_inn (String)
        - taxpayer_name (String)
        - region (String)
        - city (String)
        - tax_type (String)
        - amount (Float32)
        - status (String)
        - risk_score (UInt8)
        - has_audit (UInt8)
        - fine_amount (Float32)
        - industry (String)
        """
        return mock_schema


def get_schema_for_prompt() -> str:
    schema_info = scan_clickhouse_schema()
    prompt_context = f"ОБНОВЛЕННАЯ СХЕМА БД ДЛЯ TEXT-TO-SQL:\n{schema_info}\nИспользуйте только эти таблицы и поля при генерации SQL."
    return prompt_context
