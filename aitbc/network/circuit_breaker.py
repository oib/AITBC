"""
Circuit breaker implementation for HTTP client
"""

from datetime import UTC, datetime
from threading import Lock
from typing import Any

from ..aitbc_logging import get_logger
from ..exceptions import CircuitBreakerOpenError

# Circuit breaker states
_CLOSED = "closed"  # Normal operation — all calls allowed
_OPEN = "open"  # Tripped — all calls blocked
_HALF_OPEN = "half_open"  # Probation — limited probe calls allowed

# 4xx statuses that still count as breaker failures. Every other 4xx is a
# definitive application answer (the upstream is reachable and said "no" —
# e.g. the escrow lookup's 404 for a job that has no escrow, #3036), so it
# must not trip the breaker and starve unrelated traffic on the same host.
# Auth faults (401/403), request timeouts (408), early-data refusals (425)
# and throttling (429) are excluded: those signal a misbehaving or
# overloaded upstream, not a definitive answer.
_BREAKER_COUNTING_4XX = frozenset({401, 403, 408, 425, 429})


def http_status_code(exc: BaseException) -> int | None:
    """Return the HTTP status carried by ``exc`` or its cause chain, if any.

    Duck-typed on ``.response.status_code`` so it works for both ``httpx``
    and ``requests`` errors (and ``NetworkError`` wrappers around them)
    without importing either transport library.
    """
    seen: set[int] = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        response = getattr(cur, "response", None)
        code = getattr(response, "status_code", None)
        if isinstance(code, int) and not isinstance(code, bool):
            return code
        cur = cur.__cause__ or cur.__context__
    return None


def is_definitive_response_error(exc: BaseException) -> bool:
    """True when ``exc`` carries a definitive-negative 4xx application answer.

    A 4xx the upstream returned is proof the host is reachable and answered;
    only auth/throttle/transient-request classes (``_BREAKER_COUNTING_4XX``)
    still count as failures. 5xx and transport errors (no status) count.
    """
    status = http_status_code(exc)
    return status is not None and 400 <= status < 500 and status not in _BREAKER_COUNTING_4XX


def record_breaker_outcome(breaker: "CircuitBreaker", context: str | None, exc: BaseException) -> None:
    """Account one failed request against ``breaker``.

    Definitive-negative 4xx responses are recorded neutrally (they close an
    in-flight half-open probe but do not reset or grow the failure count);
    everything else counts as an infrastructure failure.
    """
    if is_definitive_response_error(exc):
        breaker.record_definitive_response(context)
    else:
        breaker.record_failure(context)


class CircuitBreaker:
    """Circuit breaker state machine for preventing cascading failures.

    States:
        closed    — Normal operation, all calls allowed.
        open      — Tripped, all calls blocked until timeout expires.
        half_open — Timeout expired, a single probe call is allowed.
                    If the probe succeeds → closed.
                    If the probe fails → reopens immediately.
    """

    def __init__(self, threshold: int = 5, timeout: int = 60, enabled: bool = True):
        """
        Initialize circuit breaker.

        Args:
            threshold: Number of failures before opening circuit
            timeout: Seconds to wait before attempting to close circuit
            enabled: When False the breaker is inert — ``check`` never raises
                and ``record_*`` are no-ops. Callers that must never be
                starved by accrued failure state (e.g. the JWT-authed escrow
                relay, whose own bounded retry budget is the flood
                protection) opt out this way rather than sharing breakers.
        """
        self.threshold = threshold
        self.timeout = timeout
        self.enabled = enabled
        self.failure_count = 0
        self.is_open = False
        self.open_time: datetime | None = None
        self._state = _CLOSED
        self._lock = Lock()
        self.logger = get_logger(__name__)

    def check(self) -> None:
        """Check if circuit breaker is open and raise exception if so."""
        if not self.enabled:
            return
        with self._lock:
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

    def record_failure(self, context: str | None = None) -> None:
        """Record a failure and potentially open circuit breaker.

        ``context`` names the call that failed (e.g. ``"GET https://…"``) so
        the open/reopen warnings identify the endpoint instead of floating
        context-free on stderr (#2443).
        """
        if not self.enabled:
            return
        suffix = f" — last failure: {context}" if context else ""
        with self._lock:
            if self._state == _HALF_OPEN:
                # Probe call failed — reopen immediately without waiting for threshold
                self._state = _OPEN
                self.is_open = True
                self.open_time = datetime.now(UTC)
                self.logger.warning("Circuit breaker reopened after failed probe call%s", suffix)
                return

            self.failure_count += 1
            if self.failure_count >= self.threshold:
                self._state = _OPEN
                self.is_open = True
                self.open_time = datetime.now(UTC)
                self.logger.warning("Circuit breaker opened after %s failures%s", self.failure_count, suffix)

    def record_definitive_response(self, context: str | None = None) -> None:
        """Record a definitive application answer (e.g. a 404) — neutral.

        The upstream proved reachable, so an in-flight half-open probe
        closes the breaker exactly like a success. In the closed state the
        call is a no-op: it must neither reset accrued infrastructure
        failures (a 404 interleaved with 5xx must not mask them, #3036) nor
        count as one.
        """
        if not self.enabled:
            return
        with self._lock:
            if self._state == _HALF_OPEN:
                self._state = _CLOSED
                self.failure_count = 0
                suffix = f" — last failure: {context}" if context else ""
                self.logger.info("Circuit breaker closed after definitive response probe%s", suffix)

    def record_success(self) -> None:
        """Record a success and reset failure count."""
        if not self.enabled:
            return
        with self._lock:
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
            "enabled": self.enabled,
            "open_time": self.open_time.isoformat() if self.open_time else None,
        }
