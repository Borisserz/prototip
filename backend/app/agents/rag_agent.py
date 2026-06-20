import logging
import os

from app.agents.base_agent import BaseAgent
from app.agents.models import RagResult

logger = logging.getLogger(__name__)

class RagAgent(BaseAgent):
    """Агент для поиска по нормативной базе (RAG).
    Находит релевантные юридические, методические контексты.
    """
    
    name = "rag_agent"
    description = "Специалист по нормативной базе. Знает налоговый кодекс и ищет точные выдержки."

    def run(self, question: str) -> RagResult:
        logger.info(f"[RagAgent] Ищем документы по запросу: {question}")
            
        try:
            from langchain_huggingface import HuggingFaceEmbeddings
            from app.utils.clickhouse_client import ch_client
            
            embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
            query_emb = embeddings.embed_query(question)
            
            # ClickHouse Native Vector Search (Phase 13)
            query = f"""
                SELECT 
                    id, 
                    source, 
                    content, 
                    cosineDistance(embedding, {query_emb}) AS score
                FROM default.knowledge_base
                ORDER BY score ASC
                LIMIT 3
            """
            
            result = ch_client.get_client().query(query)
            
            if not result.result_rows:
                return RagResult(
                    success=True,
                    context="Нормативной документации по данному вопросу не найдено.",
                    sources=[],
                    reasoning="Поиск по ClickHouse Vector Search не дал результатов."
                )
                
            docs = result.result_rows
            context_text = "\n\n".join([row[2] for row in docs])
            sources = list(set([row[1] for row in docs]))
            source_snippets = [
                {
                    "title": row[1],
                    "snippet": row[2][:300] + "..."
                } for row in docs
            ]
            
            return RagResult(
                success=True,
                context=context_text,
                sources=sources,
                source_snippets=source_snippets,
                reasoning=f"Найдено {len(docs)} релевантных фрагментов через ClickHouse RAG."
            )
            
        except Exception as e:
            logger.error(f"[RagAgent] Ошибка при RAG-поиске: {e}")
            return RagResult(
                success=False,
                context="",
                sources=[],
                error=str(e),
                reasoning="Произошла системная ошибка при обращении к ClickHouse RAG."
            )

