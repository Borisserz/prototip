import clickhouse_connect
import random
import uuid
from datetime import datetime, timedelta

def generate_saas_metrics(client, start_date, end_date):
    print("Generating B2B SaaS metrics...")
    client.command("""
    CREATE TABLE IF NOT EXISTS saas_metrics (
        transaction_id UUID,
        date Date,
        company_name String,
        plan_tier String,
        mrr Float32,
        seats UInt16,
        is_churned UInt8
    ) ENGINE = MergeTree()
    ORDER BY (date, plan_tier)
    """)
    client.command("TRUNCATE TABLE saas_metrics")
    
    companies = [{"name": f"Client-{i}", "tier": random.choice(["Basic", "Pro", "Enterprise"]), "active": True, "seats": random.randint(5, 100)} for i in range(1, 501)]
    
    data = []
    current_date = start_date
    while current_date < end_date:
        for comp in companies:
            if not comp["active"]:
                continue
                
            # Base MRR per seat
            mrr_per_seat = {"Basic": 10, "Pro": 25, "Enterprise": 50}[comp["tier"]]
            
            # Anomaly: Price hike in Basic tier in Jan 2023 caused massive churn
            churn_prob = 0.001
            if current_date.year == 2023 and current_date.month in [1, 2] and comp["tier"] == "Basic":
                churn_prob = 0.15
                
            is_churned = 1 if random.random() < churn_prob else 0
            if is_churned:
                comp["active"] = False
                
            mrr = comp["seats"] * mrr_per_seat
            
            data.append([uuid.uuid4(), current_date, comp["name"], comp["tier"], float(mrr), comp["seats"], is_churned])
            
        if len(data) >= 10000:
            client.insert('saas_metrics', data, column_names=['transaction_id', 'date', 'company_name', 'plan_tier', 'mrr', 'seats', 'is_churned'])
            data = []
        current_date += timedelta(days=30) # Monthly billing
        
    if data:
        client.insert('saas_metrics', data, column_names=['transaction_id', 'date', 'company_name', 'plan_tier', 'mrr', 'seats', 'is_churned'])


def generate_ecommerce_sales(client, start_date, end_date):
    print("Generating E-commerce sales...")
    client.command("""
    CREATE TABLE IF NOT EXISTS ecommerce_sales (
        transaction_id UUID,
        date Date,
        order_id String,
        client_id String,
        category String,
        amount Float32,
        region String,
        discount_applied UInt8
    ) ENGINE = MergeTree()
    ORDER BY (date, category)
    """)
    client.command("TRUNCATE TABLE ecommerce_sales")
    
    categories = ["Электроника", "Одежда", "Продукты", "Спорттовары"]
    regions = ["Минск", "Варшава", "Вильнюс", "Алматы"]
    
    data = []
    current_date = start_date
    while current_date < end_date:
        # Daily sales
        num_sales = random.randint(100, 500)
        
        # Black friday / December anomaly
        if current_date.month == 11 and current_date.day > 20:
            num_sales *= 3
        if current_date.month == 12:
            num_sales *= 2
            
        for _ in range(num_sales):
            cat = random.choice(categories)
            base_amt = random.uniform(20, 1000)
            
            # Anomaly: Clothes don't sell well in summer
            if current_date.month in [6, 7, 8] and cat == "Одежда":
                base_amt *= 0.3
                
            # Black Friday discount
            discount = 1 if (current_date.month == 11 and current_date.day > 20) else (1 if random.random() > 0.9 else 0)
            if discount:
                base_amt *= 0.7
                
            data.append([
                uuid.uuid4(),
                current_date,
                f"ORD-{random.randint(10000, 99999)}",
                f"USR-{random.randint(1000, 5000)}",
                cat,
                float(base_amt),
                random.choice(regions),
                discount
            ])
            
        if len(data) >= 10000:
            client.insert('ecommerce_sales', data, column_names=['transaction_id', 'date', 'order_id', 'client_id', 'category', 'amount', 'region', 'discount_applied'])
            data = []
        current_date += timedelta(days=1)
        
    if data:
        client.insert('ecommerce_sales', data, column_names=['transaction_id', 'date', 'order_id', 'client_id', 'category', 'amount', 'region', 'discount_applied'])


if __name__ == "__main__":
    client = clickhouse_connect.get_client(host='localhost', port=8123)
    start = datetime(2021, 1, 1)
    end = datetime(2024, 1, 1)
    generate_saas_metrics(client, start, end)
    generate_ecommerce_sales(client, start, end)
    print("Multi-domain data generated successfully!")
