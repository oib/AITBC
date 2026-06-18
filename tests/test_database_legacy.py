"""Tests for AITBC database module (legacy) - database.py

Tests cover:
- QueryMetrics dataclass
- DatabaseMetrics dataclass
- QueryMonitor class
- DatabaseConnection class
- Module-level functions
"""

import sqlite3
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from aitbc.database import (
    DatabaseConnection,
    DatabaseMetrics,
    QueryMetrics,
    QueryMonitor,
    create_async_pooled_engine,
    create_async_pooled_sessionmaker,
    create_pooled_engine,
    create_pooled_sessionmaker,
    ensure_database,
    get_database_connection,
    get_table_info,
    table_exists,
    vacuum_database,
)


# Fixture for temporary database
@pytest.fixture
def temp_db():
    """Create a temporary database file."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    yield db_path
    if db_path.exists():
        db_path.unlink()


class TestQueryMetrics:
    """Test QueryMetrics dataclass."""

    def test_query_metrics_creation(self):
        """Test QueryMetrics creation with all fields."""
        metrics = QueryMetrics(
            query="SELECT * FROM users",
            execution_time_ms=150.5,
            timestamp=datetime.now(UTC),
            success=True,
            error_message=None,
            row_count=10,
        )
        assert metrics.query == "SELECT * FROM users"
        assert metrics.execution_time_ms == 150.5
        assert metrics.success is True
        assert metrics.error_message is None
        assert metrics.row_count == 10

    def test_query_metrics_with_error(self):
        """Test QueryMetrics with error."""
        metrics = QueryMetrics(
            query="SELECT * FROM nonexistent",
            execution_time_ms=50.0,
            timestamp=datetime.now(UTC),
            success=False,
            error_message="Table not found",
            row_count=0,
        )
        assert metrics.success is False
        assert metrics.error_message == "Table not found"
        assert metrics.row_count == 0


class TestDatabaseMetrics:
    """Test DatabaseMetrics dataclass."""

    def test_database_metrics_defaults(self):
        """Test DatabaseMetrics with default values."""
        metrics = DatabaseMetrics()
        assert metrics.total_queries == 0
        assert metrics.total_errors == 0
        assert metrics.avg_execution_time_ms == 0.0
        assert metrics.slow_queries == []
        assert metrics.recent_queries == []

    def test_add_query_success(self):
        """Test add_query with successful query."""
        metrics = DatabaseMetrics()
        query_metrics = QueryMetrics(
            query="SELECT * FROM users",
            execution_time_ms=100.0,
            timestamp=datetime.now(UTC),
            success=True,
            row_count=5,
        )
        metrics.add_query(query_metrics)

        assert metrics.total_queries == 1
        assert metrics.total_errors == 0
        assert metrics.avg_execution_time_ms == 100.0
        assert len(metrics.recent_queries) == 1

    def test_add_query_error(self):
        """Test add_query with failed query."""
        metrics = DatabaseMetrics()
        query_metrics = QueryMetrics(
            query="SELECT * FROM users",
            execution_time_ms=100.0,
            timestamp=datetime.now(UTC),
            success=False,
            error_message="Error",
            row_count=0,
        )
        metrics.add_query(query_metrics)

        assert metrics.total_queries == 1
        assert metrics.total_errors == 1

    def test_add_query_slow_threshold(self):
        """Test add_query adds slow queries."""
        metrics = DatabaseMetrics()
        query_metrics = QueryMetrics(
            query="SELECT * FROM users",
            execution_time_ms=2000.0,
            timestamp=datetime.now(UTC),
            success=True,
            row_count=10,
        )
        metrics.add_query(query_metrics, slow_threshold_ms=1000.0)

        assert len(metrics.slow_queries) == 1
        assert metrics.slow_queries[0].execution_time_ms == 2000.0

    def test_add_query_recent_limit(self):
        """Test recent_queries maintains limit of 100."""
        metrics = DatabaseMetrics()
        for i in range(150):
            query_metrics = QueryMetrics(
                query=f"SELECT * FROM table_{i}",
                execution_time_ms=50.0,
                timestamp=datetime.now(UTC),
                success=True,
                row_count=1,
            )
            metrics.add_query(query_metrics)

        assert len(metrics.recent_queries) == 100
        assert metrics.total_queries == 150


class TestQueryMonitor:
    """Test QueryMonitor class."""

    def test_query_monitor_initialization(self):
        """Test QueryMonitor initialization with defaults."""
        monitor = QueryMonitor()
        assert monitor.slow_query_threshold_ms == 1000.0
        assert monitor.enable_logging is True
        assert monitor.metrics.total_queries == 0

    def test_query_monitor_custom_params(self):
        """Test QueryMonitor with custom parameters."""
        monitor = QueryMonitor(slow_query_threshold_ms=500.0, enable_logging=False)
        assert monitor.slow_query_threshold_ms == 500.0
        assert monitor.enable_logging is False

    def test_record_query_success(self):
        """Test record_query with successful query."""
        monitor = QueryMonitor()
        monitor.record_query(
            query="SELECT * FROM users",
            execution_time_ms=150.0,
            success=True,
            row_count=10,
        )

        assert monitor.metrics.total_queries == 1
        assert monitor.metrics.total_errors == 0
        assert monitor.query_counts["SELECT * FROM users"] == 1

    def test_record_query_error(self):
        """Test record_query with error."""
        monitor = QueryMonitor()
        monitor.record_query(
            query="SELECT * FROM users",
            execution_time_ms=50.0,
            success=False,
            error_message="Table not found",
            row_count=0,
        )

        assert monitor.metrics.total_queries == 1
        assert monitor.metrics.total_errors == 1

    def test_record_query_slow(self):
        """Test record_query with slow query."""
        monitor = QueryMonitor(slow_query_threshold_ms=100.0)
        monitor.record_query(
            query="SELECT * FROM users",
            execution_time_ms=200.0,
            success=True,
            row_count=10,
        )

        slow_queries = monitor.get_slow_queries()
        assert len(slow_queries) == 1

    def test_get_slow_queries(self):
        """Test get_slow_queries."""
        monitor = QueryMonitor(slow_query_threshold_ms=100.0)
        monitor.record_query("SELECT * FROM t1", 50.0, row_count=1)
        monitor.record_query("SELECT * FROM t2", 200.0, row_count=2)
        monitor.record_query("SELECT * FROM t3", 300.0, row_count=3)

        slow = monitor.get_slow_queries(limit=2)
        assert len(slow) == 2
        # Both 200 and 300 should be in the slow queries (both > 100ms threshold)
        execution_times = [q.execution_time_ms for q in slow]
        assert 200.0 in execution_times
        assert 300.0 in execution_times

    def test_get_top_queries(self):
        """Test get_top_queries."""
        monitor = QueryMonitor()
        for _i in range(3):
            monitor.record_query("SELECT * FROM t1", 50.0)
            monitor.record_query("SELECT * FROM t2", 50.0)
        monitor.record_query("SELECT * FROM t3", 50.0)

        top = monitor.get_top_queries(limit=2)
        assert len(top) == 2
        assert top[0][0] == "SELECT * FROM t1"
        assert top[0][1] == 3

    def test_get_stats(self):
        """Test get_stats."""
        monitor = QueryMonitor()
        monitor.record_query("SELECT * FROM t1", 100.0)
        monitor.record_query("SELECT * FROM t2", 200.0)
        monitor.record_query("SELECT * FROM t3", 300.0, success=False)

        stats = monitor.get_stats()

        assert stats["total_queries"] == 3
        assert stats["total_errors"] == 1
        assert stats["error_rate"] == 1 / 3
        assert stats["avg_execution_time_ms"] == 200.0


class TestDatabaseConnection:
    """Test DatabaseConnection class."""

    def test_database_connection_init(self, temp_db):
        """Test DatabaseConnection initialization."""
        conn = DatabaseConnection(temp_db, timeout=30, enable_monitoring=True)
        assert conn.db_path == temp_db
        assert conn.timeout == 30
        assert conn.enable_monitoring is True
        assert conn.monitor is not None

    def test_database_connection_init_no_monitoring(self, temp_db):
        """Test DatabaseConnection without monitoring."""
        conn = DatabaseConnection(temp_db, enable_monitoring=False)
        assert conn.monitor is None

    def test_connect(self, temp_db):
        """Test connect method."""
        conn = DatabaseConnection(temp_db)
        sqlite_conn = conn.connect()

        assert isinstance(sqlite_conn, sqlite3.Connection)
        assert sqlite_conn.row_factory == sqlite3.Row
        conn.close()

    def test_context_manager(self, temp_db):
        """Test context manager."""
        with DatabaseConnection(temp_db) as conn:
            assert conn._connection is not None

    def test_close(self, temp_db):
        """Test close method."""
        conn = DatabaseConnection(temp_db)
        conn.connect()
        conn.close()
        assert conn._connection is None

    def test_execute(self, temp_db):
        """Test execute method."""
        with DatabaseConnection(temp_db) as conn:
            conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)")
            cursor = conn.execute("INSERT INTO test (name) VALUES (?)", ("test",))
            assert cursor.rowcount == 1

    def test_fetch_one(self, temp_db):
        """Test fetch_one method."""
        with DatabaseConnection(temp_db) as conn:
            conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)")
            conn.execute("INSERT INTO test (name) VALUES (?)", ("test",))

            row = conn.fetch_one("SELECT * FROM test WHERE name = ?", ("test",))
            assert row is not None
            assert row["name"] == "test"

            row = conn.fetch_one("SELECT * FROM test WHERE name = ?", ("nonexistent",))
            assert row is None

    def test_fetch_all(self, temp_db):
        """Test fetch_all method."""
        with DatabaseConnection(temp_db) as conn:
            conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)")
            conn.execute("INSERT INTO test (name) VALUES (?)", ("test1",))
            conn.execute("INSERT INTO test (name) VALUES (?)", ("test2",))

            rows = conn.fetch_all("SELECT * FROM test ORDER BY name")
            assert len(rows) == 2
            assert rows[0]["name"] == "test1"
            assert rows[1]["name"] == "test2"

    def test_execute_many(self, temp_db):
        """Test execute_many method."""
        with DatabaseConnection(temp_db) as conn:
            conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)")
            conn.execute_many("INSERT INTO test (name) VALUES (?)", [("a",), ("b",), ("c",)])

            rows = conn.fetch_all("SELECT name FROM test ORDER BY name")
            assert len(rows) == 3

    def test_monitoring(self, temp_db):
        """Test query monitoring."""
        with DatabaseConnection(temp_db, enable_monitoring=True) as conn:
            conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY)")
            conn.execute("INSERT INTO test DEFAULT VALUES")

            stats = conn.get_monitoring_stats()
            assert stats is not None
            assert stats["total_queries"] >= 2

    def test_get_slow_queries(self, temp_db):
        """Test get_slow_queries."""
        with DatabaseConnection(temp_db, enable_monitoring=True) as conn:
            conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY)")
            slow = conn.get_slow_queries()
            assert isinstance(slow, list)


class TestModuleFunctions:
    """Test module-level functions."""

    def test_get_database_connection(self):
        """Test get_database_connection function."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        conn = get_database_connection(db_path, timeout=30)
        assert isinstance(conn, DatabaseConnection)
        assert conn.timeout == 30

    def test_ensure_database(self):
        """Test ensure_database utility creates directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "subdir" / "test.db"
            result = ensure_database(db_path)

            assert result == db_path
            assert db_path.parent.exists()
            # Note: ensure_database only creates parent directory, not the file itself

    def test_vacuum_database(self):
        """Test vacuum_database function."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        with DatabaseConnection(db_path) as conn:
            conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY)")

        vacuum_database(db_path)  # Should not raise

    def test_get_table_info(self):
        """Test get_table_info function."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        with DatabaseConnection(db_path) as conn:
            conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, email TEXT)")

        info = get_table_info(db_path, "users")

        assert isinstance(info, list)
        assert len(info) >= 3
        columns = [col["name"] for col in info]
        assert "id" in columns
        assert "name" in columns
        assert "email" in columns

    def test_table_exists(self):
        """Test table_exists function."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        with DatabaseConnection(db_path) as conn:
            conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY)")

        assert table_exists(db_path, "users") is True
        assert table_exists(db_path, "nonexistent") is False

    @patch("aitbc.database.pooling.create_engine")
    def test_create_pooled_engine_sqlite_static(self, mock_create_engine):
        """Test create_pooled_engine for SQLite with static pool."""
        mock_engine = Mock()
        mock_create_engine.return_value = mock_engine

        engine = create_pooled_engine("sqlite:///test.db", use_static_pool=True)

        assert engine == mock_engine
        mock_create_engine.assert_called_once()

    @patch("aitbc.database.pooling.create_engine")
    def test_create_pooled_engine_sqlite_queue(self, mock_create_engine):
        """Test create_pooled_engine for SQLite with queue pool."""
        mock_engine = Mock()
        mock_create_engine.return_value = mock_engine

        engine = create_pooled_engine("sqlite:///test.db", pool_size=5, max_overflow=10)

        assert engine == mock_engine

    @patch("aitbc.database.pooling.create_engine")
    def test_create_pooled_engine_postgresql(self, mock_create_engine):
        """Test create_pooled_engine for PostgreSQL."""
        mock_engine = Mock()
        mock_create_engine.return_value = mock_engine

        engine = create_pooled_engine("postgresql://localhost/test", pool_size=10, max_overflow=20)

        assert engine == mock_engine

    @patch("aitbc.database.pooling.sessionmaker")
    @patch("aitbc.database.pooling.create_engine")
    def test_create_pooled_sessionmaker(self, mock_create_engine, mock_sessionmaker):
        """Test create_pooled_sessionmaker."""
        mock_engine = Mock()
        mock_session = Mock()
        mock_create_engine.return_value = mock_engine
        mock_sessionmaker.return_value = mock_session

        session = create_pooled_sessionmaker(mock_engine)

        assert session == mock_session
        mock_sessionmaker.assert_called_once_with(bind=mock_engine, autoflush=False, autocommit=False)

    @patch("aitbc.database.pooling.create_async_engine")
    def test_create_async_pooled_engine_sqlite(self, mock_create_async_engine):
        """Test create_async_pooled_engine for SQLite."""
        mock_engine = Mock()
        mock_create_async_engine.return_value = mock_engine

        engine = create_async_pooled_engine("sqlite:///test.db")

        assert engine == mock_engine

    @patch("aitbc.database.pooling.create_async_engine")
    def test_create_async_pooled_engine_postgresql(self, mock_create_async_engine):
        """Test create_async_pooled_engine for PostgreSQL."""
        mock_engine = Mock()
        mock_create_async_engine.return_value = mock_engine

        engine = create_async_pooled_engine("postgresql://localhost/test")

        assert engine == mock_engine

    @patch("aitbc.database.pooling.async_sessionmaker")
    def test_create_async_pooled_sessionmaker(self, mock_async_sessionmaker):
        """Test create_async_pooled_sessionmaker."""
        mock_engine = Mock()
        mock_session = Mock()
        mock_async_sessionmaker.return_value = mock_session

        session = create_async_pooled_sessionmaker(mock_engine, expire_on_commit=True)

        assert session == mock_session
        mock_async_sessionmaker.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
