"""
Cache metrics tracking for performance monitoring.
"""

from typing import Any

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)


class CacheMetrics:
    """Track cache performance metrics"""
    
    def __init__(self):
        self.total_requests = 0
        self.total_hits = 0
        self.total_misses = 0
        self.total_errors = 0
        self.operation_times = []
        self.cache_operations = {}
    
    def record_hit(self, operation: str, duration_ms: float) -> None:
        """Record a cache hit"""
        self.total_requests += 1
        self.total_hits += 1
        self._record_operation(operation, duration_ms, "hit")
    
    def record_miss(self, operation: str, duration_ms: float) -> None:
        """Record a cache miss"""
        self.total_requests += 1
        self.total_misses += 1
        self._record_operation(operation, duration_ms, "miss")
    
    def record_error(self, operation: str, duration_ms: float) -> None:
        """Record a cache error"""
        self.total_requests += 1
        self.total_errors += 1
        self._record_operation(operation, duration_ms, "error")
    
    def _record_operation(self, operation: str, duration_ms: float, result: str) -> None:
        """Record individual operation details"""
        if operation not in self.cache_operations:
            self.cache_operations[operation] = {
                "hits": 0,
                "misses": 0,
                "errors": 0,
                "total": 0,
                "avg_duration_ms": []
            }
        
        op_stats = self.cache_operations[operation]
        op_stats["total"] += 1
        # Use the correct field name based on result
        if result == "hit":
            op_stats["hits"] += 1
        elif result == "miss":
            op_stats["misses"] += 1
        elif result == "error":
            op_stats["errors"] += 1
        op_stats["avg_duration_ms"].append(duration_ms)
        
        # Keep only last 100 duration measurements
        if len(op_stats["avg_duration_ms"]) > 100:
            op_stats["avg_duration_ms"] = op_stats["avg_duration_ms"][-100:]
    
    def get_stats(self) -> dict[str, Any]:
        """Get cache performance statistics"""
        hit_rate = self.total_hits / self.total_requests if self.total_requests > 0 else 0
        miss_rate = self.total_misses / self.total_requests if self.total_requests > 0 else 0
        error_rate = self.total_errors / self.total_requests if self.total_requests > 0 else 0
        
        # Calculate average durations per operation
        operation_stats = {}
        for op, stats in self.cache_operations.items():
            avg_duration = sum(stats["avg_duration_ms"]) / len(stats["avg_duration_ms"]) if stats["avg_duration_ms"] else 0
            operation_stats[op] = {
                "hits": stats["hits"],
                "misses": stats["misses"],
                "errors": stats["errors"],
                "total": stats["total"],
                "hit_rate": stats["hits"] / stats["total"] if stats["total"] > 0 else 0,
                "avg_duration_ms": avg_duration
            }
        
        return {
            "total_requests": self.total_requests,
            "total_hits": self.total_hits,
            "total_misses": self.total_misses,
            "total_errors": self.total_errors,
            "hit_rate": hit_rate,
            "miss_rate": miss_rate,
            "error_rate": error_rate,
            "operation_stats": operation_stats
        }
    
    def reset(self) -> None:
        """Reset all metrics"""
        self.total_requests = 0
        self.total_hits = 0
        self.total_misses = 0
        self.total_errors = 0
        self.operation_times = []
        self.cache_operations = {}


# Global cache metrics instance
_global_metrics: CacheMetrics | None = None


def get_cache_metrics() -> CacheMetrics:
    """
    Get global cache metrics instance
    
    Returns:
        CacheMetrics instance
    """
    global _global_metrics
    if _global_metrics is None:
        _global_metrics = CacheMetrics()
    return _global_metrics
