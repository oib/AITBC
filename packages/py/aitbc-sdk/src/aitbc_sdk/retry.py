"""Retry and circuit-breaker helpers for the AITBC SDK (v0.16.2 §A2)."""

from __future__ import annotations

import time as _time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from aitbc_errors import CircuitBreakerOpenError, RetryError
from aitbc.network.circuit_breaker import CircuitBreaker as _CoreCircuitBreaker
from aitbc.network.retry_policy import RetryPolicy as _CoreRetryPolicy


@dataclass
class RetryConfig:
    """Configuration for SDK retry behavior."""

    max_retries: int = 3
    enable_logging: bool = False


class SDKRetryPolicy:
    """Retry policy with exponential backoff for SDK clients."""

    def __init__(self, max_retries: int = 3, enable_logging: bool = False) -> None:
        self._policy = _CoreRetryPolicy(max_retries=max_retries, enable_logging=enable_logging)

    def execute(self, request_func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Execute ``request_func`` with retries."""
        return self._policy.execute(request_func, *args, **kwargs)

    async def execute_async(self, request_func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Execute an async ``request_func`` with retries."""
        return await self._policy.execute_async(request_func, *args, **kwargs)


class SDKCircuitBreaker:
    """Circuit breaker for SDK clients."""

    def __init__(self, threshold: int = 5, timeout: int = 60) -> None:
        self._breaker = _CoreCircuitBreaker(threshold=threshold, timeout=timeout)

    def call(self, request_func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Call ``request_func`` behind the circuit breaker."""
        self._breaker.check()
        try:
            result = request_func(*args, **kwargs)
            self._breaker.record_success()
            return result
        except Exception:
            self._breaker.record_failure()
            raise

    def is_open(self) -> bool:
        """Return True if the circuit is open."""
        return self._breaker.is_open

    def get_state(self) -> dict[str, Any]:
        """Return the current circuit breaker state."""
        return self._breaker.get_state()


def with_backoff[T](
    fn: Callable[[], T],
    max_retries: int = 3,
    backoff_seconds: float = 0.5,
    exceptions: tuple[type[Exception], ...] = (Exception,),
) -> T:
    """Call ``fn`` up to ``max_retries + 1`` times with exponential backoff.

    If the final attempt also raises, the last exception is propagated.
    """
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except exceptions as exc:
            last_exc = exc
            if attempt == max_retries:
                break
            _time.sleep(backoff_seconds * (2**attempt))
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("with_backoff exhausted all retries")


__all__ = [
    "CircuitBreakerOpenError",
    "RetryConfig",
    "RetryError",
    "SDKCircuitBreaker",
    "SDKRetryPolicy",
    "with_backoff",
]
