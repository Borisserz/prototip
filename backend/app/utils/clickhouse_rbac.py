import logging
import os

import clickhouse_connect

logger = logging.getLogger("clickhouse_rbac")


def apply_rbac_policies():
    """Применение политик Row-Level Security и Data Masking в ClickHouse."""
    logger.info("Applying Native ClickHouse RBAC policies...")
    try:
        client = clickhouse_connect.get_client(
            host=os.getenv("CLICKHOUSE_HOST", "localhost"),
            port=int(os.getenv("CLICKHOUSE_PORT", "8123")),
            username=os.getenv("CLICKHOUSE_USER", "default"),
            password=os.getenv("CLICKHOUSE_PASSWORD", ""),
        )

        # 1. Row-Level Security: Минский пользователь видит только Минск
        # В ClickHouse предварительно нужно создать пользователя (например: CREATE USER IF NOT EXISTS minsk_user IDENTIFIED WITH no_password)
        create_user_sql = "CREATE USER IF NOT EXISTS minsk_user IDENTIFIED WITH no_password"
        client.command(create_user_sql)

        row_policy_sql = """
        CREATE ROW POLICY IF NOT EXISTS minsk_region_policy ON tax_data
        FOR SELECT
        USING region = 'Minsk'
        TO minsk_user
        """
        client.command(row_policy_sql)
        logger.info("Row policy 'minsk_region_policy' applied.")

        # 2. Column Masking: Маскирование ИНН (payer_inn) для всех, кроме админа
        # Реализуется через GRANT и View, либо если версия CH позволяет - через Column Policy
        # Для простоты прототипа мы создаем маскирующий view
        create_view_sql = """
        CREATE OR REPLACE VIEW tax_data_masked AS
        SELECT 
            transaction_id,
            type,
            amount,
            period,
            region,
            concat(substring(payer_inn, 1, 2), '***', substring(payer_inn, -2)) AS payer_inn_masked,
            recipient_inn
        FROM tax_data
        """
        client.command(create_view_sql)
        logger.info("Masked view 'tax_data_masked' created.")

    except Exception as e:
        logger.error(f"Failed to apply RBAC policies: {str(e)}")


if __name__ == "__main__":
    apply_rbac_policies()
