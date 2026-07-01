"""Минимальные тесты на новые компоненты (BaseAgent, AgentRegistry, AgentExecutor, AgentResult).

Не требуют Ollama. Используют моки.
"""

from __future__ import annotations

from typing import Any

from app.agents.base_agent import BaseAgent
from app.agents.executor import AgentExecutor, AgentRegistry
from app.agents.models import AgentResult


class _DummyAgent(BaseAgent):
    """Простой тестовый агент для проверки Base + Executor."""

    name = "dummy"
    description = "Dummy agent for unit tests of BaseAgent/Executor"

    def run(self, request: Any, **kwargs: Any) -> AgentResult:
        q = str(request)[:30]
        return AgentResult(
            success=True,
            reasoning=f"dummy processed: {q}",
        )


def test_base_agent_interface_and_capabilities():
    ag = _DummyAgent()
    assert ag.name == "dummy"
    assert "Dummy agent" in ag.description
    caps = ag.get_capabilities()
    assert caps["name"] == "dummy"
    assert "class" in caps


def test_agent_result_is_base_for_results():
    # Проверка, что наши result-модели — наследники (унификация)
    from app.agents.models import AnalysisResult, ChartAgentResult, DashboardResult, SqlResult

    assert issubclass(SqlResult, AgentResult)
    assert issubclass(AnalysisResult, AgentResult)
    assert issubclass(ChartAgentResult, AgentResult)
    assert issubclass(DashboardResult, AgentResult)

    # Можно создать с reasoning
    r = AgentResult(success=False, reasoning="test fail", error="boom")
    assert not r.success
    assert r.reasoning == "test fail"


def test_registry_register_and_get():
    reg = AgentRegistry()
    ag = _DummyAgent()
    reg.register(ag)
    assert "dummy" in reg
    got = reg.get("dummy")
    assert got is ag
    assert "dummy" in reg.list_agents()


def test_executor_run_success_and_logging(capsys):
    reg = AgentRegistry()
    reg.register(_DummyAgent())
    ex = AgentExecutor(reg)

    res = ex.run("dummy", "какой-то вопрос про задолженность")
    assert isinstance(res, AgentResult)
    assert res.success is True
    assert "dummy processed" in res.reasoning

    # Логи executor должны были сработать (хотя бы "call" и "done")
    # (setup_logging в executor пишет в stdout + файл; здесь проверяем что не упало)


def test_executor_error_returns_failed_agent_result():
    reg = AgentRegistry()

    class _Boom(BaseAgent):
        name = "boom"
        description = "always fails"

        def run(self, request: Any, **kwargs: Any) -> AgentResult:
            raise RuntimeError("intentional boom for test")

    reg.register(_Boom())
    ex = AgentExecutor(reg)

    res = ex.run("boom", "q")
    assert isinstance(res, AgentResult)
    assert res.success is False
    assert res.error is not None
    assert "boom" in (res.reasoning or "")
