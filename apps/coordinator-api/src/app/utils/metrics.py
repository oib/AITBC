"""
Basic Metrics Collection Module
Collects and tracks system and application metrics for monitoring
"""

import os
import resource
from datetime import datetime
from typing import Any

from aitbc import get_logger

logger = get_logger(__name__)


class MetricsCollector:
    """Basic metrics collection for system and application monitoring"""
    
    def __init__(self):
        self._metrics: dict[str, Any] = {
            "api_requests": 0,
            "api_errors": 0,
            "api_response_times": [],
            "database_queries": 0,
            "database_errors": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "active_connections": 0,
            "memory_usage_mb": 0,
            "cpu_usage_percent": 0.0,
        }
        self._start_time = datetime.utcnow()
    
    def increment_api_requests(self) -> None:
        """Increment API request counter"""
        self._metrics["api_requests"] += 1
    
    def increment_api_errors(self) -> None:
        """Increment API error counter"""
        self._metrics["api_errors"] += 1
    
    def record_api_response_time(self, response_time: float) -> None:
        """Record API response time"""
        self._metrics["api_response_times"].append(response_time)
        # Keep only last 100 response times
        if len(self._metrics["api_response_times"]) > 100:
            self._metrics["api_response_times"] = self._metrics["api_response_times"][-100:]
    
    def increment_database_queries(self) -> None:
        """Increment database query counter"""
        self._metrics["database_queries"] += 1
    
    def increment_database_errors(self) -> None:
        """Increment database error counter"""
        self._metrics["database_errors"] += 1
    
    def increment_cache_hits(self) -> None:
        """Increment cache hit counter"""
        self._metrics["cache_hits"] += 1
    
    def increment_cache_misses(self) -> None:
        """Increment cache miss counter"""
        self._metrics["cache_misses"] += 1
    
    def update_active_connections(self, count: int) -> None:
        """Update active connections count"""
        self._metrics["active_connections"] = count
    
    def update_memory_usage(self, usage_mb: float) -> None:
        """Update memory usage"""
        self._metrics["memory_usage_mb"] = usage_mb
    
    def update_cpu_usage(self, usage_percent: float) -> None:
        """Update CPU usage percentage"""
        self._metrics["cpu_usage_percent"] = usage_percent
    
    def update_cache_stats(self, cache_stats: dict[str, Any]) -> None:
        """Update cache metrics from cache manager stats"""
        self._metrics["cache_hits"] = cache_stats.get("hits", 0)
        self._metrics["cache_misses"] = cache_stats.get("misses", 0)
    
    def capture_system_snapshot(self) -> None:
        """Capture a lightweight system resource snapshot"""
        memory_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        self._metrics["memory_usage_mb"] = round(memory_kb / 1024, 2)
        load_average = os.getloadavg()[0] if hasattr(os, "getloadavg") else 0.0
        cpu_estimate = min(round(load_average * 100, 2), 100.0)
        self._metrics["cpu_usage_percent"] = cpu_estimate
    
    def get_metrics(self) -> dict[str, Any]:
        """Get current metrics"""
        self.capture_system_snapshot()
        avg_response_time = 0.0
        if self._metrics["api_response_times"]:
            avg_response_time = sum(self._metrics["api_response_times"]) / len(self._metrics["api_response_times"])
        
        cache_hit_rate = 0.0
        total_cache_ops = self._metrics["cache_hits"] + self._metrics["cache_misses"]
        if total_cache_ops > 0:
            cache_hit_rate = (self._metrics["cache_hits"] / total_cache_ops) * 100
        
        error_rate = 0.0
        if self._metrics["api_requests"] > 0:
            error_rate = (self._metrics["api_errors"] / self._metrics["api_requests"]) * 100
        
        uptime_seconds = (datetime.utcnow() - self._start_time).total_seconds()
        
        return {
            **self._metrics,
            "avg_response_time_ms": avg_response_time * 1000,
            "cache_hit_rate_percent": cache_hit_rate,
            "error_rate_percent": error_rate,
            "alerts": self.get_alert_states(),
            "uptime_seconds": uptime_seconds,
            "uptime_formatted": self._format_uptime(uptime_seconds),
            "timestamp": datetime.utcnow().isoformat(),
        }
    
    def _format_uptime(self, seconds: float) -> str:
        """Format uptime in human-readable format"""
        days = int(seconds // 86400)
        hours = int((seconds % 86400) // 3600)
        minutes = int((seconds % 3600) // 60)
        return f"{days}d {hours}h {minutes}m"
    
    def get_alert_states(self) -> dict[str, dict[str, str | float | bool]]:
        """Evaluate alert thresholds for key metrics"""
        avg_response_time_ms = 0.0
        if self._metrics["api_response_times"]:
            avg_response_time_ms = (sum(self._metrics["api_response_times"]) / len(self._metrics["api_response_times"])) * 1000
        
        total_cache_ops = self._metrics["cache_hits"] + self._metrics["cache_misses"]
        cache_hit_rate = (self._metrics["cache_hits"] / total_cache_ops * 100) if total_cache_ops > 0 else 0.0
        error_rate = (self._metrics["api_errors"] / self._metrics["api_requests"] * 100) if self._metrics["api_requests"] > 0 else 0.0
        memory_percent_estimate = min((self._metrics["memory_usage_mb"] / 1024) * 100, 100.0)
        
        return {
            "error_rate": {"triggered": error_rate > 1.0, "value": round(error_rate, 2), "threshold": 1.0, "status": "critical" if error_rate > 1.0 else "ok"},
            "avg_response_time": {"triggered": avg_response_time_ms > 500.0, "value": round(avg_response_time_ms, 2), "threshold": 500.0, "status": "critical" if avg_response_time_ms > 500.0 else "ok"},
            "memory_usage": {"triggered": memory_percent_estimate > 90.0, "value": round(memory_percent_estimate, 2), "threshold": 90.0, "status": "critical" if memory_percent_estimate > 90.0 else "ok"},
            "cache_hit_rate": {"triggered": total_cache_ops > 0 and cache_hit_rate < 70.0, "value": round(cache_hit_rate, 2), "threshold": 70.0, "status": "critical" if total_cache_ops > 0 and cache_hit_rate < 70.0 else "ok"},
        }
    
    def reset_metrics(self) -> None:
        """Reset all metrics"""
        self._metrics = {
            "api_requests": 0,
            "api_errors": 0,
            "api_response_times": [],
            "database_queries": 0,
            "database_errors": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "active_connections": 0,
            "memory_usage_mb": 0,
            "cpu_usage_percent": 0.0,
        }
        self._start_time = datetime.utcnow()


# Global metrics collector instance
metrics_collector = MetricsCollector()

def build_live_metrics_payload(
    cache_stats: dict[str, Any],
    dispatcher: Any | None = None,
    collector: MetricsCollector | None = None,
) -> dict[str, Any]:
    active_collector = collector or metrics_collector
    active_collector.update_cache_stats(cache_stats)
    metrics = active_collector.get_metrics()
    if dispatcher is not None:
        metrics["alert_delivery"] = dispatcher.dispatch(metrics.get("alerts", {}))
    return metrics

def get_metrics() -> dict[str, Any]:
    """Get current metrics from global collector"""
    return metrics_collector.get_metrics()

def reset_metrics() -> None:
    """Reset global metrics collector"""
    metrics_collector.reset_metrics()
