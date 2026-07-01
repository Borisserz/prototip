"""Базовый интерфейс агента (для ).

Ре-экспорт из base_agent.py (унифицированная реализация BaseAgent с AgentResult,
name/description, get_capabilities). Старый код, импортирующий из app.agents.base,
продолжает работать.
"""

from __future__ import annotations

from app.agents.base_agent import BaseAgent  # noqa: F401

__all__ = ["BaseAgent"]
