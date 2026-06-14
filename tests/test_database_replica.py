"""Tests for aitbc.database metrics"""

from datetime import datetime

from aitbc.database import DatabaseMetrics, QueryMetrics


class TestQueryMetrics:
    def test_creation(self):
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
        qm = QueryMetrics(query="SELECT 1", execution_time_ms=10.0, timestamp=datetime.now(), success=False, error_message="fail")
        dm.add_query(qm)
        assert dm.total_errors == 1

    def test_add_query_slow(self):
        dm = DatabaseMetrics()
        qm = QueryMetrics(query="SELECT 1", execution_time_ms=2000.0, timestamp=datetime.now(), success=True)
        dm.add_query(qm, slow_threshold_ms=1000.0)
        assert len(dm.slow_queries) == 1

    def test_recent_queries_limit(self):
        dm = DatabaseMetrics()
        for i in range(110):
            dm.add_query(QueryMetrics(query=f"Q{i}", execution_time_ms=1.0, timestamp=datetime.now(), success=True))
        assert len(dm.recent_queries) == 100
