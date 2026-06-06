"""Тесты factory.get_planner singleton."""

from __future__ import annotations

from app.agents.factory import get_planner
from app.agents.planner_agent import PlannerAgent


def test_get_planner_singleton():
    p1 = get_planner()
    p2 = get_planner()
    assert p1 is p2
    assert isinstance(p1, PlannerAgent)


def test_get_planner_fresh_isolated():
    p1 = get_planner()
    p2 = get_planner(fresh=True)
    assert p1 is not p2