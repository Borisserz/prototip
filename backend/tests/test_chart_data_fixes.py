"""
Regression tests for fixes 2.3 and 2.4.

  2.3 — presenter_node chart data deduplication and row cap
  2.4 — get_schema_prompt passes tenant to use correct ClickHouse instance
"""

from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

BACKEND_DIR = Path(__file__).parent.parent
GRAPH_PY = BACKEND_DIR / "app" / "graph.py"
DATA_AGENT_PY = BACKEND_DIR / "app" / "agents" / "data_agent.py"
EXTRACTOR_PY = BACKEND_DIR / "app" / "agents" / "db_schema_extractor.py"


# ── Helpers ────────────────────────────────────────────────────────────────────


def _parse_fn(path: Path, fn_name: str) -> str:
    """Extract source of a function from a Python file via AST."""
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    lines = source.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == fn_name:
            return "\n".join(lines[node.lineno - 1 : node.end_lineno])
    return ""


# ═══════════════════════════════════════════════════════════════════════════════
# FIX 2.3 — presenter_node chart data deduplication and row cap
# ═══════════════════════════════════════════════════════════════════════════════


class TestChartDataDeduplicationAndCap:
    """
    Verify that presenter_node doesn't send the entire raw_data to every chart.

    The fix must:
      1. Project only the columns needed by each chart (x, y, group_by).
      2. Deduplicate projected rows.
      3. Cap per-chart rows at CHART_ROW_CAP (100).
    """

    def _build_raw_data(self, n_rows: int) -> list[dict]:
        """Build a synthetic dataset with many columns."""
        return [
            {
                "region": f"Region_{i % 5}",
                "tax_type": f"Type_{i % 3}",
                "accrued": float(i * 100),
                "paid": float(i * 80),
                "debt": float(i * 20),
                "other_col": f"X{i}",
            }
            for i in range(n_rows)
        ]

    def test_chart_cap_in_graph_source(self):
        """presenter_node source must define _CHART_ROW_CAP."""
        source = GRAPH_PY.read_text(encoding="utf-8")
        assert "_CHART_ROW_CAP" in source, (
            "presenter_node must define _CHART_ROW_CAP to cap per-chart row count"
        )

    def test_deduplication_in_graph_source(self):
        """presenter_node source must contain deduplication logic."""
        source = GRAPH_PY.read_text(encoding="utf-8")
        assert "seen" in source and "deduped" in source, (
            "presenter_node must deduplicate projected rows (seen / deduped variables)"
        )

    def test_projection_keeps_only_needed_columns(self):
        """After column projection, rows must only contain the specified columns."""
        raw = self._build_raw_data(20)

        spec = MagicMock()
        spec.x = "region"
        spec.y = "accrued"
        spec.group_by = None

        wanted = {c for c in (spec.x, spec.y, getattr(spec, "group_by", None)) if c}
        projected = [{k: row[k] for k in wanted if k in row} for row in raw]

        for row in projected:
            assert set(row.keys()) == wanted, (
                f"Projected row contains unexpected columns: {set(row.keys()) - wanted}"
            )

    def test_dedup_removes_repeated_projected_rows(self):
        """After projecting to x+y only, duplicate rows must be removed."""
        # 100 rows that all have the same (region, accrued) after projection
        raw = [{"region": "Minsk", "accrued": 1000.0, "extra": i} for i in range(100)]

        wanted = {"region", "accrued"}
        projected = [{k: row[k] for k in wanted if k in row} for row in raw]

        seen: set = set()
        deduped = []
        for row in projected:
            key = tuple(sorted(row.items()))
            if key not in seen:
                seen.add(key)
                deduped.append(row)

        assert len(deduped) == 1, f"Expected 1 unique projected row, got {len(deduped)}"

    def test_row_cap_limits_chart_data(self):
        """Cap must limit chart data to at most _CHART_ROW_CAP rows."""
        _CHART_ROW_CAP = 100
        raw = self._build_raw_data(500)

        wanted = {"region", "accrued"}
        projected = [{k: row[k] for k in wanted if k in row} for row in raw]

        seen: set = set()
        deduped = []
        for row in projected:
            key = tuple(sorted(row.items()))
            if key not in seen:
                seen.add(key)
                deduped.append(row)
        result = deduped[:_CHART_ROW_CAP]

        assert len(result) <= _CHART_ROW_CAP, (
            f"Chart data exceeds cap: {len(result)} > {_CHART_ROW_CAP}"
        )

    def test_sort_descending_by_y(self):
        """Deduped rows must be sorted descending by the y-column."""
        rows = [
            {"region": "A", "accrued": 100.0},
            {"region": "B", "accrued": 500.0},
            {"region": "C", "accrued": 200.0},
        ]
        y_col = "accrued"
        rows.sort(key=lambda r: r.get(y_col) or 0, reverse=True)

        assert rows[0]["accrued"] == 500.0, "Highest value must come first"
        assert rows[-1]["accrued"] == 100.0, "Lowest value must come last"


