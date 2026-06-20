import logging
import os

import clickhouse_connect

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ClickhouseOptimizer")

def optimize_schema():
    """
    Применяет ClickHouse Best Practices к текущим таблицам.
    В частности: schema-types-lowcardinality
    """
    logger.info("Начало оптимизации таблицы tax_data по ClickHouse Best Practices...")
    try:
        client = clickhouse_connect.get_client(
            host=os.getenv("CLICKHOUSE_HOST", "localhost"),
            port=int(os.getenv("CLICKHOUSE_PORT", "8123")),
            username=os.getenv("CLICKHOUSE_USER", "default"),
            password=os.getenv("CLICKHOUSE_PASSWORD", ""),
        )
        
        # Переводим колонки с малым числом уникальных значений в LowCardinality(String)
        # Это значительно ускоряет GROUP BY и снижает потребление RAM.
        columns_to_optimize = ['region', 'type']
        
        # Проверяем, существует ли таблица
        tables = [row[0] for row in client.query("SHOW TABLES").result_rows]
        if 'tax_data' not in tables:
            logger.warning("Таблица tax_data не найдена, оптимизация пропущена.")
            return

        # Проверяем существующие колонки
        cols_info = client.query("DESCRIBE TABLE tax_data").result_rows
        
        for col_name, col_type, *_ in cols_info:
            if col_name in columns_to_optimize and col_type == 'String':
                query = f"ALTER TABLE tax_data MODIFY COLUMN {col_name} LowCardinality(String)"
                logger.info(f"Выполнение: {query}")
                client.command(query)
                
        logger.info("✅ Оптимизация схемы успешно завершена.")
        
    except Exception as e:
        logger.error(f"❌ Ошибка при оптимизации: {e}")

if __name__ == "__main__":
    optimize_schema()
