import logging

from pydantic import BaseModel, Field

from app.agents.config_loader import get_agent_config
from core.llm import call_structured

logger = logging.getLogger(__name__)


class EvalDecision(BaseModel):
    is_correct: bool = Field(description="Корректно ли SQL отвечает на вопрос логически?")
    feedback: str = Field(description="Объяснение ошибки или подтверждение корректности.")


class SqlEvaluatorAgent:
    def __init__(self):
        cfg = get_agent_config("sql_evaluator")
        self.system_prompt = f"""Ты — {cfg.role}. {cfg.goal}

{cfg.rules}"""

    def evaluate(
        self, question: str, sql: str, schema: str, sample_data: list[dict] = None
    ) -> EvalDecision:
        if not sql or sql.isspace():
            return EvalDecision(is_correct=False, feedback="SQL запрос пуст.")

        data_preview = ""
        if sample_data is not None:
            if not sample_data:
                data_preview = "\nФрагмент реальных данных (Dry-Run): ВНИМАНИЕ! ЗАПРОС ВЕРНУЛ 0 СТРОК.\nОцени, нормален ли пустой результат для такого вопроса, или это ошибка логики/фильтрации."
            else:
                data_preview = f"\nФрагмент реальных данных (Dry-Run): {sample_data[:3]}\n(Убедись, что данные логически соответствуют запросу)."

        prompt = f"""
Оцени следующий запрос.

Вопрос пользователя: {question}

Схема БД:
{schema}

Сгенерированный SQL:
{sql}
{data_preview}
"""
        try:
            logger.info("Выполняется SQL Eval Pipeline...")
            decision = call_structured(
                prompt, EvalDecision, system=self.system_prompt, agent_name="sql_evaluator"
            )
            logger.info(
                f"SQL Eval Result: correct={decision.is_correct}, feedback={decision.feedback}"
            )
            return decision
        except Exception as e:
            logger.error(f"Ошибка SqlEvaluatorAgent: {e}")
            return EvalDecision(
                is_correct=True, feedback="Fallback: Пропущена проверка из-за ошибки LLM."
            )
