import json
import logging
import os
import uuid

from langchain_community.document_loaders import DirectoryLoader, PyPDFLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.utils.clickhouse_client import ch_client

logger = logging.getLogger(__name__)

def get_embeddings_model():
    try:
        from langchain_huggingface import HuggingFaceEmbeddings
        return HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
    except ImportError:
        logger.warning("Не установлен langchain_huggingface. Используется заглушка.")
        from langchain_core.embeddings import FakeEmbeddings
        return FakeEmbeddings(size=384) # all-MiniLM-L6-v2 is 384 dims

def init_tables():
    ch_client.command("""
    CREATE TABLE IF NOT EXISTS knowledge_base (
        id String,
        source String,
        content String,
        embedding Array(Float32)
    ) ENGINE = MergeTree()
    ORDER BY id
    """)
    
    ch_client.command("""
    CREATE TABLE IF NOT EXISTS dashboard_knowledge (
        id String,
        title String,
        description String,
        full_json String,
        embedding Array(Float32)
    ) ENGINE = MergeTree()
    ORDER BY id
    """)

def initialize_rag(docs_directory: str = None):
    logger.info("Инициализация RAG Pipeline в ClickHouse...")
    init_tables()
    embeddings_model = get_embeddings_model()
    
    documents = []
    if docs_directory and os.path.exists(docs_directory):
        pdf_loader = DirectoryLoader(docs_directory, glob="**/*.pdf", loader_cls=PyPDFLoader)
        documents.extend(pdf_loader.load())
        txt_loader = DirectoryLoader(docs_directory, glob="**/*.md", loader_cls=TextLoader)
        documents.extend(txt_loader.load())
        txt_loader_fallback = DirectoryLoader(docs_directory, glob="**/*.txt", loader_cls=TextLoader)
        documents.extend(txt_loader_fallback.load())

    if not documents:
        return

    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    splits = splitter.split_documents(documents)
    
    data = []
    for split in splits:
        emb = embeddings_model.embed_query(split.page_content)
        data.append([
            uuid.uuid4().hex,
            split.metadata.get("source", "unknown"),
            split.page_content,
            emb
        ])
        
    if data:
        ch_client.insert("knowledge_base", data, column_names=["id", "source", "content", "embedding"])
        logger.info(f"Загружено {len(data)} чанков в ClickHouse.")

def ingest_document(file_path: str) -> bool:
    init_tables()
    embeddings_model = get_embeddings_model()
    
    from langchain_core.documents import Document
    documents = []
    
    if file_path.endswith('.pdf'):
        try:
            import pdfplumber
            with pdfplumber.open(file_path) as pdf:
                for i, page in enumerate(pdf.pages):
                    try:
                        text = page.extract_text() or ""
                    except Exception as e:
                        logger.warning(f"Ошибка извлечения текста на странице {i}: {e}")
                        text = ""
                        
                    try:
                        tables = page.extract_tables()
                        if tables:
                            text += "\n\nТаблицы на странице:\n"
                            for table in tables:
                                for row in table:
                                    safe_row = [str(cell).replace('\n', ' ') if cell else "" for cell in row]
                                    text += " | ".join(safe_row) + "\n"
                                text += "\n"
                    except Exception as e:
                        logger.warning(f"Ошибка извлечения таблиц на странице {i} (возможно скан): {e}")
                        
                    if text.strip():
                        documents.append(Document(page_content=text, metadata={"source": file_path, "page": i}))
        except ImportError:
            logger.warning("pdfplumber не установлен. Используется PyPDFLoader.")
            loader = PyPDFLoader(file_path)
            documents.extend(loader.load())
    else:
        loader = TextLoader(file_path)
        documents.extend(loader.load())

    if not documents:
        return False

    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    splits = splitter.split_documents(documents)
    
    data = []
    for split in splits:
        emb = embeddings_model.embed_query(split.page_content)
        data.append([
            uuid.uuid4().hex,
            file_path,
            split.page_content,
            emb
        ])
        
    if data:
        ch_client.insert("knowledge_base", data, column_names=["id", "source", "content", "embedding"])
        logger.info(f"Загружено {len(data)} чанков из {file_path} в ClickHouse.")
    return True

def get_rag_context(query: str, k: int = 4) -> str:
    embeddings_model = get_embeddings_model()
    query_vector = embeddings_model.embed_query(query)
    
    try:
        sql = f"""
        SELECT content, cosineDistance(embedding, {query_vector}) as dist 
        FROM default.knowledge_base 
        ORDER BY dist ASC 
        LIMIT {k}
        """
        result = ch_client.get_client().query(sql)
        docs = []
        for row in result.result_rows:
            docs.append(row[0])
        return "\n\n".join(docs)
    except Exception as e:
        logger.error(f"ClickHouse RAG Search Error: {e}")
        return ""

def get_knowledge_documents():
    try:
        sql = "SELECT source, count(*) as chunks FROM default.knowledge_base GROUP BY source"
        result = ch_client.get_client().query(sql)
        docs = []
        for row in result.result_rows:
            docs.append({"source": row[0], "chunks": row[1]})
        return docs
    except Exception as e:
        logger.error(f"ClickHouse KB List Error: {e}")
        return []

def delete_knowledge_document(source: str) -> bool:
    try:
        sql = f"ALTER TABLE default.knowledge_base DELETE WHERE source = '{source}'"
        ch_client.command(sql)
        return True
    except Exception as e:
        logger.error(f"ClickHouse KB Delete Error: {e}")
        return False

def initialize_dashboard_rag():
    init_tables()
    embeddings_model = get_embeddings_model()
    dash_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'dashboards')
    
    if not os.path.exists(dash_dir):
        return False
        
    data = []
    for fname in os.listdir(dash_dir):
        if fname.endswith(".json"):
            with open(os.path.join(dash_dir, fname), encoding='utf-8') as f:
                dash = json.load(f)
                content = f"Title: {dash.get('title')}\nDescription: {dash.get('description')}\nID: {dash.get('id')}"
                emb = embeddings_model.embed_query(content)
                data.append([
                    dash.get("id", uuid.uuid4().hex),
                    dash.get("title", ""),
                    dash.get("description", ""),
                    json.dumps(dash, ensure_ascii=False),
                    emb
                ])
                
    if data:
        ch_client.insert("dashboard_knowledge", data, column_names=["id", "title", "description", "full_json", "embedding"])
        return True
    return False

def search_dashboards(query: str, k: int = 1):
    embeddings_model = get_embeddings_model()
    query_vector = embeddings_model.embed_query(query)
    
    try:
        sql = f"""
        SELECT full_json, cosineDistance(embedding, {query_vector}) as dist 
        FROM default.dashboard_knowledge 
        ORDER BY dist ASC 
        LIMIT {k}
        """
        result = ch_client.get_client().query(sql)
        class MockDoc:
            def __init__(self, c):
                self.page_content = c
        
        docs = []
        for row in result.result_rows:
            dash_json = row[0]
            # Formating output identical to chroma Document for compatibility
            docs.append(MockDoc(f"Найден релевантный сохраненный дашборд:\n{dash_json}"))
        return docs
    except Exception as e:
        logger.error(f"ClickHouse Dashboard Search Error: {e}")
        return []
