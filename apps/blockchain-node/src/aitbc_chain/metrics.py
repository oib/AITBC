from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Dict


@dataclass
class MetricValue:
    name: str
    value: float


class MetricsRegistry:
    def __init__(self) -> None:
        self._counters: Dict[str, float] = {}
        self._gauges: Dict[str, float] = {}
        self._summaries: Dict[str, tuple[float, float]] = {}
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
