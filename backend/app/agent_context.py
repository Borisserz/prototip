"""Контекст выполнения агентов (contextvars для вложенных вызовов)."""

from __future__ import annotations

import queue
from contextlib import contextmanager
from contextvars import ContextVar

_subplan_depth: ContextVar[int] = ContextVar("subplan_depth", default=0)
_user_role: ContextVar[str] = ContextVar("user_role", default="manager")
_current_tenant: ContextVar[object | None] = ContextVar("current_tenant", default=None)
_username: ContextVar[str | None] = ContextVar("username", default=None)
_user_permissions: ContextVar[dict | None] = ContextVar("user_permissions", default=None)
_session_id: ContextVar[str] = ContextVar("session_id", default="default_session")


def in_subplan() -> bool:
    return _subplan_depth.get() > 0


def get_user_role() -> str:
    return _user_role.get()


def get_username() -> str | None:
    """Логин текущего пользователя (per-tenant user) или None."""
    return _username.get()


def get_user_permissions() -> dict | None:
    """Гранулярные права текущего пользователя (allowed_tables/columns, rls_filters,
    can_dashboard/can_presentation) или None, если не заданы (роле-базовый режим)."""
    return _user_permissions.get()


def get_session_id() -> str:
    """Текущий session_id (устанавливается оркестратором через user_context).

    Дефолт 'default_session' гарантирует backward-совместимость при вызове
    вне контекста (тесты, CLI, прямые вызовы DataAgent).
    """
    return _session_id.get()


def get_current_tenant():
    """Активный клиент (Tenant) текущего запроса или None (single-tenant режим)."""
    return _current_tenant.get()


@contextmanager
def tenant_context(tenant):
    """Маркер: активный клиент."""
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
def user_context(
    role: str,
    *,
    username: str | None = None,
    permissions: dict | None = None,
    session_id: str | None = None,
):
    """Маркер: контекст текущего пользователя (роль + логин + гранулярные права + сессия).

    ``permissions`` — словарь из core.tenant_users.get_user_permissions(): allowed_tables,
    allowed_columns, rls_filters, can_dashboard, can_presentation. Если None — действует
    роле-базовый режим (как раньше).

    ``session_id`` — идентификатор сессии диалога. DataAgent читает его через
    get_session_id() чтобы обращаться к правильной истории ConversationMemory.
    Если None — текущее значение ContextVar не переопределяется (остаётся дефолт).
    """
    t_role = _user_role.set(role)
    t_name = _username.set(username)
    t_perms = _user_permissions.set(permissions)
    t_sess = _session_id.set(session_id) if session_id is not None else None
    try:
        yield
    finally:
        _user_role.reset(t_role)
        _username.reset(t_name)
        _user_permissions.reset(t_perms)
        if t_sess is not None:
            _session_id.reset(t_sess)


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
