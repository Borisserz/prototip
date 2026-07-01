"""
Tests for ClickHouseClient fix 3.7 — connection reuse after error.

Проверяем:
1. Успешное подключение при первом вызове get_client()
2. Ping-health-check: если ping упал → автоматическое пересоздание соединения
3. Инвалидация при ошибке execute()  → client=None → следующий вызов создаёт новый
4. Инвалидация при ошибке execute_df() → аналогично
5. Инвалидация при ошибке insert_df() → без retry
6. Инвалидация при ошибке command()   → без retry
7. Инвалидация при ошибке insert()    → без retry
8. execute()     делает retry (одну повторную попытку) при первой ошибке
9. execute_df()  делает retry при первой ошибке
10. insert/command НЕ делают retry (защита от дублей)
11. Thread isolation: разные потоки имеют разные соединения
12. После _invalidate() следующий get_client() создаёт новое соединение
"""

from __future__ import annotations

import threading
from unittest.mock import MagicMock, patch

import pytest

# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_client(mock_ch_client: MagicMock) -> ClickHouseClient:
    """Создаёт ClickHouseClient с замоканным clickhouse_connect.get_client."""
    from app.utils.clickhouse_client import ClickHouseClient

    return ClickHouseClient()


@pytest.fixture(autouse=True)
def mock_ch_connect():
    """Мокируем clickhouse_connect.get_client глобально для всех тестов."""
    with patch("app.utils.clickhouse_client.clickhouse_connect") as mock_cc:
        yield mock_cc


def _fresh_mock_connection():
    """Создаёт mock-соединение, у которого ping() возвращает True."""
    conn = MagicMock()
    conn.ping.return_value = True
    return conn


# ── 1. Базовое подключение ─────────────────────────────────────────────────────


class TestGetClient:
    def test_creates_connection_on_first_call(self, mock_ch_connect):
        """Первый вызов get_client() создаёт соединение."""
        from app.utils.clickhouse_client import ClickHouseClient

        conn = _fresh_mock_connection()
        mock_ch_connect.get_client.return_value = conn

        client = ClickHouseClient()
        result = client.get_client()

        mock_ch_connect.get_client.assert_called_once()
        assert result is conn

    def test_reuses_connection_on_second_call(self, mock_ch_connect):
        """Второй вызов get_client() возвращает кэшированное соединение."""
        from app.utils.clickhouse_client import ClickHouseClient

        conn = _fresh_mock_connection()
        mock_ch_connect.get_client.return_value = conn

        client = ClickHouseClient()
        r1 = client.get_client()
        r2 = client.get_client()

        # connect вызван ровно один раз
        assert mock_ch_connect.get_client.call_count == 1
        assert r1 is r2

    def test_reconnects_if_ping_fails(self, mock_ch_connect):
        """Если ping() упал — создаётся новое соединение."""
        from app.utils.clickhouse_client import ClickHouseClient

        stale_conn = MagicMock()
        stale_conn.ping.side_effect = OSError("Connection reset")

        fresh_conn = _fresh_mock_connection()
        mock_ch_connect.get_client.side_effect = [stale_conn, fresh_conn]

        client = ClickHouseClient()
        first = client.get_client()  # → stale_conn
        second = client.get_client()  # ping fails → new connection

        assert first is stale_conn
        assert second is fresh_conn
        assert mock_ch_connect.get_client.call_count == 2

    def test_invalidate_clears_client(self, mock_ch_connect):
        """_invalidate() устанавливает client=None; следующий get_client() создаёт новое."""
        from app.utils.clickhouse_client import ClickHouseClient

        conn1 = _fresh_mock_connection()
        conn2 = _fresh_mock_connection()
        mock_ch_connect.get_client.side_effect = [conn1, conn2]

        client = ClickHouseClient()
        c1 = client.get_client()
        client._invalidate()
        c2 = client.get_client()

        assert c1 is conn1
        assert c2 is conn2
        assert mock_ch_connect.get_client.call_count == 2


# ── 2. execute() — retry для SELECT ───────────────────────────────────────────


class TestExecute:
    def test_execute_success(self, mock_ch_connect):
        """execute() возвращает результат при успехе."""
        from app.utils.clickhouse_client import ClickHouseClient

        conn = _fresh_mock_connection()
        conn.query.return_value = "result"
        mock_ch_connect.get_client.return_value = conn

        client = ClickHouseClient()
        result = client.execute("SELECT 1")

        assert result == "result"
        conn.query.assert_called_once_with("SELECT 1", parameters=None)

    def test_execute_retries_on_error(self, mock_ch_connect):
        """execute() при первой ошибке инвалидирует соединение и делает retry."""
        from app.utils.clickhouse_client import ClickHouseClient

        broken_conn = _fresh_mock_connection()
        broken_conn.query.side_effect = [OSError("Broken pipe"), "result_after_retry"]

        fresh_conn = _fresh_mock_connection()
        fresh_conn.query.return_value = "result_after_retry"

        mock_ch_connect.get_client.side_effect = [broken_conn, fresh_conn]

        client = ClickHouseClient()
        result = client.execute("SELECT 1")

        # Должны были создать два соединения (оригинальное + после retry)
        assert mock_ch_connect.get_client.call_count == 2
        assert result == "result_after_retry"

    def test_execute_invalidates_on_both_failures(self, mock_ch_connect):
        """Если и retry упал — поднимается исключение (retry_err)."""
        from app.utils.clickhouse_client import ClickHouseClient

        conn1 = _fresh_mock_connection()
        conn1.query.side_effect = OSError("first fail")
        conn2 = _fresh_mock_connection()
        conn2.query.side_effect = RuntimeError("retry fail")

        mock_ch_connect.get_client.side_effect = [conn1, conn2]

        client = ClickHouseClient()
        with pytest.raises(RuntimeError, match="retry fail"):
            client.execute("SELECT 1")

    def test_execute_connection_invalidated_after_error(self, mock_ch_connect):
        """После ошибки execute() client в thread_local = None."""
        from app.utils.clickhouse_client import ClickHouseClient

        conn1 = _fresh_mock_connection()
        conn1.query.side_effect = OSError("fail")
        conn2 = _fresh_mock_connection()
        conn2.query.side_effect = RuntimeError("retry also fail")

        mock_ch_connect.get_client.side_effect = [conn1, conn2]

        client = ClickHouseClient()
        with pytest.raises(RuntimeError):
            client.execute("SELECT 1")

        # После двойного фейла client должен быть None
        assert getattr(client._thread_local, "client", None) is None


