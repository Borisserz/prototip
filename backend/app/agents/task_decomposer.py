import logging
from pydantic import BaseModel, Field
from core.llm import call_structured
from app.agents.config_loader import get_agent_config
logger = logging.getLogger(__name__)

class DecompositionResult(BaseModel):
    is_complex: bool = Field(description="Требует ли вопрос разбиения на несколько независимых подзапросов к БД?")
    tasks: list[str] = Field(description="Список подзадач на естественном языке. Если вопрос простой, здесь должен быть один элемент.")

class TaskDecompositionAgent:
    def __init__(self):
        self.name = "TaskDecompositionAgent"
        cfg = get_agent_config("task_decomposer")
        self.system_prompt = f"""Ты — {cfg.role}. {cfg.goal}

{cfg.rules}

=== FEW-SHOT EXAMPLES ===
{cfg.few_shot}"""

    def decompose(self, question: str, context: str) -> list[str]:
        prompt = f"""
Контекст (метаданные таблиц):
{context}

Вопрос пользователя: {question}

Разбей вопрос на подзадачи, если это необходимо.
"""
        try:
            logger.info("Выполняется Task Decomposition...")
            res = call_structured(prompt, DecompositionResult, system=self.system_prompt, agent_name=self.name)
            if res.is_complex and res.tasks:
                logger.info(f"Task Decomposer разбил задачу на {len(res.tasks)} частей: {res.tasks}")
                return res.tasks
            else:
                logger.info("Task Decomposer оставил задачу целой.")
                return [question]
        except Exception as e:
            logger.error(f"Ошибка в TaskDecompositionAgent: {e}")
            return [question]
