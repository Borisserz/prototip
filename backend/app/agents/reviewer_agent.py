import logging

from pydantic import BaseModel, Field

from app.agents.config_loader import get_agent_config
from core.llm import call_structured

logger = logging.getLogger(__name__)


class ReviewDecision(BaseModel):
    is_good: bool = Field(description="Достаточно ли глубоки выводы, или это просто пересказ цифр?")
    feedback: str = Field(description="Критика выводов для AnalystAgent (если is_good=False).")


class ReviewerAgent:
    def __init__(self):
        self.name = "reviewer_agent"
        cfg = get_agent_config("reviewer_agent")
        self.system_prompt = f"""Ты — {cfg.role}. {cfg.goal}

{cfg.rules}"""

    def evaluate(
        self, question: str, analysis: dict, raw_data: list[dict] = None
    ) -> ReviewDecision:
        if not analysis:
            return ReviewDecision(is_good=False, feedback="Пустой анализ.")

        data_preview = ""
        if raw_data:
            # Предотвращаем огромные дампы
            data_preview = f"\nФрагмент исходных данных (первые 3 строки):\n{raw_data[:3]}\nОбрати внимание, использовал ли Аналитик эти конкретные цифры в своих выводах или ограничился общими фразами.\n"

        prompt = f"""
Вопрос пользователя: {question}
{data_preview}
Текущие выводы от AnalystAgent:
Инсайты: {analysis.get("insights")}
Ключевой вывод: {analysis.get("key_conclusion")}
Аномалия/Тренд: {analysis.get("anomaly_or_trend")}

Оцени глубину этих выводов. Достаточно ли они качественные для бизнес-отчета?
"""
        try:
            logger.info("Выполняется Reviewer Pipeline...")
            decision = call_structured(
                prompt, ReviewDecision, system=self.system_prompt, agent_name=self.name
            )
            logger.info(f"Review Result: good={decision.is_good}, feedback={decision.feedback}")
            return decision
        except Exception as e:
            logger.error(f"Ошибка ReviewerAgent: {e}")
            return ReviewDecision(is_good=True, feedback="Fallback: Пропущена проверка.")
