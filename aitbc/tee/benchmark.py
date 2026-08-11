"""TEE latency/cost benchmarking utilities (v0.14.2 §A1).

ponytail: This is a simulator-friendly benchmark harness. Production should
collect real attestation and enclave execution metrics from the platform.
"""

from __future__ import annotations

import tracemalloc
from collections.abc import Callable
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any


@dataclass
class TEEBenchmarkResult:
    """Result of a single benchmark run."""

    name: str
    latency_ms: float
    # not-money: a synthetic benchmark metric alongside latency_ms and memory_bytes
    cost_units: float = 0.0
    memory_bytes: int = 0
    meta: dict[str, Any] = field(default_factory=dict)


class TEEBenchmark:
    """Simple harness for timing TEE operations."""

    def __init__(self, name: str = "tee-benchmark") -> None:
        self.name = name
        self.results: list[TEEBenchmarkResult] = []

    def run(
        self,
        operation_name: str,
        fn: Callable[..., Any],
        *args: Any,
        # not-money: the synthetic benchmark metric recorded on TEEBenchmarkResult
        cost_units: float = 0.0,
        **kwargs: Any,
    ) -> TEEBenchmarkResult:
        """Run a callable and record wall-clock latency and peak memory."""
        tracemalloc.start()
        start = perf_counter()
        fn(*args, **kwargs)
        elapsed_ms = (perf_counter() - start) * 1000
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        result = TEEBenchmarkResult(
            name=operation_name,
            latency_ms=elapsed_ms,
            cost_units=cost_units,
            memory_bytes=int(peak),
        )
        self.results.append(result)
        return result

    def summary(self) -> dict[str, float]:
        """Return aggregate latency and throughput statistics."""
        if not self.results:
            return {
                "count": 0.0,
                "total_ms": 0.0,
                "avg_ms": 0.0,
                "min_ms": 0.0,
                "max_ms": 0.0,
                "ops_per_sec": 0.0,
                "peak_memory_bytes": 0.0,
            }
        latencies = [r.latency_ms for r in self.results]
        total = sum(latencies)
        avg = total / len(latencies)
        # Avoid division by zero for instantaneous runs.
        ops_per_sec = 1000.0 / avg if avg > 0 else 0.0
        peak_memory = max(r.memory_bytes for r in self.results)
        return {
            "count": float(len(self.results)),
            "total_ms": total,
            "avg_ms": avg,
            "min_ms": min(latencies),
            "max_ms": max(latencies),
            "ops_per_sec": ops_per_sec,
            "peak_memory_bytes": float(peak_memory),
        }
