"""
AITBC Monitoring and Metrics Utilities
Monitoring and metrics collection for AITBC applications
"""

import time
from typing import Dict, Any, Optional
from collections import defaultdict
from datetime import datetime, timedelta


class MetricsCollector:
    """
    Simple in-memory metrics collector for AITBC applications.
    Tracks counters, timers, and gauges.
    """
    
    def __init__(self):
        """Initialize metrics collector."""
        self.counters: Dict[str, int] = defaultdict(int)
        self.timers: Dict[str, list] = defaultdict(list)
        self.gauges: Dict[str, float] = {}
        self.timestamps: Dict[str, datetime] = {}
    
    def increment(self, metric: str, value: int = 1) -> None:
        """
        Increment a counter metric.
        
        Args:
            metric: Metric name
            value: Value to increment by
        """
        self.counters[metric] += value
        self.timestamps[metric] = datetime.now()
    
    def decrement(self, metric: str, value: int = 1) -> None:
        """
        Decrement a counter metric.
        
        Args:
            metric: Metric name
            value: Value to decrement by
        """
        self.counters[metric] -= value
        self.timestamps[metric] = datetime.now()
    
    def timing(self, metric: str, duration: float) -> None:
        """
        Record a timing metric.
        
        Args:
            metric: Metric name
            duration: Duration in seconds
        """
        self.timers[metric].append(duration)
        self.timestamps[metric] = datetime.now()
    
    def set_gauge(self, metric: str, value: float) -> None:
        """
        Set a gauge metric.
        
        Args:
            metric: Metric name
            value: Gauge value
        """
        self.gauges[metric] = value
        self.timestamps[metric] = datetime.now()
    
    def get_counter(self, metric: str) -> int:
        """
        Get counter value.
        
        Args:
            metric: Metric name
            
        Returns:
            Counter value
        """
        return self.counters.get(metric, 0)
    
    def get_timer_stats(self, metric: str) -> Dict[str, float]:
        """
        Get timer statistics for a metric.
        
        Args:
            metric: Metric name
            
        Returns:
            Dictionary with min, max, avg, count
        """
        timings = self.timers.get(metric, [])
        if not timings:
            return {"min": 0, "max": 0, "avg": 0, "count": 0}
        
        return {
            "min": min(timings),
            "max": max(timings),
            "avg": sum(timings) / len(timings),
            "count": len(timings)
        }
    
    def get_gauge(self, metric: str) -> Optional[float]:
        """
        Get gauge value.
        
        Args:
            metric: Metric name
            
        Returns:
            Gauge value or None
        """
        return self.gauges.get(metric)
    
    def get_all_metrics(self) -> Dict[str, Any]:
        """
        Get all collected metrics.
        
        Returns:
            Dictionary of all metrics
        """
        return {
            "counters": dict(self.counters),
            "timers": {k: self.get_timer_stats(k) for k in self.timers},
            "gauges": dict(self.gauges),
            "timestamps": {k: v.isoformat() for k, v in self.timestamps.items()}
        }
    
    def reset_metric(self, metric: str) -> None:
        """
        Reset a specific metric.
        
        Args:
            metric: Metric name
        """
        if metric in self.counters:
            del self.counters[metric]
        if metric in self.timers:
            del self.timers[metric]
        if metric in self.gauges:
            del self.gauges[metric]
        if metric in self.timestamps:
            del self.timestamps[metric]
    
    def reset_all(self) -> None:
        """Reset all metrics."""
        self.counters.clear()
        self.timers.clear()
        self.gauges.clear()
        self.timestamps.clear()


class PerformanceTimer:
    """
    Context manager for timing operations.
    """
    
    def __init__(self, collector: MetricsCollector, metric: str):
        """
        Initialize timer.
        
        Args:
            collector: MetricsCollector instance
            metric: Metric name
        """
        self.collector = collector
        self.metric = metric
        self.start_time = None
    
    def __enter__(self):
        """Start timing."""
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Stop timing and record metric."""
        if self.start_time:
            duration = time.time() - self.start_time
            self.collector.timing(self.metric, duration)


class HealthChecker:
    """
    Health check utilities for AITBC applications.
    """
    
    def __init__(self):
        """Initialize health checker."""
        self.checks: Dict[str, Any] = {}
        self.last_check: Optional[datetime] = None
    
    def add_check(self, name: str, check_func: callable) -> None:
        """
        Add a health check.
        
        Args:
            name: Check name
            check_func: Function that returns (status, message)
        """
        self.checks[name] = check_func
    
    def run_check(self, name: str) -> Dict[str, Any]:
        """
        Run a specific health check.
        
        Args:
            name: Check name
            
        Returns:
            Check result with status and message
        """
        if name not in self.checks:
            return {"status": "unknown", "message": f"Check '{name}' not found"}
        
        try:
            status, message = self.checks[name]()
            return {"status": status, "message": message}
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    def run_all_checks(self) -> Dict[str, Any]:
        """
        Run all health checks.
        
        Returns:
            Dictionary of all check results
        """
        self.last_check = datetime.now()
        results = {}
        
        for name in self.checks:
            results[name] = self.run_check(name)
        
        return {
            "checks": results,
            "overall_status": self._get_overall_status(results),
            "timestamp": self.last_check.isoformat()
        }
    
    def _get_overall_status(self, results: Dict[str, Any]) -> str:
        """
        Determine overall health status.
        
        Args:
            results: Check results
            
        Returns:
            Overall status (healthy, degraded, unhealthy)
        """
        if not results:
            return "unknown"
        
        statuses = [r.get("status", "unknown") for r in results.values()]
        
        if all(s == "healthy" for s in statuses):
            return "healthy"
        elif any(s == "unhealthy" for s in statuses):
            return "unhealthy"
        else:
            return "degraded"
