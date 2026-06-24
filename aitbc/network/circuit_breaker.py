"""
Circuit breaker implementation for HTTP client
"""

from datetime import UTC, datetime
from typing import Any

from ..aitbc_logging import get_logger
from ..exceptions import CircuitBreakerOpenError

# Circuit breaker states
_CLOSED = "closed"  # Normal operation — all calls allowed
_OPEN = "open"  # Tripped — all calls blocked
_HALF_OPEN = "half_open"  # Probation — limited probe calls allowed


class CircuitBreaker:
    """Circuit breaker state machine for preventing cascading failures.

    States:
        closed    — Normal operation, all calls allowed.
        open      — Tripped, all calls blocked until timeout expires.
        half_open — Timeout expired, a single probe call is allowed.
                    If the probe succeeds → closed.
                    If the probe fails → reopens immediately.
    """

    def __init__(self, threshold: int = 5, timeout: int = 60):
        """
        Initialize circuit breaker.

        Args:
            threshold: Number of failures before opening circuit
            timeout: Seconds to wait before attempting to close circuit
        """
        self.threshold = threshold
        self.timeout = timeout
        self.failure_count = 0
        self.is_open = False
        self.open_time: datetime | None = None
        self._state = _CLOSED
        self.logger = get_logger(__name__)

    def check(self) -> None:
        """Check if circuit breaker is open and raise exception if so."""
        if self._state == _OPEN:
            if self.open_time and (datetime.now(UTC) - self.open_time).total_seconds() > self.timeout:
                # Timeout expired — transition to half-open for a probe call
                self._state = _HALF_OPEN
                self.is_open = False
                self.logger.info("Circuit breaker transitioned to half-open state")
            else:
                raise CircuitBreakerOpenError("Circuit breaker is open, rejecting request")
        elif self._state == _HALF_OPEN:
            # Only one probe call is allowed at a time in half-open state.
            # Block additional concurrent calls until the probe completes.
            raise CircuitBreakerOpenError("Circuit breaker is half-open, probe call in progress")

    def record_failure(self) -> None:
        """Record a failure and potentially open circuit breaker."""
        if self._state == _HALF_OPEN:
            # Probe call failed — reopen immediately without waiting for threshold
            self._state = _OPEN
            self.is_open = True
            self.open_time = datetime.now(UTC)
            self.logger.warning("Circuit breaker reopened after failed probe call")
            return

        self.failure_count += 1
        if self.failure_count >= self.threshold:
            self._state = _OPEN
            self.is_open = True
            self.open_time = datetime.now(UTC)
            self.logger.warning("Circuit breaker opened after %s failures", self.failure_count)

    def record_success(self) -> None:
        """Record a success and reset failure count."""
        if self._state == _HALF_OPEN:
            # Probe call succeeded — fully close
            self._state = _CLOSED
            self.logger.info("Circuit breaker closed after successful probe call")
        self.failure_count = 0

    def get_state(self) -> dict[str, Any]:
        """Get current circuit breaker state."""
        return {
            "is_open": self.is_open,
            "state": self._state,
            "failure_count": self.failure_count,
            "threshold": self.threshold,
            "open_time": self.open_time.isoformat() if self.open_time else None,
        }
