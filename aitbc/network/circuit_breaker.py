"""
Circuit breaker implementation for HTTP client
"""

from datetime import UTC, datetime

from ..aitbc_logging import get_logger
from ..exceptions import CircuitBreakerOpenError


class CircuitBreaker:
    """Circuit breaker state machine for preventing cascading failures"""

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
        self.open_time = None
        self.logger = get_logger(__name__)

    def check(self) -> None:
        """Check if circuit breaker is open and raise exception if so."""
        if self.is_open:
            if self.open_time and (datetime.now(UTC) - self.open_time).total_seconds() > self.timeout:
                self.is_open = False
                self.failure_count = 0
                self.logger.info("Circuit breaker reset to half-open state")
            else:
                raise CircuitBreakerOpenError("Circuit breaker is open, rejecting request")

    def record_failure(self) -> None:
        """Record a failure and potentially open circuit breaker."""
        self.failure_count += 1
        if self.failure_count >= self.threshold:
            self.is_open = True
            self.open_time = datetime.now(UTC)
            self.logger.warning("Circuit breaker opened after %s failures", self.failure_count)

    def record_success(self) -> None:
        """Record a success and reset failure count."""
        self.failure_count = 0

    def get_state(self) -> dict[str, any]:
        """Get current circuit breaker state."""
        return {
            "is_open": self.is_open,
            "failure_count": self.failure_count,
            "threshold": self.threshold,
            "open_time": self.open_time.isoformat() if self.open_time else None,
        }
