"""
ForecastAgent — DEPRECATED.

Этот класс заменён ForecastAnalystAgent (app/agents/forecast_analyst_agent.py),
который использует scipy/statsmodels + LLM-нарратив + иммутабельные данные.

Граф (graph.py) маршрутизирует прогнозные вопросы в forecast_node →
ForecastAnalystAgent напрямую, минуя этот класс.

ForecastAgent оставлен ТОЛЬКО как compatibility shim: если где-то во внешнем коде
он всё ещё импортируется, вызов будет делегирован ForecastAnalystAgent с
предупреждением в логах.

Ключевые отличия от старой реализации:
  - Примитивная экстраполяция (polyfit) заменена scipy/statsmodels
  - Мутация входного списка (append на data) устранена — иммутабельность
  - ChartAgentResult адаптируется из ForecastAnalystResult
"""

from __future__ import annotations

import logging
import warnings
from typing import Any

from app.agents.base_agent import BaseAgent
from app.agents.models import ChartAgentResult
from core.models import ChartSpec

logger = logging.getLogger("ForecastAgent")

_DEPRECATION_MSG = (
    "ForecastAgent is deprecated and will be removed in a future release. "
    "Use ForecastAnalystAgent (app/agents/forecast_analyst_agent.py) directly. "
    "In the LangGraph pipeline, forecast questions are handled by forecast_node."
)


class ForecastAgent(BaseAgent):
    """
    DEPRECATED: тонкая обёртка над ForecastAnalystAgent.

    Сохраняет совместимость API (принимает question + data, возвращает
    ChartAgentResult), но делегирует всю логику ForecastAnalystAgent.

    Мутация входного списка устранена — входные данные не изменяются.
    """

    name = "forecast_agent"
    description = "[DEPRECATED] Используйте ForecastAnalystAgent"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        warnings.warn(_DEPRECATION_MSG, DeprecationWarning, stacklevel=2)
        logger.warning("[ForecastAgent] %s", _DEPRECATION_MSG)

    def run(
        self,
        question: str,
        data: list[dict] | None = None,
        **kwargs: Any,
    ) -> ChartAgentResult:
        """
        Делегирует ForecastAnalystAgent.

        НЕ мутирует входной список `data` — создаёт копию через list().
        Возвращает ChartAgentResult для обратной совместимости.
        """
        from app.agents.forecast_analyst_agent import ForecastAnalystAgent

        rows = list(data or [])  # иммутабельная копия — оригинал НЕ изменяется

        agent = ForecastAnalystAgent()
        res = agent.run(question, data=rows, **kwargs)

        if not res.success:
            return ChartAgentResult(
                success=False,
                error=res.error or "ForecastAnalystAgent вернул ошибку",
                reasoning=res.reasoning,
                specs=[
                    ChartSpec(
                        chart_type="line",
                        x="period",
                        y="value",
                        title="Ошибка прогноза",
                        rationale="Нет данных или ошибка вычислений",
                    )
                ],
            )

        # Адаптируем ForecastAnalystResult → ChartAgentResult
        if res.chart_spec:
            specs = [res.chart_spec]
        else:
            specs = [
                ChartSpec(
                    chart_type="area",
                    x="period",
                    y="value",
                    title=f"Прогноз: {question}",
                    rationale="Экстраполяция исторических данных",
                )
            ]

        return ChartAgentResult(
            success=True,
            reasoning=res.narrative or res.reasoning,
            specs=specs,
        )
