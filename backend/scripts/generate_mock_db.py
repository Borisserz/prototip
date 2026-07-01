import csv
import os
import random
from datetime import datetime, timedelta

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
DB_FILE = os.path.join(DATA_DIR, "massive_mock_db.csv")

TAX_TYPES = [
    "НДС",
    "Налог на прибыль",
    "Подоходный налог",
    "Налог на недвижимость",
    "Земельный налог",
    "Акцизы",
]
REGIONS = [
    "Минск",
    "Гомельская область",
    "Брестская область",
    "Витебская область",
    "Могилевская область",
    "Гродненская область",
    "Минская область",
]
TAXPAYER_TYPES = ["ООО", "ЗАО", "ОАО", "ИП", "Физлицо"]
INDUSTRIES = ["IT", "Строительство", "Торговля", "Сельское хозяйство", "Услуги", "Производство"]


def get_clickhouse_ddl():
    """Возвращает DDL схему для ClickHouse."""
    return """
        CREATE TABLE IF NOT EXISTS tax_data (
        id UInt32,
        taxpayer_id UInt32,
        taxpayer_type LowCardinality(String),
        industry LowCardinality(String),
        region LowCardinality(String),
        tax_type LowCardinality(String),
        accrued Float32,
        paid Float32,
        debt Float32,
        penalty Float32,
        status LowCardinality(String),
        period Date
    ) ENGINE = MergeTree()
    ORDER BY (region, period, tax_type)
    SETTINGS index_granularity = 8192;
    """


def generate_db(count=50000):
    os.makedirs(DATA_DIR, exist_ok=True)

    print(f"Генерация {count} строк данных налогоплательщиков...")

    start_date = datetime(2023, 1, 1)

    with open(DB_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "id",
                "taxpayer_id",
                "taxpayer_type",
                "industry",
                "region",
                "tax_type",
                "accrued",
                "paid",
                "debt",
                "penalty",
                "status",
                "period",
            ]
        )

        for i in range(1, count + 1):
            taxpayer_id = random.randint(100000, 999999)
            taxpayer_type = random.choice(TAXPAYER_TYPES)
            industry = random.choice(INDUSTRIES)
            region = random.choice(REGIONS)
            tax_type = random.choice(TAX_TYPES)

            accrued = round(random.uniform(1000.0, 500000.0), 2)

            # Имитация долгов: 70% платят всё, 30% недоплачивают
            if random.random() > 0.3:
                paid = accrued
                debt = 0.0
                penalty = 0.0
                status = "Оплачено"
            else:
                paid = round(random.uniform(0.0, accrued * 0.9), 2)
                debt = round(accrued - paid, 2)
                penalty = round(debt * random.uniform(0.01, 0.1), 2)
                status = "Задолженность"

            period_date = start_date + timedelta(days=random.randint(0, 365))
            period_str = period_date.strftime("%Y-%m-%d")

            writer.writerow(
                [
                    i,
                    taxpayer_id,
                    taxpayer_type,
                    industry,
                    region,
                    tax_type,
                    accrued,
                    paid,
                    debt,
                    penalty,
                    status,
                    period_str,
                ]
            )

            if i % 10000 == 0:
                print(f"Готово {i} строк...")

    print(
        f"Генерация завершена. Файл сохранен: {DB_FILE} (Размер: {os.path.getsize(DB_FILE) / (1024 * 1024):.2f} MB)"
    )
    print("\nОптимизированный DDL для ClickHouse (с LowCardinality и MergeTree):\n")
    print(get_clickhouse_ddl())


if __name__ == "__main__":
    generate_db(50000)  # Генерация 50k строк для теста
