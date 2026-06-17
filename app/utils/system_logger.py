import logging
import threading
from app.utils.clickhouse_client import ch_client

logger = logging.getLogger("SystemAudit")

class SystemAuditLogger:
    def __init__(self):
        self._init_db()

    def _init_db(self):
        try:
            ddl = """
            CREATE TABLE IF NOT EXISTS default.system_audit_logs (
                timestamp DateTime,
                agent_name String,
                model String,
                prompt_tokens Int32,
                completion_tokens Int32,
                duration_ms Int32,
                error_status String,
                user_role String
            ) ENGINE = MergeTree()
            ORDER BY timestamp
            """
            ch_client.execute(ddl)
            logger.info("Таблица system_audit_logs успешно инициализирована.")
        except Exception as e:
            logger.error(f"Ошибка создания system_audit_logs: {e}")

    def log_llm_call_async(self, agent_name: str, model: str, prompt_tokens: int, completion_tokens: int, duration_ms: int, error_status: str = "", user_role: str = "system"):
        def _insert():
            try:
                # Basic escaping for error_status
                safe_err = error_status.replace("'", "''").replace("\\", "\\\\") if error_status else ""
                safe_agent = agent_name.replace("'", "''") if agent_name else "unknown"
                safe_model = model.replace("'", "''") if model else "unknown"
                safe_role = user_role.replace("'", "''") if user_role else "system"
                
                query = f"""
                INSERT INTO default.system_audit_logs 
                (timestamp, agent_name, model, prompt_tokens, completion_tokens, duration_ms, error_status, user_role)
                VALUES
                (now(), '{safe_agent}', '{safe_model}', {prompt_tokens}, {completion_tokens}, {duration_ms}, '{safe_err}', '{safe_role}')
                """
                ch_client.execute(query)
            except Exception as e:
                logger.error(f"Ошибка записи лога аудита в ClickHouse: {e}")
                
        threading.Thread(target=_insert, daemon=True).start()

audit_logger = SystemAuditLogger()
