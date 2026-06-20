#!/usr/bin/env python3
import json
import logging
from pathlib import Path

import clickhouse_connect
import yaml

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("SchemaDiscovery")

def discover_schema(host='localhost', port=8123, output_path='data/semantic_model.yaml'):
    """
    Подключается к ClickHouse, сканирует структуру всех таблиц (кроме системных),
    определяет возможные значения для LowCardinality/String колонок 
    и ищет вложенные JSON-поля. Генерирует semantic_model.yaml.
    """
    logger.info(f"Connecting to ClickHouse at {host}:{port}")
    try:
        client = clickhouse_connect.get_client(host=host, port=port)
    except Exception as e:
        logger.error(f"Failed to connect to ClickHouse: {e}")
        return

    # Получаем список пользовательских таблиц
    tables_res = client.query("SHOW TABLES FROM default")
    tables = [row[0] for row in tables_res.result_rows]
    
    if not tables:
        logger.warning("No tables found in 'default' database.")
        return

    semantic_model = {
        "version": "1.0",
        "models": []
    }

    for table in tables:
        logger.info(f"Scanning table: {table}")
        model_desc = {
            "name": table,
            "description": f"Таблица {table}. Автоматически сгенерировано (Schema Discovery).",
            "columns": []
        }
        
        # Получаем колонки
        cols_res = client.query(f"DESCRIBE TABLE {table}")
        
        for row in cols_res.result_rows:
            col_name = row[0]
            col_type = row[1]
            
            col_desc = {
                "name": col_name,
                "type": col_type,
                "description": "Описание отсутствует."
            }
            
            # Если это String или LowCardinality(String), попытаемся извлечь ENUM значения или проверить на JSON
            if "String" in col_type:
                # Сначала проверяем, не JSON ли это
                try:
                    # Быстрая проверка: начинается ли строка с { и заканчивается ли на }
                    json_check = client.query(f"SELECT {col_name} FROM {table} WHERE {col_name} LIKE '{{%}}' LIMIT 1")
                    if json_check.result_rows:
                        # Попробуем распарсить
                        sample_val = json_check.result_rows[0][0]
                        try:
                            parsed = json.loads(sample_val)
                            if isinstance(parsed, dict):
                                keys = list(parsed.keys())
                                col_desc["description"] = f"JSON поле. Содержит ключи: {', '.join(keys)}. Для доступа используйте JSONExtractString({col_name}, 'key')."
                                col_desc["is_json"] = True
                        except Exception:
                            pass
                except Exception as e:
                    logger.debug(f"JSON check failed for {col_name}: {e}")
                
                # Если это не JSON, попробуем извлечь уникальные значения для обогащения контекста
                if not col_desc.get("is_json"):
                    try:
                        unique_res = client.query(f"SELECT DISTINCT {col_name} FROM {table} LIMIT 15")
                        unique_vals = [str(r[0]) for r in unique_res.result_rows if r[0] is not None and str(r[0]).strip()]
                        
                        if 0 < len(unique_vals) <= 12:
                            col_desc["enum_values"] = unique_vals
                            col_desc["description"] = f"Возможные значения: {', '.join(unique_vals)}."
                    except Exception as e:
                        logger.debug(f"Enum extraction failed for {col_name}: {e}")
            
            model_desc["columns"].append(col_desc)
            
        semantic_model["models"].append(model_desc)

    # Сохраняем в YAML
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(out_path, 'w', encoding='utf-8') as f:
        yaml.dump(semantic_model, f, allow_unicode=True, sort_keys=False)
        
    logger.info(f"Successfully generated {out_path} with {len(tables)} tables.")

if __name__ == "__main__":
    discover_schema()
