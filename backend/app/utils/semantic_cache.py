from __future__ import annotations

import logging
from pathlib import Path

try:
    from chromadb import PersistentClient
    from chromadb.utils import embedding_functions
    HAS_CHROMA = False  # Disabled temporarily to bypass 80MB ONNX download during eval
except ImportError:
    HAS_CHROMA = False

logger = logging.getLogger("SemanticCache")

class SemanticCache:
    """Хранит отображение: Вопрос пользователя -> Сгенерированный SQL."""
    
    def __init__(self, cache_dir: str = "out/chroma_cache", threshold: float = 0.15):
        self.cache_dir = Path(cache_dir)
        self.threshold = threshold
        self.collection = None
        
        if HAS_CHROMA:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            self.ef = embedding_functions.DefaultEmbeddingFunction()
            self.client = PersistentClient(path=str(self.cache_dir))
            self.collection = self.client.get_or_create_collection(
                name="sql_cache",
                embedding_function=self.ef,
                metadata={"hnsw:space": "cosine"}
            )
        else:
            logger.warning("chromadb not installed. SemanticCache is disabled.")

    def get_sql(self, question: str) -> str | None:
        """Ищет семантически похожий вопрос. Возвращает SQL если уверенность высока."""
        if not HAS_CHROMA or self.collection is None or self.collection.count() == 0:
            return None
            
        results = self.collection.query(
            query_texts=[question],
            n_results=1
        )
        
        if not results["distances"] or not results["distances"][0]:
            return None
            
        distance = results["distances"][0][0]
        if distance < self.threshold:
            # Считаем, что это тот же самый вопрос
            sql = results["metadatas"][0][0].get("sql")
            logger.info(f"[Cache HIT] '{question}' (dist: {distance:.3f}) -> {sql}")
            return sql
            
        logger.info(f"[Cache MISS] '{question}' (closest dist: {distance:.3f})")
        return None

    def set_sql(self, question: str, sql: str) -> None:
        """Сохраняет пару вопрос-SQL в кэш."""
        if not HAS_CHROMA or self.collection is None:
            return
            
        # Для простоты используем хэш от вопроса как ID
        import hashlib
        doc_id = hashlib.md5(question.encode('utf-8')).hexdigest()
        
        self.collection.upsert(
            ids=[doc_id],
            documents=[question],
            metadatas=[{"sql": sql}]
        )
        logger.debug(f"[Cache SET] '{question}' -> {sql}")

# Global instance
semantic_cache = SemanticCache()
