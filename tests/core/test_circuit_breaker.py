"""
Tests for aitbc/network/circuit_breaker.py

Covers the half-open probation state: after recovery timeout expires,
a single probe call is allowed. If it succeeds, the breaker closes.
If it fails, the breaker reopens immediately without needing threshold
failures again.
"""

import importlib.util
import time
from pathlib import Path

import pytest


def load_module_from_path(module_name, file_path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Resolved from this file's location rather than hardcoded to /opt/aitbc, so the
# tests read the tree they live in -- a worktree or a fresh clone, not whatever
# happens to be installed at that absolute path.
REPO_ROOT = Path(__file__).resolve().parents[2]

cb_module = load_module_from_path("aitbc.network.circuit_breaker", REPO_ROOT / "aitbc/network/circuit_breaker.py")
CircuitBreaker = cb_module.CircuitBreaker
CircuitBreakerOpenError = cb_module.CircuitBreakerOpenError


class TestCircuitBreakerBasic:
    """Test basic circuit breaker behavior."""

    def test_initial_state(self):
        breaker = CircuitBreaker(threshold=3, timeout=1)
        assert breaker.is_open is False
        assert breaker.failure_count == 0
        breaker.check()  # should not raise

    def test_threshold_breach_opens_breaker(self):
        breaker = CircuitBreaker(threshold=3, timeout=1)
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.is_open is False
        breaker.record_failure()
        assert breaker.is_open is True
        with pytest.raises(CircuitBreakerOpenError):
            breaker.check()

    def test_success_resets_failure_count(self):
        breaker = CircuitBreaker(threshold=3, timeout=1)
        breaker.record_failure()
        breaker.record_failure()
        breaker.record_success()
        assert breaker.failure_count == 0
        assert breaker.is_open is False


class TestCircuitBreakerHalfOpen:
    """Test half-open probation state after recovery timeout."""

    def test_recovery_timeout_allows_probe_call(self):
        """After timeout, check() allows a single probe call (no raise)."""
        breaker = CircuitBreaker(threshold=3, timeout=0.1)
        for _ in range(3):
            breaker.record_failure()
        assert breaker.is_open is True

        # While still in timeout window, calls are blocked
        with pytest.raises(CircuitBreakerOpenError):
            breaker.check()

        # Wait for timeout to expire
        time.sleep(0.15)

        # Now check() should allow the probe call (no raise)
        breaker.check()

    def test_probe_success_closes_breaker(self):
        """After recovery, a successful probe call fully closes the breaker."""
        breaker = CircuitBreaker(threshold=3, timeout=0.1)
        for _ in range(3):
            breaker.record_failure()
        assert breaker.is_open is True

        time.sleep(0.15)
        breaker.check()  # transition to half-open, allow probe
        breaker.record_success()  # probe succeeded

        assert breaker.is_open is False
        assert breaker.failure_count == 0
        # Subsequent calls should pass without raising
        breaker.check()

    def test_probe_failure_reopens_immediately(self):
        """After recovery, a failed probe reopens the breaker immediately
        without needing threshold failures again."""
        breaker = CircuitBreaker(threshold=3, timeout=0.1)
        for _ in range(3):
            breaker.record_failure()
        assert breaker.is_open is True

        time.sleep(0.15)
        breaker.check()  # transition to half-open, allow probe
        breaker.record_failure()  # probe failed

        # Breaker should be open again immediately, not waiting for 3 failures
        assert breaker.is_open is True
        with pytest.raises(CircuitBreakerOpenError):
            breaker.check()

    def test_half_open_blocks_concurrent_calls(self):
        """In half-open state, only one probe call is allowed at a time.
        Additional calls before the probe completes are blocked."""
        breaker = CircuitBreaker(threshold=3, timeout=0.1)
        for _ in range(3):
            breaker.record_failure()

        time.sleep(0.15)
        breaker.check()  # first probe call allowed

        # Second call before probe result should be blocked
        with pytest.raises(CircuitBreakerOpenError):
            breaker.check()

    def test_state_field_in_get_state(self):
        """get_state() includes the internal state field."""
        breaker = CircuitBreaker(threshold=3, timeout=1)
        state = breaker.get_state()
        assert state["state"] == "closed"
        assert state["is_open"] is False

        for _ in range(3):
            breaker.record_failure()
        state = breaker.get_state()
        assert state["state"] == "open"
        assert state["is_open"] is True


class TestCircuitBreakerRecoveryCycle:
    """Test full open → half-open → close/reopen cycle."""

    def test_full_recovery_cycle_success(self):
        """Open → wait → probe → success → closed."""
        breaker = CircuitBreaker(threshold=2, timeout=0.05)

        # Trip the breaker
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.is_open is True

        # Wait for recovery
        time.sleep(0.06)
        breaker.check()  # half-open, probe allowed
        breaker.record_success()  # probe succeeds → closed

        # Breaker should be fully operational again
        assert breaker.is_open is False
        breaker.check()  # should not raise

        # New failures should accumulate normally
        breaker.record_failure()
        assert breaker.is_open is False  # only 1 failure, under threshold

    def test_full_recovery_cycle_failure(self):
        """Open → wait → probe → failure → reopen → wait → probe → success."""
        breaker = CircuitBreaker(threshold=2, timeout=0.05)

        # Trip the breaker
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.is_open is True

        # First recovery attempt: probe fails
        time.sleep(0.06)
        breaker.check()  # half-open
        breaker.record_failure()  # probe fails → reopen
        assert breaker.is_open is True

        # Second recovery attempt: probe succeeds
        time.sleep(0.06)
        breaker.check()  # half-open
        breaker.record_success()  # probe succeeds → closed
        assert breaker.is_open is False


class TestCircuitBreakerFailureContext:
    """#2443: open/reopen warnings must name the call that failed."""

    def test_open_warning_names_failing_call(self, caplog):
        breaker = CircuitBreaker(threshold=2, timeout=60)
        with caplog.at_level("WARNING"):
            breaker.record_failure("GET https://hub.example/v1/market/offer")
            breaker.record_failure("GET https://hub.example/v1/market/offer")
        assert "Circuit breaker opened after 2 failures" in caplog.text
        assert "GET https://hub.example/v1/market/offer" in caplog.text

    def test_open_warning_without_context_unchanged(self, caplog):
        breaker = CircuitBreaker(threshold=1, timeout=60)
        with caplog.at_level("WARNING"):
            breaker.record_failure()
        assert "Circuit breaker opened after 1 failures" in caplog.text
        assert "last failure" not in caplog.text


class TestDefinitiveResponseAccounting:
    """#3036: definitive-negative application answers (e.g. the escrow
    lookup's 404) are neutral — they must not grow or reset the failure
    count, but they DO prove reachability so a half-open probe closes."""

    def test_closed_state_is_noop(self):
        breaker = CircuitBreaker(threshold=3, timeout=1)
        breaker.record_failure()
        breaker.record_definitive_response("GET http://node/rpc/escrow/j1")
        # Neither reset nor incremented
        assert breaker.failure_count == 1
        assert breaker.is_open is False

    def test_does_not_reset_infra_failures(self):
        breaker = CircuitBreaker(threshold=3, timeout=1)
        breaker.record_failure()
        breaker.record_failure()
        breaker.record_definitive_response()
        assert breaker.failure_count == 2
        breaker.record_failure()
        assert breaker.is_open is True

    def test_half_open_probe_definitive_response_closes(self):
        breaker = CircuitBreaker(threshold=2, timeout=0.05)
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.is_open is True
        time.sleep(0.06)
        breaker.check()  # half-open, probe allowed
        breaker.record_definitive_response()  # probe got a definitive answer
        assert breaker.is_open is False
        assert breaker.failure_count == 0
        breaker.check()  # fully closed — no raise

    def test_open_state_untouched(self):
        """A definitive response recorded while still inside the open window
        must not shorten or clear the open state."""
        breaker = CircuitBreaker(threshold=1, timeout=60)
        breaker.record_failure()
        assert breaker.is_open is True
        breaker.record_definitive_response()
        assert breaker.is_open is True
        with pytest.raises(CircuitBreakerOpenError):
            breaker.check()


class TestDefinitiveResponseClassification:
    """#3036: which HTTP statuses count as breaker failures."""

    @staticmethod
    def _exc_with_status(status):
        class _Resp:
            status_code = status

        class _Err(Exception):
            response = _Resp()

        return _Err("boom")

    def test_definitive_4xx(self):
        for status in (400, 404, 405, 409, 410, 412, 413, 415, 422, 451):
            assert cb_module.is_definitive_response_error(self._exc_with_status(status)), status

    def test_counting_4xx(self):
        for status in (401, 403, 408, 425, 429):
            assert not cb_module.is_definitive_response_error(self._exc_with_status(status)), status

    def test_5xx_and_transport_count(self):
        for status in (500, 502, 503):
            assert not cb_module.is_definitive_response_error(self._exc_with_status(status)), status
        assert not cb_module.is_definitive_response_error(RuntimeError("conn refused"))

    def test_status_found_through_cause_chain(self):
        inner = self._exc_with_status(404)
        outer = RuntimeError("wrapped")
        outer.__cause__ = inner
        assert cb_module.is_definitive_response_error(outer)

    def test_record_breaker_outcome_routes(self):
        breaker = CircuitBreaker(threshold=5, timeout=1)
        cb_module.record_breaker_outcome(breaker, "ctx", self._exc_with_status(404))
        assert breaker.failure_count == 0
        cb_module.record_breaker_outcome(breaker, "ctx", self._exc_with_status(503))
        assert breaker.failure_count == 1
        cb_module.record_breaker_outcome(breaker, "ctx", RuntimeError("timeout"))
        assert breaker.failure_count == 2
