"""
Database Optimization Tests
Tests for read replica support and query monitoring
"""

import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from aitbc.database import (
    DatabaseConnection,
    QueryMetrics,
    QueryMonitor,
    ReadReplicaManager,
    create_pooled_engine,
)


class TestQueryMetrics:
    """Test query metrics dataclass"""

    def test_query_metrics_creation(self):
        """Test creating query metrics"""
        metrics = QueryMetrics(
            query="SELECT * FROM test",
            execution_time_ms=50.5,
            timestamp=datetime.now(),
            success=True,
            row_count=10
        )

        assert metrics.query == "SELECT * FROM test"
        assert metrics.execution_time_ms == 50.5
        assert metrics.success is True
        assert metrics.row_count == 10

    def test_query_metrics_with_error(self):
        """Test query metrics with error"""
        metrics = QueryMetrics(
            query="SELECT * FROM test",
            execution_time_ms=100.0,
            timestamp=datetime.now(),
            success=False,
            error_message="Connection failed",
            row_count=0
        )

        assert metrics.success is False
        assert metrics.error_message == "Connection failed"


class TestQueryMonitor:
    """Test query monitoring functionality"""

    def test_monitor_initialization(self):
        """Test query monitor initialization"""
        monitor = QueryMonitor(slow_query_threshold_ms=500.0, enable_logging=False)

        assert monitor.slow_query_threshold_ms == 500.0
        assert monitor.enable_logging is False
        assert monitor.metrics.total_queries == 0

    def test_record_successful_query(self):
        """Test recording a successful query"""
        monitor = QueryMonitor(enable_logging=False)

        monitor.record_query(
            query="SELECT * FROM users",
            execution_time_ms=45.0,
            success=True,
            row_count=10
        )

        stats = monitor.get_stats()
        assert stats["total_queries"] == 1
        assert stats["total_errors"] == 0
        assert stats["avg_execution_time_ms"] == 45.0

    def test_record_failed_query(self):
        """Test recording a failed query"""
        monitor = QueryMonitor(enable_logging=False)

        monitor.record_query(
            query="SELECT * FROM users",
            execution_time_ms=100.0,
            success=False,
            error_message="Table not found"
        )

        stats = monitor.get_stats()
        assert stats["total_queries"] == 1
        assert stats["total_errors"] == 1
        assert stats["error_rate"] == 1.0

    def test_slow_query_detection(self):
        """Test slow query detection"""
        monitor = QueryMonitor(slow_query_threshold_ms=100.0, enable_logging=False)

        # Record a slow query
        monitor.record_query(
            query="SELECT * FROM large_table",
            execution_time_ms=150.0,
            success=True,
            row_count=1000
        )

        slow_queries = monitor.get_slow_queries()
        assert len(slow_queries) == 1
        assert slow_queries[0].execution_time_ms == 150.0

    def test_get_top_queries(self):
        """Test getting most frequent queries"""
        monitor = QueryMonitor(enable_logging=False)

        # Record multiple slow queries (>1000ms threshold)
        monitor.record_query("SELECT * FROM users", 1500.0, True)
        monitor.record_query("SELECT * FROM users", 2000.0, True)
        monitor.record_query("SELECT * FROM posts", 2500.0, True)

        slow_queries = monitor.get_slow_queries(limit=2)
        assert len(slow_queries) == 2

    def test_average_execution_time_calculation(self):
        """Test average execution time calculation"""
        monitor = QueryMonitor(enable_logging=False)

        monitor.record_query("SELECT 1", 10.0, True)
        monitor.record_query("SELECT 2", 20.0, True)
        monitor.record_query("SELECT 3", 30.0, True)

        stats = monitor.get_stats()
        assert stats["avg_execution_time_ms"] == 20.0  # (10 + 20 + 30) / 3


class TestDatabaseConnectionMonitoring:
    """Test database connection with monitoring"""

    def test_database_connection_with_monitoring(self):
        """Test database connection with monitoring enabled"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"

            db = DatabaseConnection(db_path, enable_monitoring=True)
            db.connect()

            assert db.monitor is not None
            assert db.enable_monitoring is True

            db.close()

    def test_database_connection_without_monitoring(self):
        """Test database connection with monitoring disabled"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"

            db = DatabaseConnection(db_path, enable_monitoring=False)
            db.connect()

            assert db.monitor is None
            assert db.enable_monitoring is False

            db.close()

    def test_get_monitoring_stats(self):
        """Test getting monitoring statistics"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"

            db = DatabaseConnection(db_path, enable_monitoring=True)
            db.connect()

            # Execute a query
            db.execute("CREATE TABLE test (id INTEGER)")
            db.execute("INSERT INTO test VALUES (1)")

            stats = db.get_monitoring_stats()
            assert stats is not None
            assert stats["total_queries"] > 0

            db.close()

    def test_get_slow_queries(self):
        """Test getting slow queries"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"

            db = DatabaseConnection(db_path, enable_monitoring=True)
            db.connect()

            slow_queries = db.get_slow_queries(limit=5)
            assert isinstance(slow_queries, list)

            db.close()


