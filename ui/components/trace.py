"""Рендер трассировки PlannerAgent в Streamlit."""

from __future__ import annotations

import json
from typing import Any

import streamlit as st

from app.agents.models import AgentResult, PlannerTrace


def _trace_from_result(res: Any) -> PlannerTrace | None:
    if res is None:
        return None
    trace = getattr(res, "trace", None)
    if isinstance(trace, PlannerTrace):
        return trace
    if isinstance(res, dict):
        raw = res.get("trace")
        if isinstance(raw, dict):
            return PlannerTrace.model_validate(raw)
        if isinstance(raw, PlannerTrace):
            return raw
    return None


def render_planner_trace(res: Any, *, key_prefix: str = "trace") -> None:
    """Expander «Что было сделано» + скачивание JSON trace."""
    trace = _trace_from_result(res)
    if trace is None:
        return

    plan = trace.executed_plan
    steps = trace.plan_execution or []
    if not plan and not steps:
        return

    with st.expander("Что было сделано", expanded=False):
        if plan:
            st.caption(f"**Стратегия:** {plan.strategy or '—'}")
            st.caption(f"**Задач в плане:** {len(plan.tasks)}")
            for task in plan.tasks:
                deps = f" (зависит от: {', '.join(task.depends_on)})" if task.depends_on else ""
                st.markdown(f"- `{task.id}` · **{task.agent_name}** — {task.description}{deps}")

        if steps:
            st.markdown("##### Выполнение")
            for step in steps:
                status_label = "Успешно" if step.status == "успешно" else "Ошибка"
                st.markdown(
                    f"**{step.num}. {step.agent_name}** ({status_label}) — {step.description}\n\n"
                    f"{step.brief_result}"
                )

        if hasattr(res, "model_dump"):
            payload = res.model_dump(mode="json")
        elif isinstance(res, dict):
            payload = res
        else:
            payload = {"result_type": type(res).__name__}

        trace_json = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
        st.download_button(
            "Скачать trace (JSON)",
            data=trace_json.encode("utf-8"),
            file_name="planner_trace.json",
            mime="application/json",
            key=f"dl_trace_{key_prefix}",
            use_container_width=True,
        )


def result_has_trace(res: Any) -> bool:
    return _trace_from_result(res) is not None


def ensure_trace_on_agent_result(res: AgentResult, trace: PlannerTrace) -> AgentResult:
    res.trace = trace
    return res