"""Слой выполнения агентов: AgentRegistry + AgentExecutor.

Подготовка к PlannerAgent:
- Централизованная регистрация агентов по имени.
- Единая точка вызова с логированием и простой обработкой ошибок.
- Все вызовы возвращают AgentResult (или наследника при успехе).

Orchestrator постепенно мигрирует на использование executor.run(...) вместо
прямых вызовов self.xxx_agent.run(...).
"""

from __future__ import annotations

import logging
import time
from typing import Any

from app.agents.base_agent import BaseAgent
from app.agents.models import AgentResult
from core.llm import setup_logging

setup_logging()
logger = logging.getLogger("AgentExecutor")


class AgentRegistry:
    """Реестр агентов по имени (name).

    Позволяет регистрировать экземпляры BaseAgent и получать их по имени.
    Используется Executor и в будущем Planner.
    """

    def __init__(self) -> None:
        self._agents: dict[str, BaseAgent] = {}

    def register(self, agent: BaseAgent) -> None:
        """Зарегистрировать агент. Ключ — agent.name."""
        if not agent.name:
            raise ValueError("Agent must have a non-empty name")
        self._agents[agent.name] = agent
        logger.info(f"[AgentRegistry] registered: {agent.name} ({agent.__class__.__name__})")

    def get(self, name: str) -> BaseAgent:
        """Получить агент по имени. Поднимает KeyError если не найден."""
        if name not in self._agents:
            raise KeyError(f"Agent '{name}' not registered. Available: {list(self._agents.keys())}")
        return self._agents[name]

    def list_agents(self) -> list[str]:
        return list(self._agents.keys())

    def get_capabilities(self, name: str) -> dict[str, Any]:
        agent = self.get(name)
        return agent.get_capabilities()

    def __contains__(self, name: str) -> bool:
        return name in self._agents


class AgentExecutor:
    """Исполнитель вызовов агентов с логированием и graceful error handling.

    Основной API для кода, который хочет вызвать агент по имени:
        result = executor.run("data_agent", question)
        # при успехе result — SqlResult (наследник AgentResult)
        # при ошибке  result — AgentResult(success=False, error=..., reasoning=...)
    """

    def __init__(self, registry: AgentRegistry | None = None) -> None:
        self.registry = registry or AgentRegistry()

    def register(self, agent: BaseAgent) -> None:
        """Удобный прокси на реестр."""
        self.registry.register(agent)

    def run(self, agent_name: str, request: Any, **call_kwargs: Any) -> AgentResult:
        """Выполнить агент по имени.

        Логирует каждый вызов в едином стиле.
        При исключении внутри агента: логирует, возвращает AgentResult(success=False).
        Не глотает ошибку полностью — caller может проверить .success.
        """
        start = time.time()
        logger.info(
            f"[AgentExecutor] call: agent={agent_name} request_type={type(request).__name__}"
        )

        try:
            agent = self.registry.get(agent_name)
            raw_result = agent.run(request, **call_kwargs)

            # Убеждаемся, что результат — AgentResult (или наследник)
            if not isinstance(raw_result, AgentResult):
                # Редкий случай: старый агент вернул что-то другое.
                # Оборачиваем, чтобы контракт соблюдался.
                raw_result = AgentResult(
                    success=True,
                    reasoning=f"Wrapped non-AgentResult from {agent_name}",
                )

            # Если reasoning пустой — заполняем минимально (будет усилено в самих агентах)
            if not getattr(raw_result, "reasoning", ""):
                raw_result.reasoning = f"Completed by {agent_name} via AgentExecutor"

            elapsed = int((time.time() - start) * 1000)
            logger.info(
                f"[AgentExecutor] done: agent={agent_name} success={raw_result.success} ({elapsed}ms)"
            )
            return raw_result

        except Exception as exc:
            elapsed = int((time.time() - start) * 1000)
            logger.info(f"[AgentExecutor] error: agent={agent_name} {exc} ({elapsed}ms)")
            return AgentResult(
                success=False,
                reasoning=f"Executor caught exception while running {agent_name}",
                error=str(exc),
            )

    def get_agent(self, name: str) -> BaseAgent:
        """Прямой доступ к агенту (для редких случаев, когда нужен сам объект)."""
        return self.registry.get(name)

    def list_agents(self) -> list[str]:
        return self.registry.list_agents()
