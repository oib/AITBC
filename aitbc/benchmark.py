"""
Benchmarking helpers for performance measurement.

Provides lightweight context managers and accumulators for timing
database queries, network transfers, and cache hit/miss ratios.
No external dependencies — uses only stdlib.
"""

import time
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)


@contextmanager
def timed(label: str) -> Generator[dict[str, float]]:
    """Context manager that measures elapsed time.

    Usage::

        with timed("block_import") as t:
            import_block(block_data)
        print(f"Took {t['elapsed_ms']:.1f}ms")

    Yields a dict that is populated with ``elapsed_ms`` and ``elapsed_s``
    after the context block exits.
    """
    result: dict[str, float] = {}
    start = time.perf_counter()
    try:
        yield result
    finally:
        elapsed = time.perf_counter() - start
        result["elapsed_s"] = elapsed
        result["elapsed_ms"] = elapsed * 1000.0
        logger.debug("%s: %.2fms", label, result["elapsed_ms"])


class QueryTimer:
    """Accumulates DB query timings across multiple calls.

    Usage::

        qt = QueryTimer()
        with qt.measure("get_block"):
            block = session.get(Block, 1)
        print(qt.summary())
    """

    def __init__(self) -> None:
        self._timings: dict[str, list[float]] = {}

    @contextmanager
    def measure(self, label: str) -> Generator[None]:
        start = time.perf_counter()
        try:
            yield
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            self._timings.setdefault(label, []).append(elapsed_ms)

    def summary(self) -> dict[str, dict[str, float]]:
        """Return per-label stats: count, total_ms, avg_ms, min_ms, max_ms, p95_ms."""
        result: dict[str, dict[str, float]] = {}
        for label, times in self._timings.items():
            sorted_times = sorted(times)
            n = len(sorted_times)
            p95_idx = int(n * 0.95) - 1 if n > 0 else 0
            result[label] = {
                "count": float(n),
                "total_ms": sum(times),
                "avg_ms": sum(times) / n if n else 0.0,
                "min_ms": min(times) if times else 0.0,
                "max_ms": max(times) if times else 0.0,
                "p95_ms": sorted_times[max(p95_idx, 0)] if sorted_times else 0.0,
            }
        return result

    def reset(self) -> None:
        self._timings.clear()


class CacheMetrics:
    """Tracks cache hit/miss counts and ratios.

    Usage::

        cm = CacheMetrics()
        cm.hit("block:1")
        cm.miss("block:2")
        print(cm.ratio())  # 0.5
    """

    def __init__(self) -> None:
        self._hits = 0
        self._misses = 0
        self._per_key: dict[str, bool] = {}

    def hit(self, key: str) -> None:
        self._hits += 1
        self._per_key[key] = True

    def miss(self, key: str) -> None:
        self._misses += 1
        self._per_key[key] = False

    @property
    def hits(self) -> int:
        return self._hits

    @property
    def misses(self) -> int:
        return self._misses

    @property
    def total(self) -> int:
        return self._hits + self._misses

    def ratio(self) -> float:
        """Hit ratio as 0.0–1.0."""
        t = self.total
        return self._hits / t if t > 0 else 0.0

    def summary(self) -> dict[str, Any]:
        return {
            "hits": self._hits,
            "misses": self._misses,
            "total": self.total,
            "hit_ratio": self.ratio(),
        }

    def reset(self) -> None:
        self._hits = 0
        self._misses = 0
        self._per_key.clear()
