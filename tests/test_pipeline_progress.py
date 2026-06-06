"""Unit tests for pipeline progress store."""

from __future__ import annotations

from app.pipeline_progress import (
    pipeline_store,
    suppress_pipeline_emit,
    emit_pipeline_stage,
    emit_agent_started,
)


def test_pipeline_reset_and_finish():
    pipeline_store.reset("t1", "test question")
    emit_pipeline_stage("intent", "done", "ok", agent="planner_agent")
    pipeline_store.finish(success=True)
    snap = pipeline_store.snapshot()
    assert snap["finished"] is True
    assert snap["stages"]["intent"]["status"] == "done"


def test_pipeline_error_cleared_on_success():
    pipeline_store.reset("t2", "q")
    emit_pipeline_stage("sql", "error", "fail", agent="data_agent", error="boom")
    emit_pipeline_stage("sql", "running", "retry", agent="data_agent")
    emit_pipeline_stage("sql", "done", "ok", agent="data_agent")
    snap = pipeline_store.snapshot()
    assert snap["stages"]["sql"]["status"] == "done"
    assert snap["stages"]["sql"]["error"] is None


def test_suppress_pipeline_emit_blocks_nested():
    pipeline_store.reset("t3", "nested")
    with suppress_pipeline_emit():
        emit_agent_started("data_agent", "should not appear")
    snap = pipeline_store.snapshot()
    assert snap["stages"]["sql"]["status"] == "pending"