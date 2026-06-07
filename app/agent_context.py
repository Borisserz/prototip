"""Контекст выполнения агентов (contextvars для вложенных вызовов)."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar

_subplan_depth: ContextVar[int] = ContextVar("subplan_depth", default=0)


def in_subplan() -> bool:
    return _subplan_depth.get() > 0


@contextmanager
def presentation_subplan():
    """Маркер: внутри PresentationAgent (запрет рекурсивных high-level агентов в планах)."""
    token = _subplan_depth.set(_subplan_depth.get() + 1)
    try:
        yield
    finally:
        _subplan_depth.reset(token)