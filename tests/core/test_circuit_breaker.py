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


cb_module = load_module_from_path("aitbc.network.circuit_breaker", Path("/opt/aitbc/aitbc/network/circuit_breaker.py"))
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
