"""
Tests for ForecastAgent deprecation shim and graph.py forecast routing fix.

Проверяем:
1. ForecastAgent (shim) НЕ мутирует входной список data
2. ForecastAgent делегирует ForecastAnalystAgent (нет polyfit/numpy в выводе)
3. ForecastAgent возвращает DeprecationWarning при инициализации
4. ForecastAgent.run() возвращает ChartAgentResult (совместимость API)
5. graph.py presenter_node НЕ импортирует ForecastAgent (удалён из prod-пути)
6. route_after_reviewer направляет прогнозные запросы в "forecast" (не "presenter")
7. ForecastAnalystAgent возвращает иммутабельный combined result (data не загрязняется)
"""

from __future__ import annotations

import ast
import sys
import warnings
from pathlib import Path
from unittest.mock import MagicMock, patch

# ── Helpers ────────────────────────────────────────────────────────────────────

BACKEND_DIR = Path(__file__).parent.parent
GRAPH_PY = BACKEND_DIR / "app" / "graph.py"
FORECAST_AGENT_PY = BACKEND_DIR / "app" / "agents" / "forecast_agent.py"

_SAMPLE_DATA = [
    {"period": "2024-01", "amount": 100.0},
    {"period": "2024-02", "amount": 110.0},
    {"period": "2024-03", "amount": 120.0},
    {"period": "2024-04", "amount": 130.0},
    {"period": "2024-05", "amount": 140.0},
    {"period": "2024-06", "amount": 150.0},
]


# ── 1. Immutability: ForecastAgent НЕ мутирует data ───────────────────────────


