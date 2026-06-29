"""Tests for AITBC database subpackage.

Tests cover all 6 submodules:
- connection.py: DatabaseConnection class
- monitoring.py: QueryMetrics, DatabaseMetrics, QueryMonitor
- pooling.py: SQLAlchemy pooling utilities
- replica.py: ReadReplicaManager
- service.py: DatabaseService, SQLiteDatabaseService, DatabaseServiceFactory
- utils.py: Utility functions
"""

import sqlite3
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

# Import submodules directly for testing
from aitbc.database.connection import DatabaseConnection
from aitbc.database.monitoring import DatabaseMetrics, QueryMetrics, QueryMonitor
from aitbc.database.pooling import (
    create_async_pooled_engine,
    create_async_pooled_sessionmaker,
    create_pooled_engine,
    create_pooled_sessionmaker,
)
from aitbc.database.replica import ReadReplicaManager
from aitbc.database.service import DatabaseServiceFactory, SQLiteDatabaseService
from aitbc.database.utils import (
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
        # Connection should be closed after context

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
        execution_times = [q.execution_time_ms for q in slow]
        assert 200.0 in execution_times
        assert 300.0 in execution_times

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

    def test_reset(self):
        """Test reset method."""
        monitor = QueryMonitor()
        monitor.record_query("SELECT * FROM t1", 100.0)
        monitor.reset()

        assert monitor.metrics.total_queries == 0
        assert len(monitor.query_counts) == 0


class TestReadReplicaManager:
    """Test ReadReplicaManager class."""

    @patch("aitbc.database.replica.create_engine")
    def test_replica_manager_initialization(self, mock_create_engine):
        """Test ReadReplicaManager initialization."""
        mock_engine = Mock()
        mock_create_engine.return_value = mock_engine

        with patch.object(ReadReplicaManager, "_setup_monitoring"):
            manager = ReadReplicaManager(
                primary_url="postgresql://localhost/primary",
                replica_urls=["postgresql://localhost/replica1"],
                read_weight=70,
            )
            assert manager.primary_url == "postgresql://localhost/primary"
            assert manager.replica_urls == ["postgresql://localhost/replica1"]
            assert manager.read_weight == 70

    @patch("aitbc.database.replica.create_engine")
    def test_replica_manager_read_weight_clamp(self, mock_create_engine):
        """Test read_weight is clamped to 0-100."""
        mock_engine = Mock()
        mock_create_engine.return_value = mock_engine

        with patch.object(ReadReplicaManager, "_setup_monitoring"):
            manager = ReadReplicaManager(
                primary_url="postgresql://localhost/primary",
                read_weight=150,
            )
            assert manager.read_weight == 100

            manager2 = ReadReplicaManager(
                primary_url="postgresql://localhost/primary",
                read_weight=-10,
            )
            assert manager2.read_weight == 0

    @patch("aitbc.database.replica.create_engine")
    def test_get_read_engine_no_replicas(self, mock_create_engine):
        """Test get_read_engine when no replicas available."""
        mock_engine = Mock()
        mock_create_engine.return_value = mock_engine

        with patch.object(ReadReplicaManager, "_setup_monitoring"):
            manager = ReadReplicaManager(
                primary_url="postgresql://localhost/primary",
                replica_urls=[],
            )

        assert manager.get_read_engine() == mock_engine

    @patch("aitbc.database.replica.create_engine")
    def test_get_write_engine(self, mock_create_engine):
        """Test get_write_engine always returns primary."""
        mock_engine = Mock()
        mock_create_engine.return_value = mock_engine

        with patch.object(ReadReplicaManager, "_setup_monitoring"):
            manager = ReadReplicaManager(
                primary_url="postgresql://localhost/primary",
                replica_urls=["postgresql://localhost/replica1"],
            )
            assert manager.get_write_engine() == mock_engine

    @patch("aitbc.database.replica.sessionmaker")
    @patch("aitbc.database.replica.create_engine")
    def test_get_session_read(self, mock_create_engine, mock_sessionmaker):
        """Test get_session with read_only=True."""
        mock_engine = Mock()
        mock_create_engine.return_value = mock_engine
        mock_session = Mock()
        mock_sessionmaker.return_value = lambda: mock_session

        with patch.object(ReadReplicaManager, "_setup_monitoring"):
            manager = ReadReplicaManager(
                primary_url="postgresql://localhost/primary",
                replica_urls=["postgresql://localhost/replica1"],
            )

            session = manager.get_session(read_only=True)

        assert session == mock_session

    @patch("aitbc.database.replica.create_engine")
    def test_get_metrics(self, mock_create_engine):
        """Test get_metrics."""
        mock_engine = Mock()
        mock_create_engine.return_value = mock_engine

        with patch.object(ReadReplicaManager, "_setup_monitoring"):
            manager = ReadReplicaManager(
                primary_url="postgresql://localhost/primary",
                replica_urls=["postgresql://localhost/replica1"],
            )
            metrics = manager.get_metrics()

            assert "query_monitor" in metrics
            assert "replica_count" in metrics
            assert metrics["replica_count"] == 1

    @patch("aitbc.database.replica.create_engine")
    def test_close(self, mock_create_engine):
        """Test close disposes all engines."""
        mock_engine = Mock()
        mock_create_engine.return_value = mock_engine

        with patch.object(ReadReplicaManager, "_setup_monitoring"):
            manager = ReadReplicaManager(
                primary_url="postgresql://localhost/primary",
                replica_urls=["postgresql://localhost/replica1"],
            )

        manager.close()

        assert mock_engine.dispose.call_count >= 1


class TestSQLiteDatabaseService:
    """Test SQLiteDatabaseService class."""

    def test_service_creation(self, temp_db):
        """Test SQLiteDatabaseService creation."""
        service = SQLiteDatabaseService(temp_db, pool_size=3)
        assert service.db_path == temp_db
        assert service.pool_size == 3
        assert service._connections == []

    def test_ensure_database_creates_directory(self, temp_db):
        """Test _ensure_database creates parent directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "subdir" / "test.db"
            SQLiteDatabaseService(db_path)
            assert db_path.parent.exists()

    def test_get_connection(self, temp_db):
        """Test _get_connection returns connection."""
        service = SQLiteDatabaseService(temp_db, pool_size=2)
        conn = service._get_connection()
        assert isinstance(conn, sqlite3.Connection)
        assert conn.row_factory == sqlite3.Row

    def test_get_connection_pool_rotation(self, temp_db):
        """Test connection pool rotation."""
        service = SQLiteDatabaseService(temp_db, pool_size=2)

        conn1 = service._get_connection()
        service._get_connection()
        conn3 = service._get_connection()  # Should rotate back to conn1

        assert conn3 is conn1

    def test_get_connection_context_manager(self, temp_db):
        """Test get_connection context manager."""
        service = SQLiteDatabaseService(temp_db)

        with service.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)")
            cursor.execute("INSERT INTO test (name) VALUES (?)", ("test",))
            conn.commit()

    def test_execute_query(self, temp_db):
        """Test execute_query method."""
        service = SQLiteDatabaseService(temp_db)
        service.execute_query("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)")
        service.execute_query("INSERT INTO test (name) VALUES (?)", ("test1",))
        service.execute_query("INSERT INTO test (name) VALUES (?)", ("test2",))

        results = service.execute_query("SELECT * FROM test ORDER BY name")
        assert len(results) == 2
        assert results[0]["name"] == "test1"
        assert results[1]["name"] == "test2"

    def test_execute_query_with_params(self, temp_db):
        """Test execute_query with parameters."""
        service = SQLiteDatabaseService(temp_db)
        service.execute_query("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT, value INTEGER)")
        service.execute_query("INSERT INTO test (name, value) VALUES (?, ?)", ("item1", 100))
        service.execute_query("INSERT INTO test (name, value) VALUES (?, ?)", ("item2", 200))

        results = service.execute_query("SELECT * FROM test WHERE value > ?", (150,))
        assert len(results) == 1
        assert results[0]["name"] == "item2"

    def test_execute_update(self, temp_db):
        """Test execute_update method."""
        service = SQLiteDatabaseService(temp_db)
        service.execute_query("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)")

        count = service.execute_update("INSERT INTO test (name) VALUES (?)", ("test1",))
        assert count == 1

        count = service.execute_update("INSERT INTO test (name) VALUES (?)", ("test2",))
        assert count == 1

        count = service.execute_update("UPDATE test SET name = ? WHERE id = ?", ("updated", 1))
        assert count == 1

        results = service.execute_query("SELECT name FROM test WHERE id = ?", (1,))
        assert results[0]["name"] == "updated"

    def test_execute_transaction(self, temp_db):
        """Test execute_transaction method."""
        service = SQLiteDatabaseService(temp_db)
        service.execute_query("CREATE TABLE tx_test (id INTEGER PRIMARY KEY, value TEXT)")

        queries = [
            ("INSERT INTO tx_test (value) VALUES (?)", ("tx1",)),
            ("INSERT INTO tx_test (value) VALUES (?)", ("tx2",)),
        ]
        result = service.execute_transaction(queries)
        assert result is True

        results = service.execute_query("SELECT * FROM tx_test")
        assert len(results) == 2

    def test_execute_transaction_rollback_on_error(self, temp_db):
        """Test execute_transaction rolls back on error."""
        service = SQLiteDatabaseService(temp_db)
        service.execute_query("CREATE TABLE error_test (id INTEGER PRIMARY KEY, value TEXT)")

        queries = [
            ("INSERT INTO error_test (value) VALUES (?)", ("ok",)),
            ("INSERT INTO nonexistent (value) VALUES (?)", ("fail",)),
        ]

        with pytest.raises(sqlite3.OperationalError):
            service.execute_transaction(queries)

        # First insert should have been rolled back
        results = service.execute_query("SELECT * FROM error_test")
        assert len(results) == 0

    def test_connection_pooling(self, temp_db):
        """Test connection pooling reuses connections."""
        service = SQLiteDatabaseService(temp_db, pool_size=2)

        # Get two connections
        conn1 = service._get_connection()
        service._get_connection()

        # Third should reuse first
        conn3 = service._get_connection()
        assert conn3 is conn1

    def test_close_clears_connections(self, temp_db):
        """Test close clears all connections."""
        service = SQLiteDatabaseService(temp_db)
        service.execute_query("CREATE TABLE test (id INTEGER)")

        # Get some connections
        service._get_connection()
        service._get_connection()

        # Close should clear all
        service.close()
        assert service._connections == []


class TestDatabaseServiceFactory:
    """Test DatabaseServiceFactory class."""

    def test_create_sqlite_service(self, temp_db):
        """Test create_sqlite_service factory method."""
        service = DatabaseServiceFactory.create_sqlite_service(temp_db, pool_size=2)
        assert isinstance(service, SQLiteDatabaseService)
        assert service.pool_size == 2

    def test_create_service_sqlite(self, temp_db):
        """Test create_service with sqlite type."""
        service = DatabaseServiceFactory.create_service("sqlite", db_path=temp_db)
        assert isinstance(service, SQLiteDatabaseService)

    def test_create_service_unknown_type(self):
        """Test create_service with unknown type."""
        with pytest.raises(ValueError, match="Unknown database type: unknown"):
            DatabaseServiceFactory.create_service("unknown", db_path=Path("test.db"))


class TestDatabaseServiceIntegration:
    """Integration tests for database service."""

    def test_factory_creates_rpc_service(self, temp_db):
        """Test factory creates RPC service correctly."""
        service = DatabaseServiceFactory.create_service("sqlite", db_path=temp_db, pool_size=2)
        assert service is not None
        assert isinstance(service, SQLiteDatabaseService)

    @patch("aitbc.database.service.sqlite3.connect")
    def test_full_mock_flow(self, mock_connect):
        """Test full flow with mocked connections."""
        mock_conn = Mock()
        mock_connect.return_value = mock_conn

        mock_cursor = Mock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.__enter__ = Mock(return_value=mock_cursor)
        mock_cursor.__exit__ = Mock(return_value=False)

        # Row needs to be a proper dict-like object for dict()
        mock_cursor.fetchall.return_value = [
            {"name": "Alice", "email": "alice@example.com"},
            {"name": "Bob", "email": "bob@example.com"},
        ]
        mock_cursor.__enter__ = Mock(return_value=mock_cursor)

        service = SQLiteDatabaseService(Path("test.db"))
        result = service.execute_query("SELECT * FROM users")

        assert len(result) == 2
        assert result[0]["name"] == "Alice"
        assert result[0]["email"] == "alice@example.com"
        mock_cursor.execute.assert_called()
        mock_cursor.execute.assert_called()


class TestDatabaseUtils:
    """Test module-level utility functions."""

    def test_get_database_connection(self, temp_db):
        """Test get_database_connection function."""
        conn = get_database_connection(temp_db, timeout=30)
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

    def test_vacuum_database(self, temp_db):
        """Test vacuum_database function."""
        with DatabaseConnection(temp_db) as conn:
            conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY)")

        vacuum_database(temp_db)  # Should not raise

    def test_get_table_info(self, temp_db):
        """Test get_table_info function."""
        with DatabaseConnection(temp_db) as conn:
            conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, email TEXT)")

        info = get_table_info(temp_db, "users")

        assert isinstance(info, list)
        assert len(info) >= 3
        columns = [col["name"] for col in info]
        assert "id" in columns
        assert "name" in columns
        assert "email" in columns

    def test_table_exists(self, temp_db):
        """Test table_exists function."""
        with DatabaseConnection(temp_db) as conn:
            conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY)")

        assert table_exists(temp_db, "users") is True
        assert table_exists(temp_db, "nonexistent") is False


class TestPoolingFunctions:
    """Test SQLAlchemy pooling utility functions."""

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
        mock_create_engine.return_value = mock_engine
        mock_session = Mock()
        mock_sessionmaker.return_value = mock_session

        session = create_pooled_sessionmaker(mock_engine, autoflush=False, autocommit=False)

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
