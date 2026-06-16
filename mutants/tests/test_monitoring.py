"""
Tests for monitoring and metrics utilities
"""

import time

import pytest

from aitbc.monitoring import (
    HealthChecker,
    MetricsCollector,
    PerformanceTimer,
)


class TestMetricsCollector:
    """Tests for MetricsCollector"""

    def test_initialization(self):
        """Test MetricsCollector initialization"""
        collector = MetricsCollector()
        assert collector.counters == {}
        assert collector.timers == {}
        assert collector.gauges == {}
        assert collector.timestamps == {}

    def test_increment(self):
        """Test increment counter"""
        collector = MetricsCollector()
        collector.increment("test_metric")
        assert collector.get_counter("test_metric") == 1
        assert "test_metric" in collector.timestamps

    def test_increment_with_value(self):
        """Test increment with custom value"""
        collector = MetricsCollector()
        collector.increment("test_metric", value=5)
        assert collector.get_counter("test_metric") == 5

    def test_increment_multiple(self):
        """Test multiple increments"""
        collector = MetricsCollector()
        collector.increment("test_metric")
        collector.increment("test_metric")
        collector.increment("test_metric")
        assert collector.get_counter("test_metric") == 3

    def test_decrement(self):
        """Test decrement counter"""
        collector = MetricsCollector()
        collector.increment("test_metric", value=10)
        collector.decrement("test_metric")
        assert collector.get_counter("test_metric") == 9

    def test_decrement_with_value(self):
        """Test decrement with custom value"""
        collector = MetricsCollector()
        collector.increment("test_metric", value=10)
        collector.decrement("test_metric", value=3)
        assert collector.get_counter("test_metric") == 7

    def test_timing(self):
        """Test record timing"""
        collector = MetricsCollector()
        collector.timing("test_metric", 0.5)
        stats = collector.get_timer_stats("test_metric")
        assert stats["count"] == 1
        assert stats["min"] == 0.5
        assert stats["max"] == 0.5
        assert stats["avg"] == 0.5

    def test_timing_multiple(self):
        """Test multiple timing records"""
        collector = MetricsCollector()
        collector.timing("test_metric", 0.1)
        collector.timing("test_metric", 0.2)
        collector.timing("test_metric", 0.3)
        stats = collector.get_timer_stats("test_metric")
        assert stats["count"] == 3
        assert stats["min"] == 0.1
        assert stats["max"] == 0.3
        assert stats["avg"] == pytest.approx(0.2)

    def test_set_gauge(self):
        """Test set gauge"""
        collector = MetricsCollector()
        collector.set_gauge("test_metric", 42.5)
        assert collector.get_gauge("test_metric") == 42.5

    def test_set_gauge_override(self):
        """Test gauge override"""
        collector = MetricsCollector()
        collector.set_gauge("test_metric", 10.0)
        collector.set_gauge("test_metric", 20.0)
        assert collector.get_gauge("test_metric") == 20.0

    def test_get_counter_nonexistent(self):
        """Test get counter for nonexistent metric"""
        collector = MetricsCollector()
        assert collector.get_counter("nonexistent") == 0

    def test_get_timer_stats_nonexistent(self):
        """Test get timer stats for nonexistent metric"""
        collector = MetricsCollector()
        stats = collector.get_timer_stats("nonexistent")
        assert stats["min"] == 0
        assert stats["max"] == 0
        assert stats["avg"] == 0
        assert stats["count"] == 0

    def test_get_gauge_nonexistent(self):
        """Test get gauge for nonexistent metric"""
        collector = MetricsCollector()
        assert collector.get_gauge("nonexistent") is None

    def test_get_all_metrics(self):
        """Test get all metrics"""
        collector = MetricsCollector()
        collector.increment("counter1")
        collector.timing("timer1", 0.5)
        collector.set_gauge("gauge1", 10.0)

        metrics = collector.get_all_metrics()

        assert "counters" in metrics
        assert "timers" in metrics
        assert "gauges" in metrics
        assert "timestamps" in metrics
        assert metrics["counters"]["counter1"] == 1
        assert metrics["timers"]["timer1"]["count"] == 1
        assert metrics["gauges"]["gauge1"] == 10.0

    def test_reset_metric(self):
        """Test reset specific metric"""
        collector = MetricsCollector()
        collector.increment("test_metric")
        collector.timing("test_metric", 0.5)
        collector.set_gauge("test_metric", 10.0)

        collector.reset_metric("test_metric")

        assert collector.get_counter("test_metric") == 0
        assert collector.get_timer_stats("test_metric")["count"] == 0
        assert collector.get_gauge("test_metric") is None

    def test_reset_all(self):
        """Test reset all metrics"""
        collector = MetricsCollector()
        collector.increment("metric1")
        collector.timing("metric2", 0.5)
        collector.set_gauge("metric3", 10.0)

        collector.reset_all()

        assert collector.get_counter("metric1") == 0
        assert collector.get_timer_stats("metric2")["count"] == 0
        assert collector.get_gauge("metric3") is None


