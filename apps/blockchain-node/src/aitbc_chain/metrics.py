from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

# Block Processing Metrics
block_processing_duration = Histogram(
    "blockchain_block_processing_duration_seconds", "Time to process a block", buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
)

block_height = Gauge("blockchain_block_height", "Current blockchain height")

block_validation_duration = Histogram(
    "blockchain_block_validation_duration_seconds", "Time to validate a block", buckets=[0.01, 0.05, 0.1, 0.5, 1.0]
)

block_propagation_duration = Histogram(
    "blockchain_block_propagation_duration_seconds", "Time to propagate block to peers", buckets=[0.1, 0.5, 1.0, 2.0, 5.0]
)

# Transaction Metrics
transaction_processing_duration = Histogram(
    "blockchain_transaction_processing_duration_seconds",
    "Time to process a transaction",
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1],
)

transactions_total = Counter("blockchain_transactions_total", "Total number of transactions processed", ["status"])

# Sync Metrics
sync_duration = Histogram("blockchain_sync_duration_seconds", "Time to sync blockchain", buckets=[1.0, 5.0, 10.0, 30.0, 60.0])

sync_blocks_imported = Counter("blockchain_sync_blocks_imported_total", "Total number of blocks imported during sync")

# RPC Metrics
rpc_request_duration = Histogram(
    "blockchain_rpc_request_duration_seconds", "RPC request duration", buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0]
)

rpc_requests_total = Counter("blockchain_rpc_requests_total", "Total RPC requests", ["method", "status"])

# Legacy MetricsRegistry for backward compatibility
from dataclasses import dataclass
from threading import Lock


@dataclass
class MetricValue:
    name: str
    value: float


class MetricsRegistry:
    def __init__(self) -> None:
        self._counters: dict[str, float] = {}
        self._gauges: dict[str, float] = {}
        self._summaries: dict[str, tuple[float, float]] = {}
        self._lock = Lock()

    def increment(self, name: str, amount: float = 1.0) -> None:
        with self._lock:
            self._counters[name] = self._counters.get(name, 0.0) + amount

    def set_gauge(self, name: str, value: float) -> None:
        with self._lock:
            self._gauges[name] = value

    def observe(self, name: str, value: float) -> None:
        with self._lock:
            count, total = self._summaries.get(name, (0.0, 0.0))
            self._summaries[name] = (count + 1.0, total + value)

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._summaries.clear()

    def render_prometheus(self) -> str:
        with self._lock:
            lines: list[str] = []
            for name, value in sorted(self._counters.items()):
                lines.append(f"# TYPE {name} counter")
                lines.append(f"{name} {value}")
            for name, value in sorted(self._gauges.items()):
                lines.append(f"# TYPE {name} gauge")
                lines.append(f"{name} {value}")
            for name, (count, total) in sorted(self._summaries.items()):
                lines.append(f"# TYPE {name} summary")
                lines.append(f"{name}_count {count}")
                lines.append(f"{name}_sum {total}")
            return "\n".join(lines) + "\n"


metrics_registry = MetricsRegistry()
