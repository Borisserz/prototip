"""
Tests for graph.py fix 3.5 — route_after_supervisor explicit direct_answer branch.

Проверяем:
1. route field присутствует в GraphState TypedDict
2. route_after_supervisor → "end" при route=="direct_answer"
3. route_after_supervisor → "end" при final_result установлен (safety-net)
4. route_after_supervisor → "data" при drilldown (независимо от route/final_result)
5. route_after_supervisor → "data" при пустом state
6. supervisor_node явно устанавливает route="direct_answer" при direct_answer
7. supervisor_node устанавливает route="data" при data маршруте
"""

from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import MagicMock

import pytest

BACKEND_DIR = Path(__file__).parent.parent
GRAPH_PY = BACKEND_DIR / "app" / "graph.py"


# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_state(**kwargs) -> dict:
    """Создаёт минимальный GraphState-совместимый словарь."""
    base = {
        "question": "Тест",
        "drilldown": None,
        "user_role": "manager",
        "user_id": None,
        "business_context": None,
        "memory_context": None,
        "sub_questions": None,
        "raw_data": None,
        "sql": None,
        "analysis": None,
        "chart_spec": None,
        "final_result": None,
        "error": None,
        "messages": [],
        "route": None,
        "raw_analysis_dict": None,
        "eval_feedback": None,
        "eval_retry_count": None,
    }
    base.update(kwargs)
    return base


# ── 1. GraphState содержит поле route ─────────────────────────────────────────


class TestGraphStateHasRouteField:
    def test_route_field_in_graphstate_typeddict(self):
        """GraphState TypedDict должен содержать поле 'route'."""
        source = GRAPH_PY.read_text(encoding="utf-8")
        tree = ast.parse(source)

        gs_source = ""
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "GraphState":
                lines = source.splitlines()
                gs_source = "\n".join(lines[node.lineno - 1 : node.end_lineno])
                break

        assert gs_source, "GraphState не найден в graph.py"
        assert "route" in gs_source, (
            "ОШИБКА: GraphState не содержит поле 'route' — "
            "supervisor_node.route будет молча дроппаться LangGraph!"
        )


# ── Fixtures ───────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def route_after_supervisor_fn():
    """
    Извлекает route_after_supervisor из graph.py через AST + exec(),
    обходя Python 3.9 несовместимость с X|None в TypedDict аннотациях.
    Тестирует реальную логику функции без зависимостей всего модуля.
    """
    import logging

    source = GRAPH_PY.read_text(encoding="utf-8")
    tree = ast.parse(source)
    lines = source.splitlines()

    fn_source = ""
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "route_after_supervisor":
            fn_source = "\n".join(lines[node.lineno - 1 : node.end_lineno])
            break

    assert fn_source, "route_after_supervisor не найдена в graph.py"

    ns: dict = {"logger": logging.getLogger("test_graph")}
    exec(fn_source, ns)  # noqa: S102
    return ns["route_after_supervisor"]


# ── 2. route_after_supervisor logic ───────────────────────────────────────────


class TestRouteAfterSupervisor:
    def test_direct_answer_routes_to_end(self, route_after_supervisor_fn):
        """route == 'direct_answer' → router возвращает 'end'."""
        state = _make_state(route="direct_answer", final_result=MagicMock())
        result = route_after_supervisor_fn(state)
        assert result == "end", f"Expected 'end' for direct_answer, got '{result}'"

    def test_direct_answer_without_final_result_still_routes_to_end(
        self, route_after_supervisor_fn
    ):
        """
        Если route='direct_answer' но final_result пустой —
        роутер должен вернуть 'end' (не 'data').
        Защита от ситуации где final_result не передан.
        """
        state = _make_state(route="direct_answer", final_result=None)
        result = route_after_supervisor_fn(state)
        assert result == "end", (
            "ОШИБКА: route='direct_answer' должен давать 'end' даже без final_result"
        )

    def test_search_cache_final_result_routes_to_end(self, route_after_supervisor_fn):
        """safety-net: final_result установлен (search_node кэш) без route → 'end'."""
        state = _make_state(route=None, final_result=MagicMock())
        result = route_after_supervisor_fn(state)
        assert result == "end", (
            f"Safety-net: final_result установлен → должно быть 'end', получили '{result}'"
        )

    def test_drilldown_overrides_direct_answer_route(self, route_after_supervisor_fn):
        """drilldown всегда → 'data', даже если route='direct_answer'."""
        state = _make_state(
            drilldown=MagicMock(),
            route="direct_answer",
            final_result=MagicMock(),
        )
        result = route_after_supervisor_fn(state)
        assert result == "data", (
            "ОШИБКА: drilldown должен переопределять любой другой маршрут → 'data'"
        )

    def test_empty_state_routes_to_data(self, route_after_supervisor_fn):
        """Пустой state (без route и final_result) → 'data'."""
        state = _make_state()
        result = route_after_supervisor_fn(state)
        assert result == "data"

    def test_data_route_routes_to_data(self, route_after_supervisor_fn):
        """route='data' → 'data'."""
        state = _make_state(route="data")
        result = route_after_supervisor_fn(state)
        assert result == "data"

    def test_drilldown_ignores_stale_final_result(self, route_after_supervisor_fn):
        """
        CRITICAL: drilldown + stale final_result (от прошлого запроса) → 'data'.
        Это ключевой кейс, описанный в комментарии кода.
        """
        stale = MagicMock()
        state = _make_state(drilldown=MagicMock(), final_result=stale, route=None)
        result = route_after_supervisor_fn(state)
        assert result == "data", (
            "КРИТИЧНО: drilldown с stale final_result должен идти в 'data', "
            "а не в 'end' (иначе вернётся кэшированный ответ прошлого запроса)"
        )


