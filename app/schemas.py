"""Pydantic контракты для агентов (Phase 2+).

Тонкая фасада: реальные определения перенесены в app/agents/models.py для унификации
перед PlannerAgent. Все импорты из app.schemas продолжают работать (обратная совместимость
для main.py, ui/, тестов и API response_model).

ВАЖНО: все данные между модулями — только через Pydantic-модели.
"""

from __future__ import annotations

# Полная унификация: все основные модели теперь живут в app/agents/models.py
# (включая AgentResult как базовый для результатов агентов + Task/Plan/AgentCall).
# Здесь просто ре-экспорт, чтобы не ломать существующие импорты по всей кодовой базе.
from app.agents.models import (  # noqa: F401
    AgentCall,
    AgentResult,
    AnalysisResult,
    AskResult,
    ChartAgentInput,
    ChartAgentResult,
    DashboardLayout,
    DashboardRequest,
    DashboardResult,
    DataAgentInput,
    DeckNarrative,
    DrilldownContext,
    KpiCard,
    Plan,
    PlanExecutionStep,
    PlannerTrace,
    PresentationInput,
    PresentationRequest,
    PresentationResult,
    PresentationUpdateRequest,
    QuestionBlock,
    SlideData,
    SlideUpdate,
    SqlResult,
    Task,
)

# ChartSpec остаётся в core (контракт viz/ и детерминированного рендера).
# Ре-экспортируем для удобства, чтобы `from app.schemas import ChartSpec` тоже работал.
from core.models import ChartSpec  # noqa: F401

__all__ = [
    "AgentResult",
    "AnalysisResult",
    "AskResult",
    "ChartAgentInput",
    "ChartAgentResult",
    "ChartSpec",
    "DashboardLayout",
    "DashboardRequest",
    "DashboardResult",
    "DataAgentInput",
    "DrilldownContext",
    "DeckNarrative",
    "KpiCard",
    "Plan",
    "PresentationInput",
    "PresentationRequest",
    "PresentationResult",
    "PresentationUpdateRequest",
    "QuestionBlock",
    "SlideData",
    "SlideUpdate",
    "SqlResult",
    "Task",
    "AgentCall",
    "PlanExecutionStep",
    "PlannerTrace",
]
