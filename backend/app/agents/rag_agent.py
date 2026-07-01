"""RagAgent — поиск по нормативной базе через ClickHouse Vector Search.

SECURITY FIX (FIX-7): добавлена изоляция по client_id.
Документы без client_id (глобальные) доступны всем тенантам.
Документы с client_id доступны только соответствующему тенанту.
"""

from __future__ import annotations

import logging

from app.agents.base_agent import BaseAgent
from app.agents.models import RagResult

logger = logging.getLogger(__name__)


class RagAgent(BaseAgent):
    """Агент для поиска по нормативной базе (RAG).

    Находит релевантные юридические, методические контексты.
    Изолирован по client_id: документы тенанта недоступны другим тенантам.
    """

    name = "rag_agent"
    description = "Специалист по нормативной базе. Знает налоговый кодекс и ищет точные выдержки."

    def run(self, question: str) -> RagResult:
        logger.info(f"[RagAgent] Ищем документы по запросу: {question}")

        try:
            from app.agent_context import get_current_tenant
            from app.services.rag_service import get_embeddings_model
            from app.utils.clickhouse_client import ch_client

            embeddings = get_embeddings_model()
            query_emb = embeddings.embed_query(question)

            tenant = get_current_tenant()
            client_id = tenant.client_id if tenant else None

            # ClickHouse Native Vector Search с изоляцией по client_id.
            # Логика: возвращаем документы тенанта ИЛИ глобальные (client_id = '' или NULL).
            # Так тенант видит свои документы + общую нормативную базу.
            if client_id:
                where_clause = f"(client_id = '{client_id}' OR client_id = '' OR client_id IS NULL)"
            else:
                # Нет тенанта → только глобальные документы
                where_clause = "(client_id = '' OR client_id IS NULL)"

            # Проверяем наличие колонки client_id (старые инсталляции могут её не иметь)
            try:
                desc = ch_client.get_client().query(
                    "SELECT name FROM system.columns WHERE table='knowledge_base' AND database='default' AND name='client_id'"
                )
                has_client_id_col = bool(desc.result_rows)
            except Exception:
                has_client_id_col = False

            if has_client_id_col:
                filter_sql = f"WHERE {where_clause}"
            else:
                # Колонки нет — возвращаем все документы (legacy режим)
                filter_sql = ""
                if client_id:
                    logger.warning(
                        "[RagAgent] knowledge_base не имеет колонки client_id — "
                        "изоляция по тенанту не применена. Выполните миграцию."
                    )

            query = f"""
                SELECT
                    id,
                    source,
                    content,
                    cosineDistance(embedding, {query_emb}) AS score
                FROM default.knowledge_base
                {filter_sql}
                ORDER BY score ASC
                LIMIT 3
            """

            result = ch_client.get_client().query(query)

            if not result.result_rows:
                return RagResult(
                    success=True,
                    context="Нормативной документации по данному вопросу не найдено.",
                    sources=[],
                    reasoning="Поиск по ClickHouse Vector Search не дал результатов.",
                )

            docs = result.result_rows
            context_text = "\n\n".join([row[2] for row in docs])
            sources = list(dict.fromkeys([row[1] for row in docs]))  # preserve order, deduplicate
            source_snippets = [{"title": row[1], "snippet": row[2][:300] + "..."} for row in docs]

            return RagResult(
                success=True,
                context=context_text,
                sources=sources,
                source_snippets=source_snippets,
                reasoning=(
                    f"Найдено {len(docs)} релевантных фрагментов через ClickHouse RAG"
                    + (f" (tenant={client_id})" if client_id else " (global)")
                    + "."
                ),
            )

        except Exception as e:
            logger.error(f"[RagAgent] Ошибка при RAG-поиске: {e}")
            return RagResult(
                success=False,
                context="",
                sources=[],
                error=str(e),
                reasoning="Произошла системная ошибка при обращении к ClickHouse RAG.",
            )
