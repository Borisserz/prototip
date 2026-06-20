import pandas as pd
import requests
import sys

def seed():
    try:
        df = pd.read_csv('../data/sample.csv')
    except FileNotFoundError:
        print("data/sample.csv not found. Generate it first using python data/make_dataset.py")
        sys.exit(1)
        
    csv_data = df.to_csv(index=False)
    
    url = "http://localhost:8123/?database=tax_analytics&query=INSERT INTO tax_data FORMAT CSVWithNames"
    auth = ('admin', 'admin')
    
    print("Seeding ClickHouse...")
    response = requests.post(url, auth=auth, data=csv_data)
    
    if response.status_code == 200:
        print(f"Successfully inserted {len(df)} rows.")
    else:
        print(f"Failed to insert data: {response.text}")
        sys.exit(1)

if __name__ == "__main__":
    seed()
