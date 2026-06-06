"""Минимальные тесты на новые компоненты Phase 2/3 (BaseAgent, AgentRegistry, AgentExecutor, AgentResult).

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
    # Проверка, что наши result-модели — наследники (унификация Phase 1)
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


def test_orchestrator_uses_executor_and_agents_have_reasoning():
    """Проверка, что Orchestrator теперь использует executor и результаты несут reasoning."""
    from unittest.mock import patch

    from app.agents.models import AnalysisResult, SqlResult
    from app.orchestrator import Orchestrator
    from core.models import ChartSpec

    orch = Orchestrator()
    assert hasattr(orch, "executor")
    assert "data_agent" in orch.executor.list_agents()

    fake_sql = SqlResult(sql="SELECT 1", data=[{"a": 1}], row_count=1, reasoning="data r")
    fake_an = AnalysisResult(insights=["1", "2", "3"], key_conclusion="ok", reasoning="an r")
    fake_spec = ChartSpec(chart_type="bar", title="t", x="a", y="a", rationale="test r")

    with (
        patch.object(orch.data_agent, "run", return_value=fake_sql),
        patch.object(orch.analyst_agent, "run", return_value=fake_an),
        patch.object(
            orch.chart_agent,
            "run",
            return_value=type("C", (), {"spec": fake_spec, "success": True, "reasoning": "c r"})(),
        ),
        patch("app.orchestrator.build_chart"),
        patch("app.orchestrator.export_png"),
    ):
        res = orch.ask("Простой вопрос?")

    assert res.success  # AskResult теперь тоже AgentResult
    assert getattr(res, "reasoning", "")
    # Под-результаты тоже должны иметь reasoning (через executor или прямое заполнение)
    if res.analysis:
        assert getattr(res.analysis, "reasoning", "")


def test_planner_repair_plan_adds_missing_depends_on_and_question():
    """Проверка, что _repair_plan чинит deps и question (защита от капризов LLM в Главном агенте)."""
    from app.agents.models import Task
    from app.agents.planner_agent import PlannerAgent

    p = PlannerAgent()

    # План, который LLM мог отдать без depends_on и без "question" в params второй задачи
    bad_tasks = [
        Task(
            id="t1",
            description="Получить данные",
            agent_name="data_agent",
            params={"question": "сводка по налогам"},
            depends_on=[],
        ),
        Task(
            id="t2",
            description="Сделать сводку на основе полученных данных",
            agent_name="analyst_agent",
            params={},  # нет question, нет depends_on — классическая ошибка
            depends_on=[],
        ),
    ]

    repaired = p._repair_plan(bad_tasks)

    # Вторая задача должна получить depends_on на t1
    assert repaired[1].depends_on == ["t1"]
    # И хотя бы пустой question (дальше _invoke_agent подставит original)
    assert "question" in repaired[1].params

    # data_agent не должен был получить лишних deps
    assert repaired[0].depends_on == []
