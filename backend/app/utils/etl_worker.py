import os
import time
import shutil
import logging
from pathlib import Path
import pandas as pd

# Позволяем импортировать из app, если запущен как модуль
import sys
sys.path.append(str(Path(__file__).parent.parent.parent))

from app.utils.clickhouse_client import ch_client

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s')
logger = logging.getLogger("ETLWorker")

DROPZONE_DIR = Path("data/dropzone")
ARCHIVE_DIR = Path("data/archive")

def process_dropzone():
    DROPZONE_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    
    for file_path in DROPZONE_DIR.glob("*.csv"):
        logger.info(f"Начало обработки файла: {file_path.name}")
        try:
            df = pd.read_csv(file_path)
            
            table_name = "default.enterprise_taxes"
            if file_path.name.startswith("table_"):
                # Напр: table_regions_dict.csv -> default.regions_dict
                table_name = f"default.{file_path.stem.replace('table_', '')}"
                
            ch_client.insert_df(table_name, df)
            logger.info(f"Успешно вставлено {len(df)} строк в таблицу {table_name}")
            
            dest = ARCHIVE_DIR / f"{int(time.time())}_{file_path.name}"
            shutil.move(str(file_path), str(dest))
            logger.info(f"Файл {file_path.name} перемещен в архив.")
            
        except Exception as e:
            logger.error(f"Ошибка при обработке {file_path.name}: {e}")
            dest = ARCHIVE_DIR / f"error_{int(time.time())}_{file_path.name}"
            try:
                shutil.move(str(file_path), str(dest))
            except Exception as move_e:
                logger.error(f"Не удалось переместить ошибочный файл: {move_e}")

def run_worker(interval_sec=10):
    logger.info(f"ETL Worker запущен. Сканирование {DROPZONE_DIR} каждые {interval_sec}с...")
    while True:
        try:
            process_dropzone()
        except Exception as e:
            logger.error(f"Ошибка воркера: {e}")
        time.sleep(interval_sec)

if __name__ == "__main__":
    run_worker()
