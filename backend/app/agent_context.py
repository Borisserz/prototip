"""Контекст выполнения агентов (contextvars для вложенных вызовов)."""

from __future__ import annotations

import queue
from contextlib import contextmanager
from contextvars import ContextVar

_subplan_depth: ContextVar[int] = ContextVar("subplan_depth", default=0)
_user_role: ContextVar[str] = ContextVar("user_role", default="manager")
_current_tenant: ContextVar[object | None] = ContextVar("current_tenant", default=None)


def in_subplan() -> bool:
    return _subplan_depth.get() > 0


def get_user_role() -> str:
    return _user_role.get()


def get_current_tenant():
    """Активный клиент (Tenant) текущего запроса или None (single-tenant режим)."""
    return _current_tenant.get()


@contextmanager
def tenant_context(tenant):
    """Маркер: активный клиент (Phase 6, multi-tenant изоляция)."""
    token = _current_tenant.set(tenant)
    try:
        yield
    finally:
        _current_tenant.reset(token)


@contextmanager
def presentation_subplan():
    """Маркер: внутри PresentationAgent (запрет рекурсивных high-level агентов в планах)."""
    token = _subplan_depth.set(_subplan_depth.get() + 1)
    try:
        yield
    finally:
        _subplan_depth.reset(token)


@contextmanager
def user_context(role: str):
    """Маркер: роль текущего пользователя для RLS."""
    token = _user_role.set(role)
    try:
        yield
    finally:
        _user_role.reset(token)

_debate_queue: ContextVar[queue.Queue | None] = ContextVar("debate_queue", default=None)

@contextmanager
def debate_context(q: queue.Queue):
    """Контекст для стриминга дебатов агентов."""
    token = _debate_queue.set(q)
    try:
        yield
    finally:
        _debate_queue.reset(token)

def emit_debate(role: str, message: str):
    """Отправляет сообщение в UI."""
    q = _debate_queue.get()
    if q is not None:
        q.put({"type": "debate", "role": role, "content": message})

def emit_node_event(node_name: str | None):
    """Отправляет событие переключения текущего узла графа."""
    q = _debate_queue.get()
    if q is not None:
        q.put({"type": "node_event", "node": node_name})