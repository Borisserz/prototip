import os
import sys

# Добавляем корень проекта в PYTHONPATH
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from app.services.rag_service import initialize_rag
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("RAGIndexer")

def index_documents():
    """Скрипт для индексации .md файлов из data/docs в ChromaDB."""
    docs_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'docs')
    if not os.path.exists(docs_dir):
        logger.error(f"Директория {docs_dir} не найдена.")
        return

    logger.info(f"Запуск RAG Indexer для директории: {docs_dir}")
    try:
        initialize_rag(docs_directory=docs_dir)
        logger.info("✅ Индексация успешно завершена!")
    except Exception as e:
        logger.error(f"❌ Ошибка индексации: {e}")

if __name__ == "__main__":
    index_documents()