class TestReadReplicaManager:
    """Test read replica management"""

    def test_read_replica_manager_initialization(self):
        """Test read replica manager initialization"""
        # Use SQLite URLs for testing (PostgreSQL would be used in production)
        primary_url = "sqlite:///test_primary.db"
        replica_urls = ["sqlite:///test_replica1.db", "sqlite:///test_replica2.db"]

        manager = ReadReplicaManager(
            primary_url=primary_url,
            replica_urls=replica_urls,
            read_weight=70
        )

        assert manager.primary_url == primary_url
        assert len(manager.replica_urls) == 2
        assert manager.read_weight == 70
        assert manager.enable_auto_failover is True

    def test_read_replica_manager_no_replicas(self):
        """Test read replica manager with no replicas"""
        primary_url = "sqlite:///test_primary.db"

        manager = ReadReplicaManager(
            primary_url=primary_url,
            replica_urls=None,
            read_weight=100
        )

        assert len(manager.replica_urls) == 0
        assert manager.read_weight == 100

    def test_get_write_engine(self):
        """Test getting write engine (always primary)"""
        primary_url = "sqlite:///test_primary.db"

        manager = ReadReplicaManager(primary_url=primary_url)

        write_engine = manager.get_write_engine()
        assert write_engine is not None

    def test_get_read_engine_with_replicas(self):
        """Test getting read engine with replicas"""
        with tempfile.TemporaryDirectory() as tmpdir:
            primary_url = f"sqlite:///{tmpdir}/test_primary.db"
            replica_url = f"sqlite:///{tmpdir}/test_replica.db"

            manager = ReadReplicaManager(
                primary_url=primary_url,
                replica_urls=[replica_url],
                read_weight=100
            )

            read_engine = manager.get_read_engine()
            assert read_engine is not None

    def test_get_read_engine_without_replicas(self):
        """Test getting read engine without replicas (falls back to primary)"""
        primary_url = "sqlite:///test_primary.db"

        manager = ReadReplicaManager(
            primary_url=primary_url,
            replica_urls=None,
            read_weight=100
        )

        read_engine = manager.get_read_engine()
        assert read_engine is not None

    def test_get_metrics(self):
        """Test getting database metrics"""
        primary_url = "sqlite:///test_primary.db"

        manager = ReadReplicaManager(primary_url=primary_url)

        metrics = manager.get_metrics()
        assert "query_monitor" in metrics
        assert "replica_count" in metrics
        assert "read_weight" in metrics

    def test_close_connections(self):
        """Test closing all database connections"""
        with tempfile.TemporaryDirectory() as tmpdir:
            primary_url = f"sqlite:///{tmpdir}/test_primary.db"
            replica_url = f"sqlite:///{tmpdir}/test_replica.db"

            manager = ReadReplicaManager(
                primary_url=primary_url,
                replica_urls=[replica_url]
            )

            # Should close without error
            manager.close()


class TestConnectionPooling:
    """Test connection pooling enhancements"""

    def test_create_pooled_engine_sqlite(self):
        """Test creating pooled engine for SQLite"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_url = f"sqlite:///{tmpdir}/test.db"

            engine = create_pooled_engine(db_url, pool_size=5)

            assert engine is not None
            engine.dispose()

    def test_create_pooled_engine_with_static_pool(self):
        """Test creating pooled engine with static pool for SQLite"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_url = f"sqlite:///{tmpdir}/test.db"

            engine = create_pooled_engine(db_url, use_static_pool=True)

            assert engine is not None
            engine.dispose()

    @pytest.mark.skip(reason="Requires PostgreSQL connection string")
    def test_create_pooled_engine_postgresql(self):
        """Test creating pooled engine for PostgreSQL"""
        db_url = "postgresql://user:pass@localhost/test"

        engine = create_pooled_engine(db_url, pool_size=10)

        assert engine is not None
        engine.dispose()


class TestDatabaseOptimizationIntegration:
    """Test integration of database optimization features"""

    def test_monitoring_integration_with_connection(self):
        """Test that monitoring integrates properly with database connection"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"

            db = DatabaseConnection(db_path, enable_monitoring=True)
            db.connect()

            # Execute some queries
            db.execute("CREATE TABLE test (id INTEGER, name TEXT)")
            db.execute("INSERT INTO test VALUES (1, 'test')")

            # Check that queries were monitored
            stats = db.get_monitoring_stats()
            assert stats["total_queries"] >= 2

            db.close()

    def test_slow_query_detection_integration(self):
        """Test slow query detection in real database operations"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"

            # Use a low threshold for testing
            db = DatabaseConnection(db_path, enable_monitoring=True)
            db.monitor.slow_query_threshold_ms = 0.1  # Very low threshold
            db.connect()

            # Execute a query
            db.execute("CREATE TABLE test (id INTEGER)")

            # Check for slow queries (might be slow on some systems)
            slow_queries = db.get_slow_queries()
            assert isinstance(slow_queries, list)

            db.close()

    def test_monitoring_disabled_performance(self):
        """Test that disabling monitoring doesn't affect functionality"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"

            db = DatabaseConnection(db_path, enable_monitoring=False)
            db.connect()

            # Should work normally without monitoring
            db.execute("CREATE TABLE test (id INTEGER)")
            db.execute("INSERT INTO test VALUES (1)")

            # Monitoring stats should be None
            assert db.get_monitoring_stats() is None

            db.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