class TestPerformanceTimer:
    """Tests for PerformanceTimer"""

    def test_timer_context_manager(self):
        """Test PerformanceTimer as context manager"""
        collector = MetricsCollector()

        with PerformanceTimer(collector, "test_metric"):
            time.sleep(0.01)

        stats = collector.get_timer_stats("test_metric")
        assert stats["count"] == 1
        assert stats["min"] > 0

    def test_timer_records_duration(self):
        """Test timer records correct duration"""
        collector = MetricsCollector()

        with PerformanceTimer(collector, "test_metric"):
            time.sleep(0.05)

        stats = collector.get_timer_stats("test_metric")
        assert stats["min"] >= 0.05

    def test_timer_multiple_uses(self):
        """Test timer can be used multiple times"""
        collector = MetricsCollector()

        with PerformanceTimer(collector, "test_metric"):
            time.sleep(0.01)

        with PerformanceTimer(collector, "test_metric"):
            time.sleep(0.01)

        stats = collector.get_timer_stats("test_metric")
        assert stats["count"] == 2


class TestHealthChecker:
    """Tests for HealthChecker"""

    def test_initialization(self):
        """Test HealthChecker initialization"""
        checker = HealthChecker()
        assert checker.checks == {}
        assert checker.last_check is None

    def test_add_check(self):
        """Test add health check"""
        checker = HealthChecker()

        def check_func():
            return ("healthy", "All good")

        checker.add_check("test_check", check_func)
        assert "test_check" in checker.checks

    def test_run_check_success(self):
        """Test run check successfully"""
        checker = HealthChecker()

        def check_func():
            return ("healthy", "All good")

        checker.add_check("test_check", check_func)
        result = checker.run_check("test_check")

        assert result["status"] == "healthy"
        assert result["message"] == "All good"

    def test_run_check_not_found(self):
        """Test run check when check doesn't exist"""
        checker = HealthChecker()
        result = checker.run_check("nonexistent")

        assert result["status"] == "unknown"
        assert "not found" in result["message"]

    def test_run_check_exception(self):
        """Test run check when check raises exception"""
        checker = HealthChecker()

        def check_func():
            raise ValueError("Test error")

        checker.add_check("test_check", check_func)
        result = checker.run_check("test_check")

        assert result["status"] == "error"
        assert "Test error" in result["message"]

    def test_run_all_checks(self):
        """Test run all checks"""
        checker = HealthChecker()

        def check1():
            return ("healthy", "Check 1 OK")

        def check2():
            return ("healthy", "Check 2 OK")

        checker.add_check("check1", check1)
        checker.add_check("check2", check2)

        results = checker.run_all_checks()

        assert "checks" in results
        assert "overall_status" in results
        assert "timestamp" in results
        assert results["overall_status"] == "healthy"
        assert checker.last_check is not None

    def test_run_all_checks_degraded(self):
        """Test run all checks with degraded status"""
        checker = HealthChecker()

        def check1():
            return ("healthy", "Check 1 OK")

        def check2():
            return ("degraded", "Check 2 degraded")

        checker.add_check("check1", check1)
        checker.add_check("check2", check2)

        results = checker.run_all_checks()

        assert results["overall_status"] == "degraded"

    def test_run_all_checks_unhealthy(self):
        """Test run all checks with unhealthy status"""
        checker = HealthChecker()

        def check1():
            return ("healthy", "Check 1 OK")

        def check2():
            return ("unhealthy", "Check 2 failed")

        checker.add_check("check1", check1)
        checker.add_check("check2", check2)

        results = checker.run_all_checks()

        assert results["overall_status"] == "unhealthy"

    def test_run_all_checks_empty(self):
        """Test run all checks with no checks"""
        checker = HealthChecker()
        results = checker.run_all_checks()

        assert results["overall_status"] == "unknown"
        assert results["checks"] == {}

    def test_get_overall_status_healthy(self):
        """Test overall status calculation for healthy"""
        checker = HealthChecker()
        results = {"check1": {"status": "healthy"}, "check2": {"status": "healthy"}}
        status = checker._get_overall_status(results)
        assert status == "healthy"

    def test_get_overall_status_degraded(self):
        """Test overall status calculation for degraded"""
        checker = HealthChecker()
        results = {"check1": {"status": "healthy"}, "check2": {"status": "degraded"}}
        status = checker._get_overall_status(results)
        assert status == "degraded"

    def test_get_overall_status_unhealthy(self):
        """Test overall status calculation for unhealthy"""
        checker = HealthChecker()
        results = {"check1": {"status": "healthy"}, "check2": {"status": "unhealthy"}}
        status = checker._get_overall_status(results)
        assert status == "unhealthy"

    def test_get_overall_status_unknown(self):
        """Test overall status calculation for unknown"""
        checker = HealthChecker()
        results = {"check1": {"status": "unknown"}, "check2": {"status": "healthy"}}
        status = checker._get_overall_status(results)
        assert status == "degraded"
