"""
Unit tests for coordinator API metrics collection and alert delivery.
Tests MetricsCollector, AlertDispatcher, and build_live_metrics_payload
without requiring full app startup or database.
import sys
"""

import asyncio
from unittest.mock import patch

import pytest

from app.utils.alerting import AlertDispatcher
from app.utils.metrics import MetricsCollector, build_live_metrics_payload


class TestMetricsCollector:
    """Test MetricsCollector behavior and alert threshold evaluation."""

    def test_metrics_collector_initial_state(self):
        """Verify collector starts with zeroed metrics."""
        collector = MetricsCollector()
        metrics = collector.get_metrics()
        assert metrics["api_requests"] == 0
        assert metrics["api_errors"] == 0
        assert metrics["cache_hits"] == 0
        assert metrics["cache_misses"] == 0
        assert metrics["database_queries"] == 0
        assert metrics["database_errors"] == 0

    def test_metrics_collector_records_api_metrics(self):
        """Verify API request, error, and response time tracking."""
        collector = MetricsCollector()
        collector.record_api_request(error=False, response_time_ms=100.0)
        collector.record_api_request(error=True, response_time_ms=200.0)
        collector.record_api_request(error=False, response_time_ms=50.0)

        metrics = collector.get_metrics()
        assert metrics["api_requests"] == 3
        assert metrics["api_errors"] == 1
        assert len(metrics["api_response_times"]) == 3
        assert sum(metrics["api_response_times"]) == 0.35

    def test_metrics_collector_calculates_error_rate(self):
        """Verify error rate percentage calculation."""
        collector = MetricsCollector()
        for _ in range(10):
            collector.record_api_request(error=False, response_time_ms=100.0)
        collector.record_api_request(error=True, response_time_ms=100.0)

        metrics = collector.get_metrics()
        assert metrics["error_rate_percent"] == pytest.approx(9.09, rel=0.01)

    def test_metrics_collector_calculates_avg_response_time(self):
        """Verify average response time calculation."""
        collector = MetricsCollector()
        collector.record_api_request(error=False, response_time_ms=100.0)
        collector.record_api_request(error=False, response_time_ms=200.0)

        metrics = collector.get_metrics()
        assert metrics["avg_response_time_ms"] == 150.0

    def test_metrics_collector_cache_hit_rate(self):
        """Verify cache hit rate calculation."""
        collector = MetricsCollector()
        collector.update_cache_stats({"hits": 7, "misses": 3})

        metrics = collector.get_metrics()
        assert metrics["cache_hit_rate_percent"] == 70.0

    def test_metrics_collector_alert_thresholds(self):
        """Verify alert threshold evaluation for error rate and response time."""
        collector = MetricsCollector()

        collector.record_api_request(error=False, response_time_ms=100.0)
        alerts = collector.get_alert_states()
        assert alerts["error_rate"]["triggered"] is False
        assert alerts["avg_response_time"]["triggered"] is False

        for _ in range(20):
            collector.record_api_request(error=True, response_time_ms=100.0)

        alerts = collector.get_alert_states()
        assert alerts["error_rate"]["triggered"] is True
        assert alerts["error_rate"]["value"] > 1.0

    def test_metrics_collector_reset(self):
        """Verify metrics can be reset to initial state."""
        collector = MetricsCollector()
        collector.record_api_request(error=False, response_time_ms=100.0)
        collector.record_database_query(error=False)
        collector.update_cache_stats({"hits": 5, "misses": 5})

        collector.reset_metrics()
        metrics = collector.get_metrics()
        assert metrics["api_requests"] == 0
        assert metrics["database_queries"] == 0
        assert metrics["cache_hits"] == 0
        assert metrics["cache_misses"] == 0


