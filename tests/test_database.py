"""Tests for aitbc.database utilities"""

import tempfile
from datetime import datetime
from pathlib import Path

from aitbc.database import (
    DatabaseConnection,
    DatabaseMetrics,
    QueryMetrics,
    QueryMonitor,
    create_pooled_engine,
    create_pooled_sessionmaker,
    ensure_database,
    get_database_connection,
    get_table_info,
    table_exists,
    vacuum_database,
)


class TestQueryMetrics:
    def test_query_metrics_creation(self):
        qm = QueryMetrics(query="SELECT 1", execution_time_ms=10.0, timestamp=datetime.now(), success=True)
        assert qm.query == "SELECT 1"
        assert qm.success is True


class TestDatabaseMetrics:
    def test_add_query_success(self):
        dm = DatabaseMetrics()
        qm = QueryMetrics(query="SELECT 1", execution_time_ms=10.0, timestamp=datetime.now(), success=True)
        dm.add_query(qm)
        assert dm.total_queries == 1
        assert dm.total_errors == 0

    def test_add_query_error(self):
        dm = DatabaseMetrics()
        qm = QueryMetrics(
            query="SELECT 1", execution_time_ms=10.0, timestamp=datetime.now(), success=False, error_message="fail"
        )
        dm.add_query(qm)
        assert dm.total_queries == 1
        assert dm.total_errors == 1

    def test_add_query_slow(self):
        dm = DatabaseMetrics()
        qm = QueryMetrics(query="SELECT 1", execution_time_ms=2000.0, timestamp=datetime.now(), success=True)
        dm.add_query(qm, slow_threshold_ms=1000.0)
        assert len(dm.slow_queries) == 1

    def test_avg_calculation(self):
        dm = DatabaseMetrics()
        dm.add_query(QueryMetrics(query="Q1", execution_time_ms=10.0, timestamp=datetime.now(), success=True))
        dm.add_query(QueryMetrics(query="Q2", execution_time_ms=20.0, timestamp=datetime.now(), success=True))
        assert dm.avg_execution_time_ms == 15.0


class TestQueryMonitor:
    def test_record_query_success(self):
        qm = QueryMonitor()
        qm.record_query("SELECT 1", 10.0, success=True)
        assert qm.metrics.total_queries == 1

    def test_record_query_error(self):
        qm = QueryMonitor()
        qm.record_query("SELECT 1", 10.0, success=False, error_message="fail")
        assert qm.metrics.total_errors == 1

    def test_get_slow_queries(self):
        qm = QueryMonitor(slow_query_threshold_ms=5.0)
        qm.record_query("SELECT 1", 100.0, success=True)
        slow = qm.get_slow_queries()
        assert len(slow) == 1

    def test_get_stats(self):
        qm = QueryMonitor()
        qm.record_query("SELECT 1", 10.0, success=True)
        stats = qm.get_stats()
        assert stats["total_queries"] == 1
        assert stats["error_rate"] == 0.0


class TestDatabaseConnection:
    def test_connect(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = Path(f.name)
        try:
            db = DatabaseConnection(path)
            conn = db.connect()
            assert conn is not None
            db.close()
        finally:
            path.unlink(missing_ok=True)

    def test_context_manager(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = Path(f.name)
        try:
            with DatabaseConnection(path) as db:
                assert db._connection is not None
        finally:
            path.unlink(missing_ok=True)

    def test_execute_and_fetch(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = Path(f.name)
        try:
            with DatabaseConnection(path) as db:
                db.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
                db.execute("INSERT INTO users (name) VALUES (?)", ("Alice",))
                result = db.fetch_one("SELECT * FROM users WHERE name = ?", ("Alice",))
                assert result["name"] == "Alice"
        finally:
            path.unlink(missing_ok=True)

    def test_fetch_all(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = Path(f.name)
        try:
            with DatabaseConnection(path) as db:
                db.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
                db.execute("INSERT INTO users (name) VALUES (?)", ("Alice",))
                db.execute("INSERT INTO users (name) VALUES (?)", ("Bob",))
                results = db.fetch_all("SELECT * FROM users")
                assert len(results) == 2
        finally:
            path.unlink(missing_ok=True)

    def test_execute_many(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = Path(f.name)
        try:
            with DatabaseConnection(path) as db:
                db.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
                db.execute_many("INSERT INTO users (name) VALUES (?)", [("Alice",), ("Bob",)])
                results = db.fetch_all("SELECT * FROM users")
                assert len(results) == 2
        finally:
            path.unlink(missing_ok=True)

    def test_fetch_one_none(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = Path(f.name)
        try:
            with DatabaseConnection(path) as db:
                db.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
                result = db.fetch_one("SELECT * FROM users")
                assert result is None
        finally:
            path.unlink(missing_ok=True)

    def test_get_monitoring_stats(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = Path(f.name)
        try:
            db = DatabaseConnection(path, enable_monitoring=True)
            stats = db.get_monitoring_stats()
            assert stats is not None
        finally:
            path.unlink(missing_ok=True)

    def test_get_monitoring_stats_disabled(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = Path(f.name)
        try:
            db = DatabaseConnection(path, enable_monitoring=False)
            assert db.get_monitoring_stats() is None
        finally:
            path.unlink(missing_ok=True)


class TestUtilityFunctions:
    def test_ensure_database(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "subdir" / "test.db"
            result = ensure_database(path)
            assert result == path
            assert path.parent.exists()

    def test_get_database_connection(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = Path(f.name)
        try:
            db = get_database_connection(path)
            assert isinstance(db, DatabaseConnection)
        finally:
            path.unlink(missing_ok=True)

    def test_vacuum_database(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = Path(f.name)
        try:
            vacuum_database(path)
            assert path.exists()
        finally:
            path.unlink(missing_ok=True)

    def test_table_exists_true(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = Path(f.name)
        try:
            with DatabaseConnection(path) as db:
                db.execute("CREATE TABLE test_table (id INTEGER)")
            assert table_exists(path, "test_table") is True
        finally:
            path.unlink(missing_ok=True)

    def test_table_exists_false(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = Path(f.name)
        try:
            assert table_exists(path, "missing") is False
        finally:
            path.unlink(missing_ok=True)

    def test_get_table_info(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = Path(f.name)
        try:
            with DatabaseConnection(path) as db:
                db.execute("CREATE TABLE test_table (id INTEGER, name TEXT)")
            info = get_table_info(path, "test_table")
            assert len(info) == 2
        finally:
            path.unlink(missing_ok=True)


class TestPooledEngine:
    def test_create_pooled_engine_sqlite(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = Path(f.name)
        try:
            engine = create_pooled_engine(f"sqlite:///{path}")
            assert engine is not None
            engine.dispose()
        finally:
            path.unlink(missing_ok=True)

    def test_create_pooled_engine_sqlite_static(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = Path(f.name)
        try:
            engine = create_pooled_engine(f"sqlite:///{path}", use_static_pool=True)
            assert engine is not None
            engine.dispose()
        finally:
            path.unlink(missing_ok=True)

    def test_create_pooled_sessionmaker(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = Path(f.name)
        try:
            engine = create_pooled_engine(f"sqlite:///{path}")
            sm = create_pooled_sessionmaker(engine)
            assert sm is not None
            engine.dispose()
        finally:
            path.unlink(missing_ok=True)
