import os
import uuid
import logging
from app.utils.clickhouse_client import ch_client
from app.semantic.catalog import SemanticCatalog

logger = logging.getLogger(__name__)

def get_embeddings_model():
    try:
        from langchain_huggingface import HuggingFaceEmbeddings
        return HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
    except ImportError:
        logger.warning("Не установлен langchain_huggingface. Используется заглушка.")
        from langchain_core.embeddings import FakeEmbeddings
        return FakeEmbeddings(size=384)

def init_schema_knowledge():
    logger.info("Инициализация Schema Knowledge RAG в ClickHouse...")
    
    ch_client.get_client().command("""
    CREATE TABLE IF NOT EXISTS schema_knowledge (
        id String,
        name String,
        description String,
        content String,
        embedding Array(Float32)
    ) ENGINE = MergeTree()
    ORDER BY id
    """)

    # Очистка старых данных перед реиндексацией
    ch_client.get_client().command("TRUNCATE TABLE IF EXISTS schema_knowledge")

    yaml_path = os.path.join(os.path.dirname(__file__), "..", "..", "data", "semantic_model.yaml")
    catalog = SemanticCatalog.load(yaml_path)

    if not catalog.models:
        logger.warning("Нет моделей в semantic_model.yaml. Пропуск инициализации.")
        return

    embeddings_model = get_embeddings_model()
    data = []

    for model in catalog.models:
        # Генерируем контент для конкретной модели (таблицы)
        prompt = [f"Table/View: {model.name}"]
        if model.description and model.description != "Нет описания.":
            prompt.append(f"  Description: {model.description}")
        prompt.append("  Columns:")
        for col in model.columns:
            col_str = f"    - {col.name} ({col.type})"
            if col.description and col.description != "Нет описания.":
                col_str += f" | {col.description}"
            if col.enum_values:
                enums = ", ".join(col.enum_values[:5])
                if len(col.enum_values) > 5:
                    enums += ", ..."
                col_str += f" | Enums: [{enums}]"
            prompt.append(col_str)
        if model.metrics:
            prompt.append("  Calculated Metrics (Используй эти формулы в SELECT):")
            for m in model.metrics:
                m_str = f"    - {m.name} AS {m.expression}"
                if m.description:
                    m_str += f" | {m.description}"
                prompt.append(m_str)
        
        content = "\n".join(prompt)
        emb = embeddings_model.embed_query(content)
        
        data.append([
            uuid.uuid4().hex,
            model.name,
            model.description or "",
            content,
            emb
        ])

    if data:
        ch_client.insert("schema_knowledge", data, column_names=["id", "name", "description", "content", "embedding"])
        logger.info(f"Загружено {len(data)} таблиц/моделей в ClickHouse RAG.")

if __name__ == "__main__":
    init_schema_knowledge()
