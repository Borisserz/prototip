import logging
import os

import clickhouse_connect
from crewai.tools import BaseTool

logger = logging.getLogger("crew_tools")


class QueryClickhouseTool(BaseTool):
    name: str = "query_clickhouse"
    description: str = "Выполняет SQL-запрос (только SELECT) к DWH ClickHouse и возвращает данные."

    def _run(self, sql_query: str) -> str:
        """Execute query in ClickHouse."""
        try:
            client = clickhouse_connect.get_client(
                host=os.getenv("CLICKHOUSE_HOST", "localhost"),
                port=int(os.getenv("CLICKHOUSE_PORT", "8123")),
                username=os.getenv("CLICKHOUSE_USER", "default"),
                password=os.getenv("CLICKHOUSE_PASSWORD", ""),
            )
            logger.info(f"Executing SQL via CrewAI Tool: {sql_query}")

            # ЕДИНАЯ точка безопасности: тот же core.sql_guard.secure_sql, что и в DataAgent.
            # Раньше здесь была своя regex-защита, которая НЕ применяла multi-tenant
            # изоляцию (client_id, allowed_tables) — CrewAI-путь обходил RLS. Теперь:
            #   1) только SELECT (парсинг sqlglot, блок DDL/DML/опасных функций);
            #   2) allowed_tables + WHERE client_id для активного клиента (tenant);
            #   3) RLS-фильтры по роли (region IN (...)) из конфига/БД;
            #   4) авто-LIMIT.
            from app.agent_context import get_current_tenant, get_user_permissions, get_user_role
            from core.rls import get_role_filters
            from core.sql_guard import SqlSecurityError, secure_sql

            tenant = get_current_tenant()
            # Per-tenant user: персональные права имеют приоритет над роле-базовыми.
            perms = get_user_permissions()
            if perms:
                role_filters = perms.get("rls_filters") or get_role_filters(get_user_role()) or None
                user_tables = perms.get("allowed_tables") or None
                allowed_columns = perms.get("allowed_columns") or None
            else:
                role_filters = get_role_filters(get_user_role()) or None
                user_tables = None
                allowed_columns = None
            try:
                sql_query = secure_sql(
                    sql_query,
                    tenant=tenant,
                    extra_filters=role_filters,
                    allowed_tables=user_tables,
                    allowed_columns=allowed_columns,
                )
                logger.info(f"SQL secured (tenant+RLS+user): {sql_query}")
            except SqlSecurityError as sec_e:
                logger.warning(f"SECURITY ALERT: запрос отклонён политикой: {sec_e}")
                return (
                    f"Ошибка безопасности: {sec_e} Разрешён только SELECT в рамках вашего доступа."
                )

            result = client.query(sql_query)

            if not result.result_rows:
                return "Запрос выполнен успешно, но данных не найдено."

            # Формируем читаемый ответ
            header = " | ".join(result.column_names)
            rows = [" | ".join(map(str, row)) for row in result.result_rows]
            return header + "\n" + "\n".join(rows)

        except Exception as e:
            logger.error(f"ClickHouse execution error: {str(e)}")
            return f"Ошибка выполнения SQL: {str(e)}. Исправьте запрос и попробуйте снова."


class FetchWrenContextTool(BaseTool):
    name: str = "fetch_wren_context"
    description: str = "Получает семантический контекст (схему и правила бизнес-логики) из WrenAI для правильного составления SQL."

    def _run(self, question: str) -> str:
        """Fetch semantic context from WrenAI."""
        from app.services.wrenai_client import wren_client

        return wren_client.get_semantic_context(question)


class ChromaSearchTool(BaseTool):
    name: str = "search_tax_code_chroma"
    description: str = "Ищет статьи и законы в базе знаний (Налоговый кодекс) для консультации по правилам бизнеса. Использует векторный поиск ChromaDB через RAG Service."

    def _run(self, query: str) -> str:
        """Search in ChromaDB Vector Knowledge Base."""
        try:
            from app.services.rag_service import get_rag_context

            context = get_rag_context(query)
            if not context or context.strip() == "":
                return "В нормативной базе ничего не найдено по данному вопросу."
            return f"Найденные нормативные документы:\n{context}"
        except Exception as e:
            logger.error(f"ChromaDB search error: {str(e)}")
            return f"Ошибка при поиске по базе знаний: {str(e)}"


class SearchPastReportsTool(BaseTool):
    name: str = "search_past_reports"
    description: str = "Ищет ранее сгенерированные отчеты и дашборды по корпоративному каталогу. Если найдено, возвращает полный JSON с данными."

    def _run(self, query: str) -> str:
        try:
            from app.services.rag_service import search_dashboards

            docs = search_dashboards(query, k=1)
            if docs:
                doc = docs[0]
                # Простая эвристика релевантности: если текст похож
                return f"Найден релевантный сохраненный дашборд:\n{doc.metadata.get('full_json')}"
        except Exception as e:
            logger.error(f"Error searching dashboards: {e}")

        return "Ранее сгенерированные отчеты по данному запросу не найдены. Требуется полный цикл генерации."


class EmailDeliveryTool(BaseTool):
    name: str = "email_delivery"
    description: str = "Отправляет текст или дашборд на корпоративную почту. Используйте, если пользователь просит 'отправь', 'перешли на почту' или 'поделись по email'."

    def _run(self, payload: str) -> str:
        import os
        import smtplib
        from email.message import EmailMessage

        smtp_server = os.getenv("SMTP_SERVER")
        admin_email = os.getenv("ADMIN_EMAIL", "chief@tax.gov.by")

        if not smtp_server:
            logger.warning("SMTP_SERVER not set. Mocking delivery.")
            logger.info(f"MOCK EMAIL DELIVERY to {admin_email}:\n{payload}")

            # сохраняем мок на диск
            out_dir = os.path.join(
                os.path.abspath(os.path.dirname(__file__)), "..", "out", "mock_emails"
            )
            os.makedirs(out_dir, exist_ok=True)
            import json
            import uuid

            file_path = os.path.join(out_dir, f"email_{uuid.uuid4().hex[:8]}.json")
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump({"to": admin_email, "content": payload}, f, ensure_ascii=False, indent=2)

            return "Отправка симулирована (SMTP не настроен). Отчет успешно 'отправлен' на корпоративную почту."

        try:
            msg = EmailMessage()
            msg.set_content(payload)
            msg["Subject"] = "Аналитический отчет из Prototip BI"
            msg["From"] = os.getenv("SMTP_USER", "prototip@example.com")
            msg["To"] = admin_email

            server = smtplib.SMTP(smtp_server, int(os.getenv("SMTP_PORT", 587)))
            server.starttls()
            if os.getenv("SMTP_USER") and os.getenv("SMTP_PASS"):
                server.login(os.getenv("SMTP_USER"), os.getenv("SMTP_PASS"))
            server.send_message(msg)
            server.quit()

            logger.info(f"Sending via {smtp_server} to {admin_email}...")
            return "Отчет успешно отправлен на корпоративную почту."
        except Exception as e:
            logger.error(f"Failed to send to Email: {e}")
            return f"Ошибка отправки email: {e}"
