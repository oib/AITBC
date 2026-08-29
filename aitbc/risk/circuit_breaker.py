"""Market-stress circuit breakers for autonomous actions (v0.13.0 §A3).

Provides a simple state-machine circuit breaker that opens when market-stress
metrics exceed a threshold, protecting automated rebalancing, reinvestment, and
staking operations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Any


class CircuitState(StrEnum):
    """Circuit breaker states."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class MarketStressEvent:
    """A single market-stress observation.

    ``severity`` is a 0–1 value; ``stress_score`` is the 0–100 equivalent.
    If ``stress_score`` is not supplied, it is derived from ``severity``.
    """

    event_id: str = ""
    metric: str = ""
    severity: Decimal = Decimal("0")
    stress_score: Decimal | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.stress_score is None:
            self.stress_score = self.severity * Decimal("100")
        if not (Decimal("0") <= self.stress_score <= Decimal("100")):
            raise ValueError("stress_score must be between 0 and 100")

    @property
    def effective_stress_score(self) -> Decimal:
        """Return the 0–100 stress score, computing from severity if needed."""
        if self.stress_score is not None:
            return self.stress_score
        return self.severity * Decimal("100")


@dataclass
class CircuitBreaker:
    """Circuit breaker for autonomous economic actions.

    ``threshold`` may be supplied as a 0–1 fraction or a 0–100 percentage.
    ``stress_score`` values from ``MarketStressEvent`` are normalized to 0–100.

    - ``CLOSED``: actions allowed; failures open the breaker.
    - ``OPEN``: actions blocked until ``recovery_timeout`` passes.
    - ``HALF_OPEN``: a limited number of probes are allowed.
    """

    name: str
    threshold: Decimal
    recovery_timeout: timedelta = field(default_factory=lambda: timedelta(minutes=5))
    half_open_max_calls: int = 1
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    last_state_change: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_failure_time: datetime | None = None
    half_open_calls: int = 0
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.threshold < 0 or self.threshold > 100:
            raise ValueError("threshold must be between 0 and 100")
        if self.half_open_max_calls < 1:
            raise ValueError("half_open_max_calls must be at least 1")

    @property
    def _effective_threshold(self) -> Decimal:
        """Normalize threshold to a 0–100 scale."""
        # Thresholds <= 1 are treated as fractions; >1 as percentages.
        if self.threshold <= 1:
            return self.threshold * Decimal("100")
        return self.threshold

    def is_open(self) -> bool:
        """Return True when the breaker is open."""
        return self.state == CircuitState.OPEN

    def can_execute(self, now: datetime | None = None) -> bool:
        """Return True if an autonomous action may run."""
        if now is None:
            now = datetime.now(UTC)

        if self.state == CircuitState.CLOSED:
            return True

        if self.state == CircuitState.OPEN:
            if self.last_failure_time is None:
                # Should not happen; reset to closed
                self._transition(CircuitState.CLOSED, now)
                return True
            if now - self.last_failure_time >= self.recovery_timeout:
                self._transition(CircuitState.HALF_OPEN, now)
                self.half_open_calls = 0
                return True
            return False

        # HALF_OPEN
        return self.half_open_calls < self.half_open_max_calls

    def record(self, event: MarketStressEvent, now: datetime | None = None) -> None:
        """Record a market-stress event and update breaker state."""
        if now is None:
            now = datetime.now(UTC)

        score = event.effective_stress_score
        if self.state == CircuitState.HALF_OPEN:
            self.half_open_calls += 1
            if score >= self._effective_threshold:
                self._open(now)
            elif self.half_open_calls >= self.half_open_max_calls:
                self._transition(CircuitState.CLOSED, now)
            return

        if self.state == CircuitState.CLOSED:
            if score >= self._effective_threshold:
                self.failure_count += 1
                self._open(now)
            else:
                self.failure_count = 0
            return

        # OPEN: keep open until timeout; event does not change state
        if score >= self._effective_threshold:
            self.last_failure_time = now

    def _open(self, now: datetime) -> None:
        self.last_failure_time = now
        self._transition(CircuitState.OPEN, now)

    def _transition(self, state: CircuitState, now: datetime) -> None:
        self.state = state
        self.last_state_change = now
        if state == CircuitState.CLOSED:
            self.failure_count = 0
            self.half_open_calls = 0