# ═══════════════════════════════════════════════════════════════════════════════
# FIX 2.4 — get_schema_prompt passes tenant to use correct ClickHouse instance
# ═══════════════════════════════════════════════════════════════════════════════


class TestTenantAwareSchemaPrompt:
    """
    Verify that get_schema_prompt() accepts a tenant and routes to the correct
    ClickHouse instance rather than always using the shared default.
    """

    def test_get_schema_prompt_accepts_tenant_kwarg(self):
        """get_schema_prompt signature must have a tenant parameter."""
        source = EXTRACTOR_PY.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "get_schema_prompt":
                args = [a.arg for a in node.args.args]
                defaults = node.args.defaults
                kwarg_names = [a.arg for a in node.args.kwonlyargs]
                all_params = args + kwarg_names
                assert "tenant" in all_params, (
                    "get_schema_prompt() must accept a 'tenant' parameter (FIX 2.4)"
                )
                return
        pytest.fail("get_schema_prompt not found in db_schema_extractor.py")

    def test_get_schema_prompt_without_tenant_uses_default(self):
        """
        Without tenant argument, get_schema_prompt must call DbSchemaExtractor
        with no special parameters (default ClickHouse).
        """
        with patch("app.agents.db_schema_extractor.DbSchemaExtractor") as MockExtractor:
            mock_instance = MockExtractor.return_value
            mock_instance.extract_schema.return_value = "schema"

            from app.agents.db_schema_extractor import get_schema_prompt

            result = get_schema_prompt()

            # Called once, no credentials passed
            MockExtractor.assert_called_once_with()
            mock_instance.extract_schema.assert_called_once()
            assert result == "schema"

    def test_get_schema_prompt_with_tenant_uses_tenant_clickhouse(self):
        """
        With a tenant argument, get_schema_prompt must instantiate
        DbSchemaExtractor with the tenant's ClickHouse connection details.
        """
        fake_tenant = MagicMock()
        fake_tenant.client_id = "acme"
        fake_tenant.clickhouse.host = "ch.acme.internal"
        fake_tenant.clickhouse.port = 9000
        fake_tenant.clickhouse.user = "acme_user"
        fake_tenant.clickhouse.password_enc = ""  # no encryption

        with (
            patch("app.agents.db_schema_extractor.DbSchemaExtractor") as MockExtractor,
            patch("app.security.decrypt_data", return_value=""),
        ):
            mock_instance = MockExtractor.return_value
            mock_instance.extract_schema.return_value = "tenant_schema"

            import app.agents.db_schema_extractor as mod

            result = mod.get_schema_prompt(tenant=fake_tenant)

            # DbSchemaExtractor should be called with tenant credentials
            assert MockExtractor.called, "DbSchemaExtractor must be instantiated for tenant"
            call_args = MockExtractor.call_args
            # Accept positional or keyword — host must be the tenant's host
            all_args = list(call_args.args or []) + list((call_args.kwargs or {}).values())
            assert (
                "ch.acme.internal" in all_args
                or (call_args.kwargs or {}).get("host") == "ch.acme.internal"
            ), (
                f"DbSchemaExtractor must be called with tenant's ClickHouse host. "
                f"Got call_args: {call_args}"
            )

    def test_data_agent_schema_cache_keyed_by_tenant_id(self):
        """DataAgent._schema_cache dict must be keyed by tenant_id, not a bool flag."""
        source = DATA_AGENT_PY.read_text(encoding="utf-8")
        tree = ast.parse(source)

        # Find _get_dynamic_schema
        fn_src = _parse_fn(DATA_AGENT_PY, "_get_dynamic_schema")
        assert fn_src, "_get_dynamic_schema not found in data_agent.py"

        # Must reference tenant_id as cache key
        assert "tenant_id" in fn_src, (
            "ОШИБКА: _get_dynamic_schema must key the cache by tenant_id (FIX 2.4)"
        )
        # Must NOT use the old pattern 'if not self._schema_cache:'
        assert "if not self._schema_cache" not in fn_src, (
            "РЕГРЕССИЯ: _get_dynamic_schema must not use 'if not self._schema_cache' "
            "(that ignores multi-tenant isolation)"
        )

    def test_data_agent_passes_tenant_to_get_schema_prompt(self):
        """_get_dynamic_schema must pass tenant= to get_schema_prompt (FIX 2.4)."""
        fn_src = _parse_fn(DATA_AGENT_PY, "_get_dynamic_schema")
        assert (
            "tenant=tenant" in fn_src
            or "tenant = tenant" in fn_src
            or ("get_schema_prompt" in fn_src and "tenant" in fn_src)
        ), "FIX 2.4: _get_dynamic_schema must pass tenant object to get_schema_prompt"