class TestAlertDispatcher:
    """Test AlertDispatcher cooldown suppression and history recording."""

    def test_alert_dispatcher_initial_state(self):
        """Verify dispatcher starts with empty history and no last sent timestamps."""
        dispatcher = AlertDispatcher(cooldown_seconds=300)
        assert len(dispatcher.get_recent_alerts()) == 0

    def test_alert_dispatcher_records_history(self):
        """Verify dispatched alerts are recorded in history."""
        dispatcher = AlertDispatcher(cooldown_seconds=0)
        alerts = {
            "test_alert": {"triggered": True, "status": "critical", "value": 95.0, "threshold": 90.0}
        }
        dispatcher.dispatch(alerts)

        history = dispatcher.get_recent_alerts()
        assert len(history) == 1
        assert history[0]["severity"] == "critical"
        assert history[0]["delivery_status"] == "sent"

    def test_alert_dispatcher_cooldown_suppression(self):
        """Verify alerts are suppressed during cooldown period."""
        dispatcher = AlertDispatcher(cooldown_seconds=10)
        alerts = {
            "test_alert": {"triggered": True, "status": "critical", "value": 95.0, "threshold": 90.0}
        }

        result1 = dispatcher.dispatch(alerts)
        assert result1["triggered_count"] == 1
        assert len(result1["sent"]) == 1
        assert len(result1["suppressed"]) == 0

        result2 = dispatcher.dispatch(alerts)
        assert result2["triggered_count"] == 1
        assert len(result2["sent"]) == 0
        assert len(result2["suppressed"]) == 1

    def test_alert_dispatcher_history_filter_by_severity(self):
        """Verify history can be filtered by severity."""
        dispatcher = AlertDispatcher(cooldown_seconds=0)

        dispatcher.dispatch({"alert1": {"triggered": True, "status": "critical", "value": 95.0, "threshold": 90.0}})
        dispatcher.dispatch({"alert2": {"triggered": True, "status": "warning", "value": 85.0, "threshold": 80.0}})

        critical_alerts = dispatcher.get_recent_alerts(severity="critical")
        warning_alerts = dispatcher.get_recent_alerts(severity="warning")

        assert len(critical_alerts) == 1
        assert len(warning_alerts) == 1
        assert critical_alerts[0]["severity"] == "critical"
        assert warning_alerts[0]["severity"] == "warning"

    def test_alert_dispatcher_history_limit(self):
        """Verify history respects the limit parameter."""
        dispatcher = AlertDispatcher(cooldown_seconds=0, max_history=10)

        for i in range(5):
            dispatcher.dispatch({f"alert{i}": {"triggered": True, "status": "critical", "value": 95.0, "threshold": 90.0}})

        assert len(dispatcher.get_recent_alerts(limit=3)) == 3
        assert len(dispatcher.get_recent_alerts(limit=10)) == 5

    def test_alert_dispatcher_reset_history(self):
        """Verify history can be cleared."""
        dispatcher = AlertDispatcher(cooldown_seconds=0)
        dispatcher.dispatch({"alert1": {"triggered": True, "status": "critical", "value": 95.0, "threshold": 90.0}})

        dispatcher.reset_history()
        assert len(dispatcher.get_recent_alerts()) == 0

    @patch.dict("os.environ", {}, clear=True)
    def test_alert_dispatcher_log_fallback(self):
        """Verify alert falls back to log when webhook URL is not configured."""
        dispatcher = AlertDispatcher(cooldown_seconds=0)
        alerts = {"test_alert": {"triggered": True, "status": "critical", "value": 95.0, "threshold": 90.0}}

        result = dispatcher.dispatch(alerts)
        assert result["channel"] == "log"
        assert len(result["sent"]) == 1


class TestBuildLiveMetricsPayload:
    """Test the shared metrics payload builder used by /v1/metrics endpoint."""

    def test_build_live_metrics_payload_basic(self):
        """Verify payload builder returns metrics with cache stats."""
        collector = MetricsCollector()
        cache_stats = {"hits": 8, "misses": 2}

        payload = build_live_metrics_payload(cache_stats=cache_stats, collector=collector)

        assert "cache_hits" in payload
        assert "cache_misses" in payload
        assert payload["cache_hits"] == 8
        assert payload["cache_misses"] == 2
        assert payload["cache_hit_rate_percent"] == 80.0

    def test_build_live_metrics_payload_with_dispatcher(self):
        """Verify payload builder includes alert delivery results when dispatcher is provided."""
        collector = MetricsCollector()
        dispatcher = AlertDispatcher(cooldown_seconds=0)
        cache_stats = {"hits": 5, "misses": 5}

        payload = build_live_metrics_payload(cache_stats=cache_stats, dispatcher=dispatcher, collector=collector)

        assert "alert_delivery" in payload
        assert "triggered_count" in payload["alert_delivery"]
        assert "channel" in payload["alert_delivery"]

    def test_build_live_metrics_payload_uses_global_collector(self):
        """Verify payload builder uses global collector when none is provided."""
        cache_stats = {"hits": 3, "misses": 7}

        payload = build_live_metrics_payload(cache_stats=cache_stats)

        assert "cache_hit_rate_percent" in payload
        assert payload["cache_hit_rate_percent"] == 30.0
