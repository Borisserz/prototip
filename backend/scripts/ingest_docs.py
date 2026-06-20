import os
import glob
import logging
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_qdrant import QdrantVectorStore, FastEmbedSparse, RetrievalMode
from langchain_huggingface import HuggingFaceEmbeddings
from qdrant_client import QdrantClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ingest_docs")

DOCS_DIR = os.path.join(os.path.dirname(__file__), "../docs_source")

def main():
    logger.info(f"Ищем документы в {DOCS_DIR}...")
    pdf_files = glob.glob(os.path.join(DOCS_DIR, "*.pdf"))
    txt_files = glob.glob(os.path.join(DOCS_DIR, "*.txt"))
    
    docs = []
    
    # Загружаем PDF
    for pdf_path in pdf_files:
        logger.info(f"Загрузка PDF: {pdf_path}")
        loader = PyPDFLoader(pdf_path)
        docs.extend(loader.load())
        
    # Загружаем TXT (если есть моки)
    for txt_path in txt_files:
        logger.info(f"Загрузка TXT: {txt_path}")
        loader = TextLoader(txt_path)
        docs.extend(loader.load())
        
    if not docs:
        logger.warning("Нет документов для загрузки.")
        return
        
    logger.info(f"Загружено {len(docs)} страниц/документов. Начинаем разбиение (chunking)...")
    
    # Разбиваем на чанки
    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    splits = splitter.split_documents(docs)
    logger.info(f"Получено {len(splits)} чанков.")
    
    # Инициализация Qdrant и Embedding
    embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
    sparse_embeddings = FastEmbedSparse(model_name="Qdrant/bm25")
    client = QdrantClient("localhost", port=6333)
    
    # Создаем/пересоздаем коллекцию
    collection_name = "knowledge_base"
    
    logger.info(f"Индексация в Qdrant (collection: {collection_name})...")
    
    QdrantVectorStore.from_documents(
        splits,
        embedding=embeddings,
        sparse_embedding=sparse_embeddings,
        retrieval_mode=RetrievalMode.HYBRID,
        collection_name=collection_name,
        url="http://localhost:6333",
        force_recreate=True
    )
    
    logger.info("Успешно завершено! База знаний RAG 2.0 обновлена.")

if __name__ == "__main__":
    main()
