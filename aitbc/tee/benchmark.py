"""TEE latency/cost benchmarking utilities (v0.14.2 §A1).

ponytail: This is a simulator-friendly benchmark harness. Production should
collect real attestation and enclave execution metrics from the platform.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter
from typing import Any


@dataclass
class TEEBenchmarkResult:
    """Result of a single benchmark run."""

    name: str
    latency_ms: float
    cost_units: float = 0.0
    meta: dict[str, Any] = field(default_factory=dict)


class TEEBenchmark:
    """Simple harness for timing TEE operations."""

    def __init__(self, name: str = "tee-benchmark") -> None:
        self.name = name
        self.results: list[TEEBenchmarkResult] = []

    def run(
        self,
        operation_name: str,
        fn: Any,
        *args: Any,
        cost_units: float = 0.0,
        **kwargs: Any,
    ) -> TEEBenchmarkResult:
        """Run a callable and record its wall-clock latency."""
        start = perf_counter()
        fn(*args, **kwargs)
        elapsed_ms = (perf_counter() - start) * 1000
        result = TEEBenchmarkResult(
            name=operation_name,
            latency_ms=elapsed_ms,
            cost_units=cost_units,
        )
        self.results.append(result)
        return result

    def summary(self) -> dict[str, float]:
        """Return aggregate latency statistics."""
        if not self.results:
            return {"count": 0.0, "total_ms": 0.0, "avg_ms": 0.0}
        total = sum(r.latency_ms for r in self.results)
        return {
            "count": float(len(self.results)),
            "total_ms": total,
            "avg_ms": total / len(self.results),
        }
