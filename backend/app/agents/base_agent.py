"""Базовый абстрактный класс агента.

Требования:
- Поля класса/экземпляра: name, description
- Абстрактный метод run(self, request: Any) -> AgentResult
- Метод get_capabilities(self) -> dict

Все агенты проекта наследуются от BaseAgent.
Возвращаемые значения — AgentResult или его наследники (см. app/agents/models.py).

Практически run принимает разные формы request (str / InputModel / (q, data) и т.д.)
в зависимости от агента — это сохраняет существующие вызовы Orchestrator/UI без изменений.

НЕ ломает ChartAgent / PresentationAgent / viz.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.agents.models import AgentResult


class BaseAgent(ABC):
    """Абстрактный базовый агент.

    Каждый конкретный агент (Data, Analyst, Chart, Dashboard, Presentation) обязан:
    - задать class attr name и description
    - реализовать run(...) возвращающий AgentResult (или наследника)
    - при необходимости переопределить get_capabilities()
    """

    # Class-level defaults (конкретные агенты переопределяют)
    name: str = "base_agent"
    description: str = "Базовый агент (не следует использовать напрямую)"

    @abstractmethod
    def run(self, request: Any, *args: Any, **kwargs: Any) -> AgentResult:
        """Выполнить работу агента.

        request — основной вход (вопрос-строка, Pydantic-модель запроса, dict и т.д.).
        Конкретная семантика зависит от агента. Метод обязан вернуть AgentResult
        (или наследника: SqlResult, AnalysisResult, ChartAgentResult, DashboardResult,
        PresentationResult и т.п.).

        Реализации могут также предоставлять удобные методы run_input(...) или
        перегруженные run(question, data, ...), но базовый контракт — этот run.
        """
        raise NotImplementedError

    def get_capabilities(self) -> dict[str, Any]:
        """Возвращает описание возможностей агента (для Planner / introspection)."""
        return {
            "name": self.name,
            "description": self.description,
            "class": self.__class__.__name__,
        }

    def __repr__(self) -> str:  # pragma: no cover
        return f"<{self.__class__.__name__} name={self.name}>"
