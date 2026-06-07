"""Лёгкий пайплайн слайда: data → chart → analyst (без полного PlannerAgent)."""

from __future__ import annotations

import logging
from typing import Any

from app.agents.models import AskResult, ChartAgentResult, SqlResult
from app.chart_repair import repair_chart_spec
from core.models import ChartSpec

logger = logging.getLogger("SlidePipeline")


def build_slide_ask_result(question: str, executor: Any) -> AskResult:
    """Собирает AskResult для одного слайда презентации через листовых агентов."""
    q = question.strip()
    sql_res = executor.run("data_agent", q)
    if not isinstance(sql_res, SqlResult) or not sql_res.success:
        return AskResult(
            question=q,
            sql=getattr(sql_res, "sql", "") or "",
            data=[],
            success=False,
            error=getattr(sql_res, "error", None) or "DataAgent не вернул данные",
            reasoning="Slide pipeline: ошибка на этапе data_agent",
        )

    data = sql_res.data or []
    if not data:
        return AskResult(
            question=q,
            sql=sql_res.sql,
            data=[],
            success=False,
            error="Пустой результат SQL",
            reasoning="Slide pipeline: нет строк данных",
        )

    chart_res = executor.run("chart_agent", q, data=data)
    chart_spec: ChartSpec | None = None
    if isinstance(chart_res, ChartAgentResult) and chart_res.success and chart_res.spec:
        chart_spec = repair_chart_spec(chart_res.spec, data, question=q)

    analyst_kwargs: dict[str, Any] = {"data": data, "source_sql": sql_res.sql}
    if chart_spec is not None:
        analyst_kwargs["chart_spec"] = chart_spec.model_dump()

    analysis = executor.run("analyst_agent", q, **analyst_kwargs)
    success = chart_spec is not None or getattr(analysis, "success", True)

    return AskResult(
        question=q,
        sql=sql_res.sql,
        data=data,
        chart_spec=chart_spec,
        analysis=analysis if getattr(analysis, "insights", None) else None,
        success=success and getattr(analysis, "success", True),
        error=None if success else "Не удалось построить график для слайда",
        reasoning="Slide pipeline: data_agent → chart_agent → analyst_agent",
    )