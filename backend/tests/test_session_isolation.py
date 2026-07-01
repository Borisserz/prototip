"""
Tests for ConversationMemory session_id fix (issue 3.2).

Проверяем:
1. get_session_id() возвращает "default_session" вне user_context (backward-совместимость)
2. user_context(session_id=...) правильно устанавливает ContextVar
3. user_context без session_id НЕ меняет текущий ContextVar
4. ContextVar изолирован между вложенными контекстами (reset после выхода)
5. DataAgent._build_prompt() использует get_session_id() (не хардкод)
6. Разные пользователи с разными session_id получают разную историю ConversationMemory
"""

from __future__ import annotations

import ast
import threading
from pathlib import Path

BACKEND_DIR = Path(__file__).parent.parent
DATA_AGENT_PY = BACKEND_DIR / "app" / "agents" / "data_agent.py"
AGENT_CONTEXT_PY = BACKEND_DIR / "app" / "agent_context.py"


# ── 1. get_session_id() без контекста → "default_session" ────────────────────


class TestGetSessionIdDefaults:
    def test_default_outside_context(self):
        """Вне user_context get_session_id() возвращает 'default_session'."""
        from app.agent_context import get_session_id

        assert get_session_id() == "default_session"

    def test_get_session_id_is_exported(self):
        """get_session_id должен быть публичным именем в agent_context."""
        import app.agent_context as ctx

        assert hasattr(ctx, "get_session_id"), "get_session_id не экспортирован из agent_context"
        assert callable(ctx.get_session_id)


# ── 2. user_context устанавливает session_id ──────────────────────────────────


class TestUserContextSetsSessionId:
    def test_session_id_set_inside_context(self):
        """Внутри user_context(session_id=...) get_session_id() возвращает нужное значение."""
        from app.agent_context import get_session_id, user_context

        with user_context("manager", session_id="user-abc-123"):
            sid = get_session_id()

        assert sid == "user-abc-123"

    def test_session_id_reset_after_context_exit(self):
        """После выхода из user_context значение сбрасывается к дефолту."""
        from app.agent_context import get_session_id, user_context

        with user_context("manager", session_id="temp-session"):
            pass  # выходим сразу

        # Должен вернуться дефолт
        assert get_session_id() == "default_session"

    def test_session_id_none_does_not_override(self):
        """user_context(session_id=None) НЕ переопределяет текущий ContextVar."""
        from app.agent_context import get_session_id, user_context

        # Устанавливаем внешний контекст с конкретным session_id
        with user_context("manager", session_id="outer-session"):
            # Вложенный контекст без session_id — не должен сбрасывать
            with user_context("analyst"):
                inner_sid = get_session_id()

        assert inner_sid == "outer-session", (
            f"Вложенный user_context(session_id=None) не должен сбрасывать "
            f"session_id к дефолту, но вернул: {inner_sid!r}"
        )

    def test_nested_contexts_restore_correctly(self):
        """Вложенные user_context с разными session_id корректно восстанавливают значения."""
        from app.agent_context import get_session_id, user_context

        results = {}
        with user_context("manager", session_id="outer"):
            results["outer_before"] = get_session_id()
            with user_context("analyst", session_id="inner"):
                results["inner"] = get_session_id()
            results["outer_after"] = get_session_id()

        assert results["outer_before"] == "outer"
        assert results["inner"] == "inner"
        assert results["outer_after"] == "outer"  # восстановлен после выхода из inner


# ── 3. Изоляция между потоками ────────────────────────────────────────────────


