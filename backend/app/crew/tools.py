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
        import re
        try:
            client = clickhouse_connect.get_client(
            host=os.getenv("CLICKHOUSE_HOST", "localhost"),
            port=int(os.getenv("CLICKHOUSE_PORT", "8123")),
            username=os.getenv("CLICKHOUSE_USER", "default"),
            password=os.getenv("CLICKHOUSE_PASSWORD", ""),
        )
            logger.info(f"Executing SQL via CrewAI Tool: {sql_query}")
            
            # Строгая защита от SQL-инъекций и деструктивных действий (Харденинг)
            forbidden_keywords = [
                r"\bDROP\b", r"\bDELETE\b", r"\bUPDATE\b", r"\bALTER\b", 
                r"\bINSERT\b", r"\bTRUNCATE\b", r"\bGRANT\b", r"\bREVOKE\b", r"\bSYSTEM\b"
            ]
            upper_query = sql_query.upper()
            
            for pattern in forbidden_keywords:
                if re.search(pattern, upper_query):
                    logger.warning(f"SECURITY ALERT: Blocked destructive query: {sql_query}")
                    return "Ошибка безопасности: Вы пытаетесь выполнить запрещенную операцию (DROP/DELETE/ALTER/etc). Разрешен только SELECT."
                
            # Проверяем, что это запрос на чтение (допускаем CTE через WITH)
            if not (upper_query.strip().startswith("SELECT") or upper_query.strip().startswith("WITH")):
                return "Ошибка: Запрос должен начинаться с SELECT или WITH."
                
            import sqlglot
            from sqlglot import exp

            from app.agent_context import get_user_role
            
            role = get_user_role()
            region_filter = None
            if role == "grodno_manager":
                region_filter = "г. Гродно"
            elif role == "minsk_manager":
                region_filter = "г. Минск"
                
            if region_filter:
                try:
                    # Подмешиваем WHERE RLS через sqlglot
                    parsed = sqlglot.parse_one(sql_query, read="clickhouse")
                    where_clause = exp.condition(f"region = '{region_filter}'")
                    parsed = parsed.where(where_clause)
                    sql_query = parsed.sql(dialect="clickhouse")
                    logger.info(f"RLS Applied. Modified Query: {sql_query}")
                except Exception as parse_e:
                    logger.warning(f"Failed to parse query for RLS: {parse_e}")
                    
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
            
            # Save mock to disk
            out_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), "..", "out", "mock_emails")
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
