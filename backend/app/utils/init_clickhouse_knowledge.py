import logging
import clickhouse_connect

logger = logging.getLogger("InitClickhouseKnowledge")

def init_knowledge_base():
    try:
        client = clickhouse_connect.get_client(host='localhost', port=8123)
        
        # Создаем таблицу с поддержкой векторного хранения
        client.command("""
        CREATE TABLE IF NOT EXISTS knowledge_base (
            id String,
            source String,
            content String,
            embedding Array(Float32)
        ) ENGINE = MergeTree()
        ORDER BY id
        """)
        
        logger.info("Таблица knowledge_base успешно создана/обновлена в ClickHouse!")
        
        # Проверяем, пустая ли она
        count = client.query("SELECT count() FROM knowledge_base").result_rows[0][0]
        if count == 0:
            logger.info("Таблица пуста, загружаем тестовую нормативную базу...")
            
            try:
                from langchain_huggingface import HuggingFaceEmbeddings
                embeddings_model = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
                
                docs = [
                    {"id": "doc1", "source": "Налоговый Кодекс Ст. 101", "content": "Для фильтрации по году всегда используйте функцию toYear(period) или toYear(date). Начисления хранятся в колонке accrued, а задолженности - в колонке debt (если используется tax_data)."},
                    {"id": "doc2", "source": "Регламент BI аналитики", "content": "В таблице enterprise_taxes задолженности определяются как status='Взыскание' или status='Просрочка', а оплаченные налоги - status='Оплачено'."}
                ]
                
                data = []
                for doc in docs:
                    emb = embeddings_model.embed_query(doc["content"])
                    data.append([doc["id"], doc["source"], doc["content"], emb])
                    
                client.insert("knowledge_base", data, column_names=["id", "source", "content", "embedding"])
                logger.info("Тестовые векторы успешно загружены в ClickHouse.")
            except ImportError:
                logger.error("Не установлен пакет langchain_huggingface или sentence-transformers. Загрузка данных пропущена.")
        else:
            logger.info(f"В knowledge_base уже есть {count} записей.")
            
    except Exception as e:
        logger.error(f"Ошибка: {e}")

if __name__ == "__main__":
    init_knowledge_base()
