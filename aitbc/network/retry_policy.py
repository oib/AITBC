"""
Retry policy with exponential backoff for HTTP client
"""

import asyncio
import time
from collections.abc import Callable
from typing import Any

import httpx
from urllib3.exceptions import (
    ConnectTimeoutError,
    NameResolutionError,
    NewConnectionError,
    ProxyError,
)

from ..aitbc_logging import get_logger
from ..exceptions import AmbiguousRequestError, RetryError

# Methods that are idempotent by HTTP spec: replaying them cannot create a
# second logical operation, so an ambiguous failure (post-send timeout, 5xx)
# is safe to retry.
SPEC_IDEMPOTENT_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE", "PUT", "DELETE"})

# urllib3 failures that prove the request never left this process. Anything
# else under requests.ConnectionError (protocol errors mid-stream, dropped
# keep-alives) is ambiguous.
_PRESEND_URLLIB3 = (NewConnectionError, ConnectTimeoutError, NameResolutionError, ProxyError)

# httpx failures that prove the request never left this process.
_PRESEND_HTTPX = (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout)


def _is_presend_requests(exc: BaseException) -> bool:
    """True when a requests.* failure provably happened before the request
    was sent (connect refused, DNS, proxy connect, connect timeout)."""
    import requests

    if isinstance(exc, requests.ConnectTimeout):
        return True
    seen: set[int] = set()
    stack: list[Any] = [exc]
    while stack:
        cur = stack.pop()
        if cur is None or id(cur) in seen:
            continue
        seen.add(id(cur))
        if isinstance(cur, _PRESEND_URLLIB3):
            return True
        # urllib3 MaxRetryError carries the real reason; requests wraps errors
        # as args or __context__.
        reason = getattr(cur, "reason", None)
        if isinstance(reason, _PRESEND_URLLIB3):
            return True
        stack.append(reason)
        stack.append(getattr(cur, "__cause__", None))
        stack.append(getattr(cur, "__context__", None))
        stack.extend(a for a in getattr(cur, "args", ()) if isinstance(a, BaseException))
    return False


