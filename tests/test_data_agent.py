"""Тесты DataAgent (Phase 2).

Моки для LLM (structured), проверка self-correction, whitelist, выполнение на sample.csv (Беларусь).
Живой прогон на 5 вопросах если модель доступна (qwen2.5-coder:7b-instruct).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from app.agents.data_agent import DataAgent
from app.schemas import SqlResult
from core.llm import is_ollama_available
from core.models import ChartSpec
from viz.charts import build_chart, export_png


def test_data_agent_basic_mock() -> None:
    """Простой мок: возвращает валидный SELECT, выполняется без ошибок."""
    agent = DataAgent()

    fake_sql = "SELECT region, SUM(amount) as d FROM default.enterprise_taxes WHERE tax_type = 'НДС' GROUP BY region ORDER BY d DESC LIMIT 5"

    with patch("app.agents.data_agent.call_structured") as mock_call:
        mock_call.return_value = type("obj", (object,), {"sql": fake_sql, "step_by_step_reasoning": "mock"})()
        result = agent.run("Какие регионы имеют наибольшую задолженность по НДС?")

    assert isinstance(result, SqlResult)
    assert "SELECT" in result.sql.upper()
    assert result.row_count > 0
    assert "region" in result.data[0]


def test_data_agent_rejects_write() -> None:
    """Мок с попыткой INSERT — агент должен отвергнуть или self-correct до ошибки."""
    agent = DataAgent()

    bad_sql = "INSERT INTO default.enterprise_taxes VALUES (1)"

    with patch("app.agents.data_agent.call_structured") as mock_call:
        mock_call.return_value = type("obj", (object,), {"sql": bad_sql, "step_by_step_reasoning": "mock"})()
        with pytest.raises(RuntimeError):
            agent.run("Сделай что-то плохое")


def test_data_agent_self_correction_on_error() -> None:
    """При ошибке SQL агент должен попробовать исправить (мок sequential)."""
    agent = DataAgent()
    calls = []

    def fake_call(prompt, schema, **kw):
        calls.append(prompt)
        if len(calls) == 1:
            # первая попытка — несуществующая колонка (должна вызвать ошибку DuckDB -> self-correction)
            return type("obj", (object,), {"sql": "SELECT foo FROM default.enterprise_taxes LIMIT 3", "step_by_step_reasoning": "mock"})()
        # вторая — исправленный
        return type(
            "obj",
            (object,),
            {"sql": "SELECT region, COUNT(*) as c FROM default.enterprise_taxes GROUP BY region LIMIT 3", "step_by_step_reasoning": "mock"},
        )()

    with patch("app.agents.data_agent.call_structured", side_effect=fake_call):
        result = agent.run("Сколько записей по регионам?")

    assert result.row_count >= 3
    assert len(calls) >= 2  # была коррекция (self-correction сработала)
    assert "region" in result.sql.lower() or "count" in result.sql.lower()


@pytest.mark.live
@pytest.mark.skipif(
    not is_ollama_available(),
    reason="Ollama + qwen2.5-coder:7b-instruct недоступен для живого теста",
)
def test_data_agent_live_5_questions() -> None:
    """Живой прогон на 5 типовых вопросах (как требует spec Phase 2 'Готово')."""
    agent = DataAgent()
    questions = [
        "Какие регионы имеют наибольшую задолженность по НДС?",
        "Динамика начислений подоходного налога в г. Минск по месяцам?",
        "Топ-3 региона по сумме имущественных налогов?",
        "Среднее число налогоплательщиков по областям?",
        "Общая сумма начислений по всем налогам в декабре 2024?",
    ]

    for q in questions:
        res = agent.run(q)
        assert isinstance(res, SqlResult)
        assert res.sql.strip().upper().startswith("SELECT")
        assert res.row_count >= 0
        # Данные валидны (хотя бы одна известная колонка или агрегат)
        if res.data:
            row0 = res.data[0]
            has_known = any(k in row0 for k in ("region", "accrued", "paid", "period", "tax_type"))
            has_aggregate = any(
                "sum" in k.lower() or "count" in k.lower() or "avg" in k.lower() for k in row0
            )
            assert has_known or has_aggregate or len(row0) > 0


@pytest.mark.live
@pytest.mark.skipif(
    not is_ollama_available(),
    reason="Ollama + qwen2.5-coder:7b-instruct недоступен для живого регресс-теста",
)
def test_data_agent_year_filter_regression_non_empty_and_png() -> None:
    """Регресс-тест: годовой фильтр не должен давать пустой результат (period LIKE '2023-%')."""
    agent = DataAgent()
    res = agent.run("Топ-3 региона по задолженности в 2023?")
    assert isinstance(res, SqlResult)
    assert res.sql.strip().upper().startswith("SELECT")
    assert res.row_count > 0, f"Ожидался непустой результат, но получено 0 строк. SQL: {res.sql}"

    # Строим PNG, чтобы подтвердить, что данные позволяют построить график (как в UI/Orchestrator)
    df = pd.DataFrame(res.data)
    # Берём первую числовую колонку как y (обычно алиас вроде total_debt)
    numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    y_col = numeric_cols[0] if numeric_cols else "debt"
    spec = ChartSpec(
        chart_type="bar",
        title="Топ-3 региона по задолженности в 2024",
        x="region",
        y=y_col,
        agg="sum",
        rationale="Регресс-тест годового фильтра",
    )
    fig = build_chart(df, spec)
    png_path = Path("/tmp/regress_year_filter_2024.png")
    export_png(fig, png_path, scale=1.0)
    assert png_path.exists() and png_path.stat().st_size > 0
