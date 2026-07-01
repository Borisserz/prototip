import logging
import os

import clickhouse_connect
import yaml

logger = logging.getLogger("SchemaCrawler")


def generate_semantic_model():
    """Сканирует ClickHouse, извлекает схему и ENUM-значения, и сохраняет в semantic_model.yaml"""
    logger.info("Сканирование ClickHouse и генерация семантической модели...")
    try:
        client = clickhouse_connect.get_client(
            host=os.getenv("CLICKHOUSE_HOST", "localhost"),
            port=int(os.getenv("CLICKHOUSE_PORT", "8123")),
            username=os.getenv("CLICKHOUSE_USER", "default"),
            password=os.getenv("CLICKHOUSE_PASSWORD", ""),
        )

        # Получаем все пользовательские таблицы
        tables_query = """
        SELECT table 
        FROM system.tables 
        WHERE database = 'default' 
        AND table NOT IN ('knowledge_base', 'tax_data_masked')
        """
        tables = [row[0] for row in client.query(tables_query).result_rows]

        models = []
        for table in tables:
            columns_query = f"""
            SELECT name, type, comment
            FROM system.columns
            WHERE table = '{table}' AND database = 'default'
            """
            columns_data = client.query(columns_query).result_rows

            columns_list = []
            for col_name, col_type, col_comment in columns_data:
                col_info = {
                    "name": col_name,
                    "type": col_type,
                    "description": col_comment if col_comment else "Нет описания.",
                }

                # Если колонка строковая, пытаемся вытащить уникальные значения (ENUM)
                # Это помогает LLM понять, что лежит в базе (например, type: ['charge', 'debt'])
                if "String" in col_type and not any(
                    x in col_name.lower() for x in ["id", "inn", "json", "embedding", "content"]
                ):
                    try:
                        enum_query = f"SELECT DISTINCT {col_name} FROM {table} LIMIT 10"
                        enum_vals = []
                        for row in client.query(enum_query).result_rows:
                            if row[0] is not None:
                                val_str = (
                                    str(row[0])
                                    if not isinstance(row[0], (list, tuple))
                                    else ", ".join(map(str, row[0]))
                                )
                                if val_str.strip():
                                    enum_vals.append(val_str)
                        if enum_vals and len(enum_vals) <= 10:
                            col_info["enum_values"] = enum_vals
                            col_info["description"] += (
                                f" Возможные значения: {', '.join(enum_vals)}."
                            )
                    except Exception:
                        pass

                columns_list.append(col_info)

            models.append(
                {
                    "name": table,
                    "description": f"Таблица {table}. Авто-генерация.",
                    "columns": columns_list,
                }
            )

        semantic_model = {"version": "1.0", "models": models}

        # Сохраняем в data/semantic_model.yaml
        output_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data"
        )
        os.makedirs(output_dir, exist_ok=True)
        out_file = os.path.join(output_dir, "semantic_model.yaml")

        with open(out_file, "w", encoding="utf-8") as f:
            yaml.dump(
                semantic_model, f, allow_unicode=True, default_flow_style=False, sort_keys=False
            )

        logger.info(f"Семантическая модель успешно сохранена в {out_file}")

    except Exception as e:
        logger.error(f"Ошибка Schema Crawler: {e}")


if __name__ == "__main__":
    generate_semantic_model()
