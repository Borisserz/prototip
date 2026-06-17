import pandas as pd
import clickhouse_connect
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATA_PATH = Path("data/sample.csv")

def seed():
    if not DATA_PATH.exists():
        logger.error(f"Data file not found at {DATA_PATH}")
        return

    logger.info("Reading data/sample.csv...")
    df = pd.read_csv(DATA_PATH)
    
    # Normalize column names for ClickHouse
    df.columns = [c.replace(' ', '_').replace('.', '').lower() for c in df.columns]

    # Convert period to datetime so it fits ClickHouse Date type
    if 'period' in df.columns:
        df['period'] = pd.to_datetime(df['period']).dt.date

    logger.info("Connecting to ClickHouse at localhost:8123...")
    client = clickhouse_connect.get_client(host='localhost', port=8123, username='default', password='')

    logger.info("Creating optimized table 'tax_data'...")
    client.command("DROP TABLE IF EXISTS tax_data")
    
    create_table_sql = """
    CREATE TABLE tax_data (
        period Date,
        region LowCardinality(String),
        tax_type LowCardinality(String),
        accrued Float32,
        paid Float32,
        debt Float32,
        taxpayers UInt32,
        penalties Float32
    ) ENGINE = MergeTree()
    ORDER BY (region, period, tax_type)
    SETTINGS index_granularity = 8192;
    """
    client.command(create_table_sql)

    logger.info(f"Inserting {len(df)} rows into ClickHouse...")
    client.insert_df('tax_data', df)
    logger.info("Seed complete.")

if __name__ == "__main__":
    seed()
