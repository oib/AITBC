"""
Query performance monitoring for AITBC database operations.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)


@dataclass
class QueryMetrics:
    """Query performance metrics"""

    query: str
    execution_time_ms: float
    timestamp: datetime
    success: bool
    error_message: str | None = None
    row_count: int = 0


@dataclass
class DatabaseMetrics:
    """Database performance metrics"""

    total_queries: int = 0
    total_errors: int = 0
    avg_execution_time_ms: float = 0.0
    slow_queries: list[QueryMetrics] = field(default_factory=list)
    recent_queries: list[QueryMetrics] = field(default_factory=list)

    def add_query(self, metrics: QueryMetrics, slow_threshold_ms: float = 1000.0):
        """Add query metrics"""
        self.total_queries += 1
        if not metrics.success:
            self.total_errors += 1
        total_time = self.avg_execution_time_ms * (self.total_queries - 1) + metrics.execution_time_ms
        self.avg_execution_time_ms = total_time / self.total_queries
        if metrics.execution_time_ms > slow_threshold_ms:
            self.slow_queries.append(metrics)
        self.recent_queries.append(metrics)
        if len(self.recent_queries) > 100:
            self.recent_queries.pop(0)


class QueryMonitor:
    """Query performance monitoring and logging"""

    def __init__(self, slow_query_threshold_ms: float = 1000.0, enable_logging: bool = True):
        """
        Initialize query monitor

        Args:
            slow_query_threshold_ms: Threshold for slow query detection
            enable_logging: Enable query logging
        """
        self.slow_query_threshold_ms = slow_query_threshold_ms
        self.enable_logging = enable_logging
        self.metrics = DatabaseMetrics()
        self.query_counts = defaultdict(int)

    def record_query(
        self, query: str, execution_time_ms: float, success: bool = True, error_message: str | None = None, row_count: int = 0
    ) -> None:
        """
        Record query execution metrics

        Args:
            query: SQL query string
            execution_time_ms: Execution time in milliseconds
            success: Whether query succeeded
            error_message: Error message if failed
            row_count: Number of rows affected/returned
        """
        query_metrics = QueryMetrics(
            query=query,
            execution_time_ms=execution_time_ms,
            timestamp=datetime.now(UTC),
            success=success,
            error_message=error_message,
            row_count=row_count,
        )
        self.metrics.add_query(query_metrics, self.slow_query_threshold_ms)
        self.query_counts[query] += 1
        if self.enable_logging:
            if not success:
                logger.error("Query failed: %s", error_message)
            elif execution_time_ms > self.slow_query_threshold_ms:
                logger.warning("Slow query (%sms): %s", execution_time_ms, query[:100])

    def get_stats(self) -> dict[str, Any]:
        """
        Get monitoring statistics

        Returns:
            Dictionary of statistics
        """
        return {
            "total_queries": self.metrics.total_queries,
            "total_errors": self.metrics.total_errors,
            "avg_execution_time_ms": self.metrics.avg_execution_time_ms,
            "slow_query_count": len(self.metrics.slow_queries),
            "error_rate": self.metrics.total_errors / self.metrics.total_queries if self.metrics.total_queries > 0 else 0,
            "unique_queries": len(self.query_counts),
        }

    def get_slow_queries(self, limit: int = 10) -> list[QueryMetrics]:
        """
        Get slow queries

        Args:
            limit: Maximum number of slow queries to return

        Returns:
            List of slow query metrics
        """
        return self.metrics.slow_queries[-limit:]

    def get_top_queries(self, limit: int = 10) -> list[tuple[str, int]]:
        """Get most frequently executed queries"""
        return sorted(self.query_counts.items(), key=lambda x: x[1], reverse=True)[:limit]

    def reset(self) -> None:
        """Reset all metrics"""
        self.metrics = DatabaseMetrics()
        self.query_counts = defaultdict(int)
