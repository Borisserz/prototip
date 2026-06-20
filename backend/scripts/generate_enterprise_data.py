import random
import uuid
from datetime import datetime, timedelta

import clickhouse_connect


def generate_enterprise_data():
    client = clickhouse_connect.get_client(host='localhost', port=8123)
    
    # Создаем широкую таблицу
    client.command("""
    CREATE TABLE IF NOT EXISTS enterprise_taxes (
        transaction_id UUID,
        date Date,
        taxpayer_inn String,
        taxpayer_name String,
        region String,
        city String,
        tax_type String,
        amount Float32,
        status String,
        risk_score UInt8,
        has_audit UInt8,
        fine_amount Float32,
        industry String
    ) ENGINE = MergeTree()
    ORDER BY (date, region, industry)
    """)
    
    # Очищаем перед генерацией (если запускаем повторно)
    client.command("TRUNCATE TABLE enterprise_taxes")
    
    print("Table enterprise_taxes ready. Generating data...")
    
    regions = ["Минская область", "Брестская область", "Гомельская область", "Гродненская область", "Витебская область", "Могилевская область", "г. Минск"]
    cities = {"Минская область": ["Борисов", "Солигорск", "Молодечно"], "Брестская область": ["Брест", "Барановичи", "Пинск"], "Гомельская область": ["Гомель", "Мозырь", "Жлобин"], "Гродненская область": ["Гродно", "Лида", "Слоним"], "Витебская область": ["Витебск", "Орша", "Новополоцк"], "Могилевская область": ["Могилев", "Бобруйск", "Горки"], "г. Минск": ["Минск"]}
    tax_types = ["НДС", "Налог на прибыль", "Подоходный налог", "Экологический налог", "Налог на недвижимость"]
    statuses = ["Оплачено", "Оплачено", "Оплачено", "Оплачено", "Просрочка", "Взыскание"]
    industries = ["IT", "Ритейл", "Производство", "Строительство", "Транспорт", "Финансы", "Агропром"]
    
    # Генерируем 100 компаний
    companies = []
    for i in range(1, 101):
        ind = random.choice(industries)
        reg = random.choice(regions)
        cit = random.choice(cities[reg])
        inn = str(random.randint(100000000, 999999999))
        name = f"{random.choice(['ООО', 'ЗАО', 'ОАО'])} 'Компани-{i}'"
        companies.append({
            "inn": inn, "name": name, "region": reg, "city": cit, "industry": ind
        })
        
    start_date = datetime(2021, 1, 1)
    end_date = datetime(2024, 1, 1)
    
    data = []
    batch_size = 10000
    
    current_date = start_date
    while current_date < end_date:
        # Кол-во транзакций в день: ~100
        for _ in range(random.randint(50, 150)):
            comp = random.choice(companies)
            ttype = random.choice(tax_types)
            
            # Базовая сумма
            base_amt = random.uniform(1000, 50000)
            
            # Тренды: Ритейл растет со временем
            days_passed = (current_date - start_date).days
            if comp["industry"] == "Ритейл":
                base_amt *= (1 + (days_passed / 1000))  # Рост до +100% за 3 года
                
            # Аномалия: Падение IT в середине 2022 года
            if comp["industry"] == "IT" and current_date.year == 2022 and current_date.month in [6, 7, 8, 9, 10]:
                base_amt *= 0.2  # Резкое падение
                
            # Сезонность: В декабре налоги больше
            if current_date.month == 12:
                base_amt *= 1.5
                
            status = random.choice(statuses)
            risk = random.randint(1, 100)
            
            # Если риск высокий, шанс аудита больше
            has_audit = 1 if risk > 80 and random.random() > 0.5 else 0
            fine_amount = random.uniform(5000, 20000) if has_audit else 0.0
            
            data.append([
                uuid.uuid4(),
                current_date,
                comp["inn"],
                comp["name"],
                comp["region"],
                comp["city"],
                ttype,
                float(base_amt),
                status,
                risk,
                has_audit,
                float(fine_amount),
                comp["industry"]
            ])
            
            if len(data) >= batch_size:
                client.insert('enterprise_taxes', data, column_names=['transaction_id', 'date', 'taxpayer_inn', 'taxpayer_name', 'region', 'city', 'tax_type', 'amount', 'status', 'risk_score', 'has_audit', 'fine_amount', 'industry'])
                data = []
                
        current_date += timedelta(days=1)
        
    if data:
        client.insert('enterprise_taxes', data, column_names=['transaction_id', 'date', 'taxpayer_inn', 'taxpayer_name', 'region', 'city', 'tax_type', 'amount', 'status', 'risk_score', 'has_audit', 'fine_amount', 'industry'])

    print("Data generation complete! Added ~100k+ rows to enterprise_taxes.")

if __name__ == "__main__":
    generate_enterprise_data()