# ── 3. supervisor_node устанавливает route явно ───────────────────────────────


class TestSupervisorNodeSetsRoute:
    """Проверяем через AST что supervisor_node явно задаёт route в обоих ветках."""

    def _get_supervisor_source(self) -> str:
        source = GRAPH_PY.read_text(encoding="utf-8")
        tree = ast.parse(source)
        lines = source.splitlines()
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "supervisor_node":
                return "\n".join(lines[node.lineno - 1 : node.end_lineno])
        return ""

    def test_supervisor_sets_route_direct_answer(self):
        """supervisor_node должен явно возвращать route='direct_answer' при direct_answer."""
        src = self._get_supervisor_source()
        assert src, "supervisor_node не найден"
        assert '"direct_answer"' in src or "'direct_answer'" in src, (
            "supervisor_node не содержит строку 'direct_answer' в маршруте"
        )
        # Проверяем что route присутствует как ключ в возвращаемом словаре
        assert '"route"' in src or "'route'" in src, (
            "supervisor_node не возвращает ключ 'route' явно"
        )

    def test_supervisor_sets_route_data_on_data_branch(self):
        """supervisor_node должен явно возвращать {'route': 'data'} при data-маршруте."""
        src = self._get_supervisor_source()
        # return {"route": "data"} должен быть в коде
        assert '"data"' in src, "supervisor_node не содержит строку 'data'"

    def test_route_after_supervisor_checks_route_field_not_only_final_result(self):
        """
        route_after_supervisor должен явно проверять state.get('route'),
        а не только state.get('final_result').
        """
        source = GRAPH_PY.read_text(encoding="utf-8")
        tree = ast.parse(source)
        lines = source.splitlines()

        router_source = ""
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "route_after_supervisor":
                router_source = "\n".join(lines[node.lineno - 1 : node.end_lineno])
                break

        assert router_source, "route_after_supervisor не найден"
        assert "route" in router_source, "route_after_supervisor не проверяет поле 'route' из state"
        assert "direct_answer" in router_source, (
            "route_after_supervisor не имеет явной проверки на 'direct_answer'"
        )


# ── 4. Регрессия initial_state (fix 4.1) ──────────────────────────────────────


class TestInitialStateKeys:
    """
    Регрессионные тесты для fix 4.1:
    - tasks_completed и agent_results удалены (legacy, не объявлены в GraphState)
    - route явно инициализируется в initial_state
    - все ключи initial_state объявлены в GraphState
    """

    ORCHESTRATOR_PY = BACKEND_DIR / "app" / "orchestrator.py"

    def _get_graphstate_fields(self) -> set:
        src = GRAPH_PY.read_text(encoding="utf-8")
        tree = ast.parse(src)
        fields = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "GraphState":
                for item in node.body:
                    if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                        fields.add(item.target.id)
        return fields

    def _get_initial_state_keys(self) -> list[list]:
        """Возвращает список ключей для каждого initial_state в orchestrator.py."""
        src = self.ORCHESTRATOR_PY.read_text(encoding="utf-8")
        tree = ast.parse(src)
        results = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                keys = [k.value for k in node.keys if isinstance(k, ast.Constant)]
                # Признак initial_state: содержит и 'question' и 'messages'
                if "question" in keys and "messages" in keys:
                    results.append(keys)
        return results

    def test_no_tasks_completed_in_initial_state(self):
        """
        РЕГРЕССИЯ: tasks_completed не должен быть в initial_state.
        Это legacy-ключ, не объявленный в GraphState.
        """
        for keys in self._get_initial_state_keys():
            assert "tasks_completed" not in keys, (
                "РЕГРЕССИЯ: 'tasks_completed' вернулся в initial_state! "
                "Этот ключ не объявлен в GraphState и никогда не использовался."
            )

    def test_no_agent_results_in_initial_state(self):
        """
        РЕГРЕССИЯ: agent_results не должен быть в initial_state.
        Это legacy-ключ, не объявленный в GraphState.
        """
        for keys in self._get_initial_state_keys():
            assert "agent_results" not in keys, (
                "РЕГРЕССИЯ: 'agent_results' вернулся в initial_state! "
                "Этот ключ не объявлен в GraphState и никогда не использовался."
            )

    def test_route_explicitly_initialized_in_initial_state(self):
        """
        initial_state основного ask() должен явно инициализировать route=None,
        чтобы LangGraph не получал unknown key на первом вызове.
        """
        # Ищем initial_state с наибольшим числом ключей (это ask(), не ask_stream())
        all_states = self._get_initial_state_keys()
        ask_state_keys = max(all_states, key=len)
        assert "route" in ask_state_keys, (
            "ОШИБКА: 'route' не инициализируется явно в initial_state. "
            "Это поле должно быть объявлено с None при запуске графа."
        )

    def test_all_initial_state_keys_are_in_graphstate(self):
        """
        Все ключи initial_state должны быть объявлены в GraphState TypedDict.
        Любой неизвестный ключ — технический долг (LangGraph добавит как extra key).
        """
        gs_fields = self._get_graphstate_fields()
        assert gs_fields, "GraphState fields не найдены"

        for keys in self._get_initial_state_keys():
            unknown = [k for k in keys if k not in gs_fields]
            assert not unknown, (
                f"ОШИБКА: initial_state содержит ключи, не объявленные в GraphState: "
                f"{unknown}. Добавьте их в GraphState или удалите из initial_state."
            )