class RetryPolicy:
    """Retry policy with exponential backoff"""

    def __init__(self, max_retries: int = 3, enable_logging: bool = False):
        """
        Initialize retry policy.

        Args:
            max_retries: Maximum number of retry attempts
            enable_logging: Enable logging of retry attempts
        """
        self.max_retries = max_retries
        self.enable_logging = enable_logging
        self.logger = get_logger(__name__)

    def _retry_allowed(self, method: str, retry_ambiguous: bool, presend: bool) -> bool:
        if presend:
            # The request never reached the upstream: replaying any method is safe.
            return True
        return method.upper() in SPEC_IDEMPOTENT_METHODS or retry_ambiguous

    def _ambiguous(self, method: str, exc: BaseException) -> AmbiguousRequestError:
        return AmbiguousRequestError(
            f"{method.upper()} request may have reached the server and its outcome is "
            f"unknown ({exc!r}); not retried. Pass an Idempotency-Key to opt into retry."
        )

    def execute(self, request_func: Callable, *args, method: str = "GET", retry_ambiguous: bool = False, **kwargs) -> Any:
        """
        Execute request with retry logic and exponential backoff.

        Args:
            request_func: Function to execute
            method: HTTP method — ambiguous failures (post-send timeouts, 5xx
                responses) are only retried for spec-idempotent methods unless
                retry_ambiguous is set
            retry_ambiguous: caller asserts the upstream deduplicates this
                request (e.g. an Idempotency-Key header was set), so ambiguous
                outcomes may be replayed
            *args: Positional arguments for request_func
            **kwargs: Keyword arguments for request_func

        Returns:
            Result of request_func

        Raises:
            AmbiguousRequestError: a non-idempotent write may have committed
            RetryError: If all retry attempts exhausted
        """
        import requests

        last_error: requests.RequestException | None = None
        for attempt in range(self.max_retries + 1):
            try:
                if attempt > 0:
                    backoff_time = 2 ** (attempt - 1)
                    if self.enable_logging:
                        self.logger.info("Retry attempt %s/%s after %ss backoff", attempt, self.max_retries, backoff_time)
                    time.sleep(backoff_time)
                return request_func(*args, **kwargs)
            except requests.HTTPError as e:
                if e.response is not None and 400 <= e.response.status_code < 500:
                    raise
                # A response (even 5xx) means the request reached the server.
                if not self._retry_allowed(method, retry_ambiguous, presend=False):
                    raise self._ambiguous(method, e) from e
                last_error = e
                if attempt < self.max_retries:
                    if self.enable_logging:
                        self.logger.warning("Request failed (attempt %s/%s): %s", attempt + 1, self.max_retries + 1, e)
                    continue
                else:
                    if self.enable_logging:
                        self.logger.error("All retry attempts exhausted: %s", e)
                    raise RetryError(f"Retry attempts exhausted: {e}") from e
            except requests.RequestException as e:
                if not self._retry_allowed(method, retry_ambiguous, presend=_is_presend_requests(e)):
                    raise self._ambiguous(method, e) from e
                last_error = e
                if attempt < self.max_retries:
                    if self.enable_logging:
                        self.logger.warning("Request failed (attempt %s/%s): %s", attempt + 1, self.max_retries + 1, e)
                    continue
                else:
                    if self.enable_logging:
                        self.logger.error("All retry attempts exhausted: %s", e)
                    raise RetryError(f"Retry attempts exhausted: {e}") from e
        raise RetryError(f"Request failed: {last_error}")

    async def execute_async(
        self, request_func: Callable, *args, method: str = "GET", retry_ambiguous: bool = False, **kwargs
    ) -> Any:
        """
        Execute async request with retry logic and exponential backoff.

        Same retry contract as execute(), for httpx-based request functions.
        (Previously this caught requests.* exceptions while callers used
        httpx, so transport errors were never actually retried.)

        Args:
            request_func: Async function to execute
            method: HTTP method — see execute()
            retry_ambiguous: see execute()
            *args: Positional arguments for request_func
            **kwargs: Keyword arguments for request_func

        Returns:
            Result of request_func

        Raises:
            AmbiguousRequestError: a non-idempotent write may have committed
            RetryError: If all retry attempts exhausted
        """
        last_error: httpx.HTTPError | None = None
        for attempt in range(self.max_retries + 1):
            try:
                if attempt > 0:
                    backoff_time = 2 ** (attempt - 1)
                    if self.enable_logging:
                        self.logger.info("Retry attempt %s/%s after %ss backoff", attempt, self.max_retries, backoff_time)
                    await asyncio.sleep(backoff_time)
                return await request_func(*args, **kwargs)
            except httpx.HTTPStatusError as e:
                if e.response is not None and 400 <= e.response.status_code < 500:
                    raise
                if not self._retry_allowed(method, retry_ambiguous, presend=False):
                    raise self._ambiguous(method, e) from e
                last_error = e
                if attempt < self.max_retries:
                    if self.enable_logging:
                        self.logger.warning("Request failed (attempt %s/%s): %s", attempt + 1, self.max_retries + 1, e)
                    continue
                else:
                    if self.enable_logging:
                        self.logger.error("All retry attempts exhausted: %s", e)
                    raise RetryError(f"Retry attempts exhausted: {e}") from e
            except httpx.HTTPError as e:
                if not self._retry_allowed(method, retry_ambiguous, presend=isinstance(e, _PRESEND_HTTPX)):
                    raise self._ambiguous(method, e) from e
                last_error = e
                if attempt < self.max_retries:
                    if self.enable_logging:
                        self.logger.warning("Request failed (attempt %s/%s): %s", attempt + 1, self.max_retries + 1, e)
                    continue
                else:
                    if self.enable_logging:
                        self.logger.error("All retry attempts exhausted: %s", e)
                    raise RetryError(f"Retry attempts exhausted: {e}") from e
        raise RetryError(f"Request failed: {last_error}")
