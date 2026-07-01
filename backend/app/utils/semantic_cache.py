"""
SemanticCache — семантический кэш SQL-запросов через ChromaDB.

Хранит пары (вопрос_пользователя → SQL) с векторным поиском:
если семантически похожий вопрос уже задавался, возвращает ранее
сгенерированный SQL без вызова LLM.

Embedding: SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
  → использует уже установленный sentence-transformers, не качает ONNX Runtime.
  → Модель ~90MB, кэшируется в ~/.cache/torch/sentence_transformers/ при первом запуске.

Порог схожести (cosine distance): threshold=0.15
  → distance < threshold → HIT (вопросы идентичны по смыслу)
  → distance ≥ threshold → MISS (новый запрос, нужен LLM)

Отключение кэша: SEMANTIC_CACHE_ENABLED=false в .env
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger("SemanticCache")

_ENABLED = os.getenv("SEMANTIC_CACHE_ENABLED", "true").lower() not in ("false", "0", "no")

# -- ChromaDB + SentenceTransformer ---
try:
    from chromadb import PersistentClient
    from chromadb.utils.embedding_functions import (
        SentenceTransformerEmbeddingFunction,  # type: ignore[import]
    )

    HAS_CHROMA = True
except ImportError:
    HAS_CHROMA = False
    logger.warning(
        "chromadb not installed — SemanticCache disabled. Install: pip install 'chromadb>=0.5,<1.1'"
    )


class SemanticCache:
    """Кэш вопрос→SQL с векторным поиском (ChromaDB + sentence-transformers)."""

    def __init__(
        self,
        cache_dir: str = "out/chroma_cache",
        threshold: float = 0.15,
        model_name: str = "all-MiniLM-L6-v2",
    ):
        self.cache_dir = Path(cache_dir)
        self.threshold = threshold
        self.collection = None

        if not _ENABLED:
            logger.info("SemanticCache disabled via SEMANTIC_CACHE_ENABLED=false")
            return

        if not HAS_CHROMA:
            return

        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            # SentenceTransformerEmbeddingFunction использует sentence-transformers
            # (уже в requirements.txt) — не качает ONNX Runtime.
            self.ef = SentenceTransformerEmbeddingFunction(model_name=model_name)
            self.client = PersistentClient(path=str(self.cache_dir))
            self.collection = self.client.get_or_create_collection(
                name="sql_cache",
                embedding_function=self.ef,
                metadata={"hnsw:space": "cosine"},
            )
            logger.info(
                f"[SemanticCache] ChromaDB ready: {self.cache_dir} "
                f"(model={model_name}, threshold={threshold})"
            )
        except Exception as exc:
            logger.error(f"[SemanticCache] Init failed — cache disabled: {exc}")
            self.collection = None

    # ------------------------------------------------------------------

    def get_sql(self, question: str) -> str | None:
        """Ищет семантически похожий вопрос. Возвращает SQL при высоком сходстве."""
        if self.collection is None or self.collection.count() == 0:
            return None

        try:
            results = self.collection.query(query_texts=[question], n_results=1)
        except Exception as exc:
            logger.warning(f"[SemanticCache] query error: {exc}")
            return None

        distances = results.get("distances") or []
        if not distances or not distances[0]:
            return None

        distance = distances[0][0]
        if distance < self.threshold:
            sql = (results.get("metadatas") or [[{}]])[0][0].get("sql")
            logger.info(
                f"[Cache HIT] '{question[:60]}' (dist={distance:.3f}) → {sql[:60] if sql else '?'}..."
            )
            return sql

        logger.info(f"[Cache MISS] '{question[:60]}' (closest dist={distance:.3f})")
        return None

    def set_sql(self, question: str, sql: str) -> None:
        """Сохраняет пару вопрос→SQL в кэш."""
        if self.collection is None:
            return

        import hashlib

        doc_id = hashlib.md5(question.encode("utf-8")).hexdigest()
        try:
            self.collection.upsert(
                ids=[doc_id],
                documents=[question],
                metadatas=[{"sql": sql}],
            )
            logger.debug(f"[Cache SET] '{question[:60]}' → {sql[:60]}...")
        except Exception as exc:
            logger.warning(f"[SemanticCache] set_sql error: {exc}")

    def clear(self) -> None:
        """Очистить весь кэш (полезно при изменении схемы данных)."""
        if self.collection is None:
            return
        try:
            self.collection.delete(where={"sql": {"$ne": ""}})
            logger.info("[SemanticCache] Cache cleared")
        except Exception as exc:
            logger.warning(f"[SemanticCache] clear error: {exc}")

    @property
    def is_active(self) -> bool:
        return self.collection is not None


# глобальный синглтон
semantic_cache = SemanticCache()