class TestForecastAgentImmutability:
    """Гарантируем что ForecastAgent.run() не вызывает data.append() на переданном списке."""

    def test_input_list_not_mutated(self):
        """data до и после вызова должны иметь одинаковую длину и содержимое."""
        from core.models import ChartSpec

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from app.agents.forecast_agent import ForecastAgent

        data = list(_SAMPLE_DATA)  # копия
        original_len = len(data)
        original_ids = [id(row) for row in data]

        agent = ForecastAgent()

        # Мокируем ForecastAnalystAgent — chart_spec ДОЛЖЕН быть реальным ChartSpec
        # (Pydantic не принимает MagicMock в specs[])
        real_spec = ChartSpec(
            chart_type="area", x="period", y="amount", title="Прогноз", rationale="тест"
        )
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.narrative = "Тест прогноза"
        mock_result.reasoning = "Расчёт выполнен."
        mock_result.chart_spec = real_spec

        with patch(
            "app.agents.forecast_analyst_agent.ForecastAnalystAgent.run", return_value=mock_result
        ):
            agent.run("прогноз", data=data)

        # Основная проверка: список НЕ изменился
        assert len(data) == original_len, (
            f"data мутировал! было {original_len} строк, стало {len(data)}"
        )
        assert [id(r) for r in data] == original_ids, "Ссылки на объекты изменились"

    def test_none_data_handled(self):
        """ForecastAgent.run(data=None) не должен падать."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from app.agents.forecast_agent import ForecastAgent

        agent = ForecastAgent()

        mock_result = MagicMock()
        mock_result.success = False
        mock_result.error = "Нет данных"
        mock_result.reasoning = "Пустой датасет"
        mock_result.chart_spec = None

        with patch(
            "app.agents.forecast_analyst_agent.ForecastAnalystAgent.run", return_value=mock_result
        ):
            result = agent.run("прогноз", data=None)

        # При ошибке (success=False) агент возвращает ChartAgentResult с success=False
        assert result.success is False
        # Не должно быть исключений Pydantic — specs должен содержать реальный ChartSpec
        assert len(result.specs) >= 1


# ── 2. DeprecationWarning при инициализации ────────────────────────────────────


class TestForecastAgentDeprecation:
    def test_deprecation_warning_raised(self):
        """ForecastAgent должен выдавать DeprecationWarning при __init__."""
        # Убираем кэш модуля чтобы __init__ вызвался свежо
        sys.modules.pop("app.agents.forecast_agent", None)

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            from app.agents.forecast_agent import ForecastAgent

            ForecastAgent()

        deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
        assert len(deprecation_warnings) >= 1, "Ожидался DeprecationWarning, но не был поднят"
        assert "ForecastAgent" in str(deprecation_warnings[0].message)

    def test_returns_chart_agent_result(self):
        """Возвращаемый тип должен быть ChartAgentResult (обратная совместимость)."""
        from app.agents.models import ChartAgentResult
        from core.models import ChartSpec

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from app.agents.forecast_agent import ForecastAgent

        agent = ForecastAgent()

        real_spec = ChartSpec(
            chart_type="area", x="period", y="amount", title="Тест", rationale="тест"
        )
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.narrative = "OK"
        mock_result.reasoning = "OK"
        mock_result.chart_spec = real_spec

        with patch(
            "app.agents.forecast_analyst_agent.ForecastAnalystAgent.run", return_value=mock_result
        ):
            result = agent.run("прогноз", data=list(_SAMPLE_DATA))

        assert isinstance(result, ChartAgentResult)
        assert result.success is True
        assert len(result.specs) == 1


# ── 3. graph.py: presenter_node НЕ импортирует ForecastAgent ──────────────────


class TestGraphNoDependencyOnOldForecastAgent:
    """AST-анализ: ни один путь в presenter_node не импортирует ForecastAgent."""

    def _get_presenter_node_source(self) -> str:
        source = GRAPH_PY.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "presenter_node":
                lines = source.splitlines()
                start = node.lineno - 1
                end = node.end_lineno
                return "\n".join(lines[start:end])
        return ""

    def test_presenter_node_has_no_forecast_agent_import(self):
        """presenter_node не должен содержать 'from app.agents.forecast_agent import ForecastAgent'."""
        presenter_source = self._get_presenter_node_source()
        assert presenter_source, "presenter_node не найден в graph.py"
        assert "from app.agents.forecast_agent import ForecastAgent" not in presenter_source, (
            "ОШИБКА: presenter_node всё ещё импортирует старый ForecastAgent!"
        )

    def test_presenter_node_uses_forecast_analyst_agent_for_forecast_branch(self):
        """Если ветка 'прогноз' в presenter_node осталась — она должна использовать ForecastAnalystAgent."""
        presenter_source = self._get_presenter_node_source()
        if "прогноз" in presenter_source or "forecast" in presenter_source.lower():
            assert "ForecastAnalystAgent" in presenter_source, (
                "ОШИБКА: ветка прогноза в presenter_node не использует ForecastAnalystAgent!"
            )


# ── 4. route_after_reviewer → "forecast" для прогнозных запросов ───────────────


class TestRouteAfterReviewer:
    """route_after_reviewer должен отправлять прогнозные вопросы в forecast_node."""

    def _get_router(self):

        import importlib.util

        spec = importlib.util.spec_from_file_location("graph_module", str(GRAPH_PY))
        # Не можем импортировать graph.py без полной инициализации — вместо этого
        # проверяем логику через AST
        return None

    def test_forecast_keywords_route_to_forecast_node(self):
        """
        Проверяем что route_after_reviewer возвращает 'forecast'
        при наличии ключевых слов прогноза.
        """
        graph_source = GRAPH_PY.read_text(encoding="utf-8")
        tree = ast.parse(graph_source)

        router_source = ""
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "route_after_reviewer":
                lines = graph_source.splitlines()
                router_source = "\n".join(lines[node.lineno - 1 : node.end_lineno])
                break

        assert router_source, "route_after_reviewer не найден в graph.py"

        # Проверяем что ключевые слова прогноза присутствуют в условии
        assert "прогноз" in router_source, "Ключевое слово 'прогноз' должно быть в router"
        assert '"forecast"' in router_source or "'forecast'" in router_source, (
            "router должен возвращать 'forecast'"
        )

    def test_graph_has_forecast_node_registered(self):
        """build_graph() регистрирует forecast_node."""
        graph_source = GRAPH_PY.read_text(encoding="utf-8")
        assert "forecast_node" in graph_source
        assert (
            '"forecast": forecast_node' in graph_source
            or "'forecast': forecast_node" in graph_source
        ), "forecast_node должен быть зарегистрирован в _nodes словаре"


# ── 5. ForecastAnalystAgent: данные иммутабельны ──────────────────────────────


class TestForecastAnalystAgentImmutability:
    """ForecastAnalystAgent.run() не должен мутировать переданный список data."""

    def test_input_data_not_mutated_by_analyst(self):
        """ForecastAnalystAgent работает с копией данных, не меняя оригинал."""
        from app.agents.forecast_analyst_agent import ForecastAnalystAgent

        data = list(_SAMPLE_DATA)
        original_len = len(data)

        agent = ForecastAnalystAgent()

        # Мокируем LLM-вызов чтобы не нужен реальный API
        with patch("core.llm.call_structured") as mock_llm:
            mock_llm.return_value = MagicMock(narrative="Тренд положительный.")
            result = agent.run("покажи прогноз", data=data)

        # Длина исходного списка не должна измениться
        assert len(data) == original_len, (
            f"ForecastAnalystAgent мутировал data: было {original_len}, стало {len(data)}"
        )

        # Результат должен содержать history + forecast (combined)
        if result.success:
            assert len(result.data) >= original_len, (
                "result.data должен включать минимум исторические точки"
            )
            # Убеждаемся что result.data — это НОВЫЙ объект, не оригинальный data
            assert result.data is not data, "result.data должен быть новым объектом"


# ── 6. Финальная проверка: нет импорта ForecastAgent (polyfit) в продакшн-путях ─


class TestNoPolyFitInProductionPaths:
    """numpy.polyfit не должен использоваться в forecast_agent.py."""

    def _code_lines_only(self, source: str) -> str:
        """Возвращает только строки кода: убирает docstring и # комментарии."""
        lines = []
        in_docstring = False
        for line in source.splitlines():
            stripped = line.strip()
            # Простой детектор тройных кавычек (достаточно для этого файла)
            if stripped.startswith('"""') or stripped.startswith("'''"):
                in_docstring = not in_docstring
                continue
            if in_docstring:
                continue
            # Убираем строки-только-комментарии
            if stripped.startswith("#"):
                continue
            lines.append(line)
        return "\n".join(lines)

    def test_forecast_agent_has_no_polyfit_in_code(self):
        """forecast_agent.py не содержит вызовов np.polyfit в коде (не в комментариях)."""
        source = FORECAST_AGENT_PY.read_text(encoding="utf-8")
        code_only = self._code_lines_only(source)
        assert "polyfit" not in code_only, (
            "ОШИБКА: forecast_agent.py всё ещё вызывает np.polyfit в продакшн-коде!"
        )

    def test_forecast_agent_has_no_data_append_mutation(self):
        """forecast_agent.py не содержит data.append() в коде (мутация устранена)."""
        source = FORECAST_AGENT_PY.read_text(encoding="utf-8")
        code_only = self._code_lines_only(source)
        # Паттерн мутации: прямой вызов data.append( на входном параметре
        assert "data.append(" not in code_only, (
            "ОШИБКА: forecast_agent.py всё ещё мутирует data через data.append()!"
        )