class TestThreadIsolation:
    """ContextVar изолированы между потоками — разные пользователи не мешают друг другу."""

    def test_concurrent_sessions_are_isolated(self):
        """
        Два потока с разными session_id видят только свои значения.
        Это критично для мультипользовательской работы.
        """
        from app.agent_context import get_session_id, user_context

        results = {}
        barrier = threading.Barrier(2)  # синхронизация — оба потока стартуют вместе

        def thread_fn(name: str, session: str):
            with user_context("manager", session_id=session):
                barrier.wait()  # оба потока внутри контекста одновременно
                results[name] = get_session_id()

        t1 = threading.Thread(target=thread_fn, args=("user1", "session-user-1"))
        t2 = threading.Thread(target=thread_fn, args=("user2", "session-user-2"))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert results["user1"] == "session-user-1", (
            f"Поток user1 видит чужую сессию: {results['user1']}"
        )
        assert results["user2"] == "session-user-2", (
            f"Поток user2 видит чужую сессию: {results['user2']}"
        )
        assert results["user1"] != results["user2"]


# ── 4. DataAgent._build_prompt() не хардкодит "default_session" ──────────────


class TestDataAgentNoHardcodedSession:
    def test_build_prompt_no_default_session_string_in_code(self):
        """
        _build_prompt() не должен содержать строку 'default_session' в коде
        (только через get_session_id() из ContextVar).
        """
        source = DATA_AGENT_PY.read_text(encoding="utf-8")
        tree = ast.parse(source)
        lines = source.splitlines()

        # Находим метод _build_prompt
        prompt_source = ""
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_build_prompt":
                prompt_source = "\n".join(lines[node.lineno - 1 : node.end_lineno])
                break

        assert prompt_source, "_build_prompt не найден в data_agent.py"
        assert (
            '"default_session"' not in prompt_source and "'default_session'" not in prompt_source
        ), "ОШИБКА: _build_prompt всё ещё содержит хардкод 'default_session'!"

    def test_build_prompt_uses_get_session_id(self):
        """_build_prompt() должен вызывать get_session_id()."""
        source = DATA_AGENT_PY.read_text(encoding="utf-8")
        tree = ast.parse(source)
        lines = source.splitlines()

        prompt_source = ""
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_build_prompt":
                prompt_source = "\n".join(lines[node.lineno - 1 : node.end_lineno])
                break

        assert "get_session_id" in prompt_source, (
            "ОШИБКА: _build_prompt не вызывает get_session_id()!"
        )


# ── 5. ConversationMemory: разные session_id → разные истории ─────────────────


class TestConversationMemoryMultiSession:
    """Базовая проверка что ConversationMemory корректно изолирует истории."""

    def test_different_sessions_get_different_history(self):
        """Два session_id — две отдельные истории, без перекрёстного загрязнения."""
        import threading

        from app.utils.memory import ConversationMemory

        mem = ConversationMemory.__new__(ConversationMemory)
        mem._history = {}  # чистая память без файла
        mem._lock = threading.RLock()

        mem.add_message("session-A", "user", "Вопрос пользователя A")
        mem.add_message("session-A", "bot", "Ответ для A")
        mem.add_message("session-B", "user", "Вопрос пользователя B")

        ctx_a = mem.get_context_string("session-A")
        ctx_b = mem.get_context_string("session-B")
        ctx_c = mem.get_context_string("session-C")  # несуществующая

        assert "пользователя A" in ctx_a, "История сессии A не читается"
        assert "пользователя A" not in ctx_b, "История A попала в контекст B!"
        assert "пользователя B" not in ctx_a, "История B попала в контекст A!"
        assert ctx_c == "", "Несуществующая сессия должна возвращать пустую строку"

    def test_get_context_string_with_real_session_id(self):
        """get_context_string(get_session_id()) внутри user_context читает правильную сессию."""
        import threading

        from app.agent_context import get_session_id, user_context
        from app.utils.memory import ConversationMemory

        mem = ConversationMemory.__new__(ConversationMemory)
        mem._history = {}
        mem._lock = threading.RLock()

        mem.add_message("real-session-xyz", "user", "Привет из реальной сессии")

        with user_context("manager", session_id="real-session-xyz"):
            sid = get_session_id()
            ctx = mem.get_context_string(sid)

        assert "реальной сессии" in ctx, (
            f"get_session_id() вернул '{sid}', но контекст пустой или неправильный"
        )