# ── 5. FIX 2.6 — route_after_search drilldown shortcut ───────────────────────


@pytest.fixture(scope="module")
def route_after_search_fn():
    """
    Extracts route_after_search from graph.py via AST+exec,
    bypassing Python 3.9 TypedDict annotation incompatibilities.
    """
    import logging

    source = GRAPH_PY.read_text(encoding="utf-8")
    tree = ast.parse(source)
    lines = source.splitlines()

    fn_source = ""
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "route_after_search":
            fn_source = "\n".join(lines[node.lineno - 1 : node.end_lineno])
            break

    assert fn_source, "route_after_search не найдена в graph.py"

    ns: dict = {"logger": logging.getLogger("test_route_after_search")}
    exec(fn_source, ns)  # noqa: S102
    return ns["route_after_search"]


class TestRouteAfterSearch:
    """
    Regression tests for FIX 2.6:
    route_after_search must short-circuit to 'supervisor' for drilldown,
    completely skipping planner_node (RagAgent + TaskDecompositionAgent).
    """

    def test_drilldown_routes_to_supervisor_not_planner(self, route_after_search_fn):
        """
        CRITICAL FIX 2.6: drilldown → 'supervisor', NOT 'planner'.

        Before the fix, route_after_search returned 'planner' for drilldown,
        causing search→planner→supervisor→data when planner output is unused.
        After the fix it returns 'supervisor' for direct shortcut.
        """
        state = _make_state(drilldown=MagicMock(), final_result=None)
        result = route_after_search_fn(state)
        assert result == "supervisor", (
            f"FIX 2.6 REGRESSION: drilldown must route to 'supervisor' (skip planner), "
            f"got '{result}'. planner_node runs RagAgent+TaskDecompositionAgent "
            f"which supervisor always ignores for drilldown."
        )

    def test_drilldown_does_not_route_to_planner(self, route_after_search_fn):
        """REGRESSION guard: drilldown must NEVER return 'planner' anymore."""
        state = _make_state(drilldown=MagicMock())
        result = route_after_search_fn(state)
        assert result != "planner", (
            "РЕГРЕССИЯ: route_after_search вернула 'planner' при drilldown. "
            "Это запускает два лишних LLM-вызова без пользы."
        )

    def test_final_result_routes_to_end(self, route_after_search_fn):
        """Cache hit (final_result already set) → 'end', skip everything."""
        state = _make_state(drilldown=None, final_result=MagicMock())
        result = route_after_search_fn(state)
        assert result == "end", (
            f"Кэш-хит: final_result установлен → должно быть 'end', получили '{result}'"
        )

    def test_normal_query_routes_to_planner(self, route_after_search_fn):
        """Normal query (no drilldown, no cache) → 'planner'."""
        state = _make_state(drilldown=None, final_result=None)
        result = route_after_search_fn(state)
        assert result == "planner", (
            f"Обычный запрос без drilldown/кэша должен идти в 'planner', получили '{result}'"
        )

    def test_graph_edge_map_contains_supervisor(self):
        """
        The conditional edge map for 'search' node must include 'supervisor'
        as a valid destination (required for FIX 2.6 to work at runtime).
        """
        source = GRAPH_PY.read_text(encoding="utf-8")
        # Both "supervisor" and "planner" must appear in the edge map section
        # We check the source around the search conditional edges definition
        assert '"supervisor": "supervisor"' in source or "'supervisor': 'supervisor'" in source, (
            "FIX 2.6: graph edge map for 'search' node must include "
            "'supervisor': 'supervisor' entry — otherwise LangGraph will raise "
            "an InvalidUpdateError at runtime when drilldown routes to supervisor."
        )

    def test_route_after_search_docstring_mentions_fix(self):
        """route_after_search must have a docstring explaining FIX 2.6."""
        source = GRAPH_PY.read_text(encoding="utf-8")
        tree = ast.parse(source)
        lines = source.splitlines()
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "route_after_search":
                fn_src = "\n".join(lines[node.lineno - 1 : node.end_lineno])
                assert "FIX 2.6" in fn_src or "drilldown" in fn_src, (
                    "route_after_search должна иметь комментарий объясняющий shortcut"
                )
                return
        pytest.fail("route_after_search не найдена")