# ── 3. execute_df() — retry для SELECT ────────────────────────────────────────


class TestExecuteDf:
    def test_execute_df_retries_on_error(self, mock_ch_connect):
        """execute_df() делает одну повторную попытку при первой ошибке."""
        import pandas as pd

        from app.utils.clickhouse_client import ClickHouseClient

        expected_df = pd.DataFrame({"a": [1, 2, 3]})

        broken = _fresh_mock_connection()
        broken.query_df.side_effect = OSError("timeout")

        fresh = _fresh_mock_connection()
        fresh.query_df.return_value = expected_df

        mock_ch_connect.get_client.side_effect = [broken, fresh]

        client = ClickHouseClient()
        result = client.execute_df("SELECT a FROM t")

        assert mock_ch_connect.get_client.call_count == 2
        assert result is expected_df


# ── 4. INSERT/command — без retry ─────────────────────────────────────────────


class TestNoRetryForWrites:
    def test_insert_df_no_retry(self, mock_ch_connect):
        """insert_df() НЕ делает retry при ошибке (защита от дублей)."""
        import pandas as pd

        from app.utils.clickhouse_client import ClickHouseClient

        conn = _fresh_mock_connection()
        conn.insert_df.side_effect = OSError("write failed")
        mock_ch_connect.get_client.return_value = conn

        client = ClickHouseClient()
        with pytest.raises(OSError):
            client.insert_df("table", pd.DataFrame())

        # clickhouse_connect.get_client вызван только ОДИН раз (нет retry)
        assert mock_ch_connect.get_client.call_count == 1
        # Соединение инвалидировано
        assert getattr(client._thread_local, "client", None) is None

    def test_command_no_retry(self, mock_ch_connect):
        """command() НЕ делает retry при ошибке."""
        from app.utils.clickhouse_client import ClickHouseClient

        conn = _fresh_mock_connection()
        conn.command.side_effect = RuntimeError("DDL error")
        mock_ch_connect.get_client.return_value = conn

        client = ClickHouseClient()
        with pytest.raises(RuntimeError):
            client.command("CREATE TABLE t ...")

        assert mock_ch_connect.get_client.call_count == 1
        assert getattr(client._thread_local, "client", None) is None

    def test_insert_no_retry(self, mock_ch_connect):
        """insert() НЕ делает retry при ошибке."""
        from app.utils.clickhouse_client import ClickHouseClient

        conn = _fresh_mock_connection()
        conn.insert.side_effect = OSError("insert error")
        mock_ch_connect.get_client.return_value = conn

        client = ClickHouseClient()
        with pytest.raises(OSError):
            client.insert("table", [[1, 2, 3]], column_names=["a", "b", "c"])

        assert mock_ch_connect.get_client.call_count == 1
        assert getattr(client._thread_local, "client", None) is None


# ── 5. Thread isolation ────────────────────────────────────────────────────────


class TestThreadIsolation:
    def test_different_threads_get_different_connections(self, mock_ch_connect):
        """Каждый поток получает независимое соединение."""
        from app.utils.clickhouse_client import ClickHouseClient

        conn_a = _fresh_mock_connection()
        conn_b = _fresh_mock_connection()
        connections = [conn_a, conn_b]
        lock = threading.Lock()

        def make_conn(**kwargs):
            with lock:
                return connections.pop(0)

        mock_ch_connect.get_client.side_effect = make_conn

        client = ClickHouseClient()
        results = {}
        barrier = threading.Barrier(2)

        def thread_fn(name):
            c = client.get_client()
            barrier.wait()  # оба потока внутри get_client одновременно
            results[name] = c

        t1 = threading.Thread(target=thread_fn, args=("t1",))
        t2 = threading.Thread(target=thread_fn, args=("t2",))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert results["t1"] is not results["t2"], (
            "Потоки должны иметь РАЗНЫЕ соединения (thread_local)"
        )

    def test_invalidate_in_one_thread_does_not_affect_other(self, mock_ch_connect):
        """_invalidate() в одном потоке не затрагивает соединение другого потока."""
        from app.utils.clickhouse_client import ClickHouseClient

        conn_main = _fresh_mock_connection()
        conn_thread = _fresh_mock_connection()

        call_count = [0]
        lock = threading.Lock()

        def make_conn(**kwargs):
            with lock:
                call_count[0] += 1
                return conn_main if call_count[0] == 1 else conn_thread

        mock_ch_connect.get_client.side_effect = make_conn

        client = ClickHouseClient()
        # Основной поток — получает соединение
        main_conn = client.get_client()
        assert main_conn is conn_main

        thread_result = {}

        def other_thread():
            thread_result["conn"] = client.get_client()

        t = threading.Thread(target=other_thread)
        t.start()
        t.join()

        # Инвалидируем в основном потоке
        client._invalidate()

        # Соединение основного потока инвалидировано
        assert getattr(client._thread_local, "client", None) is None
        # Соединение другого потока НЕ тронуто
        assert thread_result["conn"] is conn_thread
