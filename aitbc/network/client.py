"""
HTTP client implementations for AITBC applications
"""

from datetime import UTC, datetime
from typing import Any, cast

import httpx
import requests

from ..aitbc_logging import get_logger
from ..exceptions import CircuitBreakerOpenError, NetworkError, RateLimitError, RetryError
from .cache_layer import CacheLayer
from .circuit_breaker import CircuitBreaker
from .rate_limiter import RateLimiter
from .retry_policy import RetryPolicy


class AITBCHTTPClient:
    """
    Base HTTP client for AITBC applications.
    Provides common HTTP methods with error handling.
    """

    def __init__(
        self,
        base_url: str = "",
        timeout: int | float = 30,
        headers: dict[str, str] | None = None,
        api_key: str | None = None,
        max_retries: int = 3,
        enable_cache: bool = False,
        cache_ttl: int = 300,
        enable_logging: bool = False,
        circuit_breaker_threshold: int = 5,
        rate_limit: int | None = None,
        correlation_id: str | None = None,
    ):
        """
        Initialize HTTP client.

        Args:
            base_url: Base URL for all requests
            timeout: Request timeout in seconds
            headers: Default headers for all requests
            api_key: API key added to request headers
            max_retries: Maximum retry attempts with exponential backoff
            enable_cache: Enable request/response caching for GET requests
            cache_ttl: Cache time-to-live in seconds
            enable_logging: Enable request/response logging
            circuit_breaker_threshold: Failures before opening circuit breaker
            rate_limit: Rate limit in requests per minute
            correlation_id: Correlation ID for distributed tracing
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.headers = headers or {}
        if api_key:
            self.headers["X-API-Key"] = api_key
        self.correlation_id = correlation_id
        self.logger = get_logger(__name__)
        self.session = requests.Session()
        self.session.headers.update(self.headers)

        # Initialize components
        self.circuit_breaker = CircuitBreaker(threshold=circuit_breaker_threshold)
        self.rate_limiter = RateLimiter(rate_limit=rate_limit)
        self.retry_policy = RetryPolicy(max_retries=max_retries, enable_logging=enable_logging)
        self.cache = CacheLayer(enable=enable_cache, ttl=cache_ttl, enable_logging=enable_logging)
        self.enable_logging = enable_logging

    def _build_url(self, endpoint: str) -> str:
        """
        Build full URL from base URL and endpoint.

        Args:
            endpoint: API endpoint

        Returns:
            Full URL
        """
        if endpoint.startswith("http://") or endpoint.startswith("https://"):
            return endpoint
        return f"{self.base_url}/{endpoint.lstrip('/')}"

    def _build_headers(self, headers: dict[str, str] | None = None) -> dict[str, str]:
        """Build request headers with correlation ID if set."""
        req_headers = {**self.headers, **(headers or {})}
        if self.correlation_id:
            req_headers["X-Request-ID"] = self.correlation_id
        return req_headers

    def get(
        self, endpoint: str, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None
    ) -> dict[str, Any]:
        """
        Perform GET request.

        Args:
            endpoint: API endpoint
            params: Query parameters
            headers: Additional headers

        Returns:
            Response data as dictionary

        Raises:
            NetworkError: If request fails
            CircuitBreakerOpenError: If circuit breaker is open
            RateLimitError: If rate limit is exceeded
        """
        url = self._build_url(endpoint)
        cache_key = self.cache.get_cache_key(url, params)
        cached_data = self.cache.get(cache_key)
        if cached_data is not None:
            return cached_data

        self.circuit_breaker.check()
        self.rate_limiter.check()
        req_headers = self._build_headers(headers)

        if self.enable_logging:
            self.logger.info("GET %s with params=%s", url, params)
        start_time = datetime.now(UTC)

        def _make_request():
            response = self.session.get(url, params=params, headers=req_headers, timeout=self.timeout)
            response.raise_for_status()
            return response.json()

        try:
            result = self.retry_policy.execute(_make_request)
            self.cache.set(cache_key, result)
            self.circuit_breaker.record_success()
            self.rate_limiter.record_request()
            if self.enable_logging:
                elapsed = (datetime.now(UTC) - start_time).total_seconds()
                self.logger.info("GET %s succeeded in %ss", url, elapsed)
            return cast(dict[str, Any], result)
        except (RateLimitError, CircuitBreakerOpenError):
            raise
        except RetryError as e:
            self.circuit_breaker.record_failure()
            raise NetworkError(f"GET request failed: {e}") from e
        except requests.RequestException as e:
            self.circuit_breaker.record_failure()
            raise NetworkError(f"GET request failed: {e}") from e

    def post(
        self,
        endpoint: str,
        data: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """
        Perform POST request.

        Args:
            endpoint: API endpoint
            data: Form data
            json: JSON data
            headers: Additional headers

        Returns:
            Response data as dictionary

        Raises:
            NetworkError: If request fails
            CircuitBreakerOpenError: If circuit breaker is open
            RateLimitError: If rate limit is exceeded
        """
        url = self._build_url(endpoint)
        self.circuit_breaker.check()
        self.rate_limiter.check()
        req_headers = self._build_headers(headers)

        if self.enable_logging:
            self.logger.info("POST %s with json=%s", url, json)
        start_time = datetime.now(UTC)

        def _make_request():
            response = self.session.post(url, data=data, json=json, headers=req_headers, timeout=self.timeout)
            response.raise_for_status()
            return response.json()

        try:
            result = self.retry_policy.execute(_make_request)
            self.circuit_breaker.record_success()
            self.rate_limiter.record_request()
            if self.enable_logging:
                elapsed = (datetime.now(UTC) - start_time).total_seconds()
                self.logger.info("POST %s succeeded in %ss", url, elapsed)
            return cast(dict[str, Any], result)
        except (RateLimitError, CircuitBreakerOpenError):
            raise
        except RetryError as e:
            self.circuit_breaker.record_failure()
            raise NetworkError(f"POST request failed: {e}") from e
        except requests.RequestException as e:
            self.circuit_breaker.record_failure()
            raise NetworkError(f"POST request failed: {e}") from e

    def put(
        self,
        endpoint: str,
        data: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """
        Perform PUT request.

        Args:
            endpoint: API endpoint
            data: Form data
            json: JSON data
            headers: Additional headers

        Returns:
            Response data as dictionary

        Raises:
            NetworkError: If request fails
            CircuitBreakerOpenError: If circuit breaker is open
            RateLimitError: If rate limit is exceeded
        """
        url = self._build_url(endpoint)
        self.circuit_breaker.check()
        self.rate_limiter.check()
        req_headers = self._build_headers(headers)

        if self.enable_logging:
            self.logger.info("PUT %s with json=%s", url, json)
        start_time = datetime.now(UTC)

        def _make_request():
            response = self.session.put(url, data=data, json=json, headers=req_headers, timeout=self.timeout)
            response.raise_for_status()
            return response.json()

        try:
            result = self.retry_policy.execute(_make_request)
            self.circuit_breaker.record_success()
            self.rate_limiter.record_request()
            if self.enable_logging:
                elapsed = (datetime.now(UTC) - start_time).total_seconds()
                self.logger.info("PUT %s succeeded in %ss", url, elapsed)
            return cast(dict[str, Any], result)
        except (RateLimitError, CircuitBreakerOpenError):
            raise
        except RetryError as e:
            self.circuit_breaker.record_failure()
            raise NetworkError(f"PUT request failed: {e}") from e
        except requests.RequestException as e:
            self.circuit_breaker.record_failure()
            raise NetworkError(f"PUT request failed: {e}") from e

    def delete(
        self, endpoint: str, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None
    ) -> dict[str, Any]:
        """
        Perform DELETE request.

        Args:
            endpoint: API endpoint
            params: Query parameters
            headers: Additional headers

        Returns:
            Response data as dictionary

        Raises:
            NetworkError: If request fails
            CircuitBreakerOpenError: If circuit breaker is open
            RateLimitError: If rate limit is exceeded
        """
        url = self._build_url(endpoint)
        self.circuit_breaker.check()
        self.rate_limiter.check()
        req_headers = self._build_headers(headers)

        if self.enable_logging:
            self.logger.info("DELETE %s with params=%s", url, params)
        start_time = datetime.now(UTC)

        def _make_request():
            response = self.session.delete(url, params=params, headers=req_headers, timeout=self.timeout)
            response.raise_for_status()
            return response.json() if response.content else {}

        try:
            result = self.retry_policy.execute(_make_request)
            self.circuit_breaker.record_success()
            self.rate_limiter.record_request()
            if self.enable_logging:
                elapsed = (datetime.now(UTC) - start_time).total_seconds()
                self.logger.info("DELETE %s succeeded in %ss", url, elapsed)
            return cast(dict[str, Any], result)
        except (RateLimitError, CircuitBreakerOpenError):
            raise
        except RetryError as e:
            self.circuit_breaker.record_failure()
            raise NetworkError(f"DELETE request failed: {e}") from e
        except requests.RequestException as e:
            self.circuit_breaker.record_failure()
            raise NetworkError(f"DELETE request failed: {e}") from e

    def close(self) -> None:
        """Close the HTTP session."""
        self.session.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


class AsyncAITBCHTTPClient:
    """
    Async HTTP client for AITBC applications.
    Provides async HTTP methods with error handling.
    """

    def __init__(
        self,
        base_url: str = "",
        timeout: int | float = 30,
        headers: dict[str, str] | None = None,
        api_key: str | None = None,
        max_retries: int = 3,
        enable_cache: bool = False,
        cache_ttl: int = 300,
        enable_logging: bool = False,
        circuit_breaker_threshold: int = 5,
        rate_limit: int | None = None,
        correlation_id: str | None = None,
    ):
        """
        Initialize async HTTP client.

        Args:
            base_url: Base URL for all requests
            timeout: Request timeout in seconds
            headers: Default headers for all requests
            api_key: API key added to request headers
            max_retries: Maximum retry attempts with exponential backoff
            enable_cache: Enable request/response caching for GET requests
            cache_ttl: Cache time-to-live in seconds
            enable_logging: Enable request/response logging
            circuit_breaker_threshold: Failures before opening circuit breaker
            rate_limit: Rate limit in requests per minute
            correlation_id: Correlation ID for distributed tracing
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.headers = headers or {}
        if api_key:
            self.headers["X-API-Key"] = api_key
        self.correlation_id = correlation_id
        self.logger = get_logger(__name__)

        # Initialize components
        #
        # V23-12 listed this module as needing a concurrency audit: several `async def`s and
        # no lock. This is the result of that audit, recorded here because the next reader
        # will ask the same question.
        #
        # This class holds no mutable shared state of its own. Everything set above is
        # read-only after __init__ (base_url, headers, timeout, correlation_id,
        # enable_logging), and every piece of state that *does* change across requests lives
        # in the collaborators below, each of which locks it:
        #
        #   CircuitBreaker  — failure count and open/closed state
        #   RateLimiter     — the request window
        #   CacheLayer      — the response cache
        #   RetryPolicy     — stateless; holds parameters only
        #
        # Those three use threading.Lock rather than asyncio.Lock, which is correct here:
        # their critical sections are synchronous and contain no await, so they cannot be
        # suspended while held. That makes them safe under the event loop and under threads,
        # whereas an asyncio.Lock would only cover the former.
        #
        # So the absence of a lock here is a conclusion, not an omission. Adding one would
        # serialise unrelated requests through a client that is already safe to share.
        #
        # If mutable state is ever added to this class, it needs its own lock: the
        # collaborators' locks protect their state, not this object's.
        self.circuit_breaker = CircuitBreaker(threshold=circuit_breaker_threshold)
        self.rate_limiter = RateLimiter(rate_limit=rate_limit)
        self.retry_policy = RetryPolicy(max_retries=max_retries, enable_logging=enable_logging)
        self.cache = CacheLayer(enable=enable_cache, ttl=cache_ttl, enable_logging=enable_logging)
        self.enable_logging = enable_logging

    def _build_url(self, endpoint: str) -> str:
        """Build full URL from base URL and endpoint."""
        if endpoint.startswith("http://") or endpoint.startswith("https://"):
            return endpoint
        return f"{self.base_url}/{endpoint.lstrip('/')}"

    def _build_headers(self, headers: dict[str, str] | None = None) -> dict[str, str]:
        """Build request headers with correlation ID if set."""
        req_headers = {**self.headers, **(headers or {})}
        if self.correlation_id:
            req_headers["X-Request-ID"] = self.correlation_id
        return req_headers

    async def get(
        self, endpoint: str, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None
    ) -> dict[str, Any]:
        """
        Perform async GET request.

        Args:
            endpoint: API endpoint
            params: Query parameters
            headers: Additional headers

        Returns:
            Response data as dictionary

        Raises:
            NetworkError: If request fails
            CircuitBreakerOpenError: If circuit breaker is open
            RateLimitError: If rate limit is exceeded
        """
        url = self._build_url(endpoint)
        cache_key = self.cache.get_cache_key(url, params)
        cached_data = self.cache.get(cache_key)
        if cached_data is not None:
            return cached_data

        self.circuit_breaker.check()
        self.rate_limiter.check()
        req_headers = self._build_headers(headers)

        if self.enable_logging:
            self.logger.info("GET %s with params=%s", url, params)
        start_time = datetime.now(UTC)

        async def _make_request():
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                return await client.get(url, params=params, headers=req_headers)

        try:
            response = await self.retry_policy.execute_async(_make_request)
            response.raise_for_status()
            result = response.json()
            self.cache.set(cache_key, result)
            self.circuit_breaker.record_success()
            self.rate_limiter.record_request()
            if self.enable_logging:
                elapsed = (datetime.now(UTC) - start_time).total_seconds()
                self.logger.info("GET %s succeeded in %ss", url, elapsed)
            return cast(dict[str, Any], result)
        except (RateLimitError, CircuitBreakerOpenError):
            raise
        except RetryError as e:
            self.circuit_breaker.record_failure()
            raise NetworkError(f"GET request failed: {e}") from e
        except httpx.HTTPError as e:
            self.circuit_breaker.record_failure()
            raise NetworkError(f"GET request failed: {e}") from e

    async def post(
        self,
        endpoint: str,
        data: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """
        Perform async POST request.

        Args:
            endpoint: API endpoint
            data: Form data
            json: JSON data
            headers: Additional headers

        Returns:
            Response data as dictionary

        Raises:
            NetworkError: If request fails
            CircuitBreakerOpenError: If circuit breaker is open
            RateLimitError: If rate limit is exceeded
        """
        url = self._build_url(endpoint)
        self.circuit_breaker.check()
        self.rate_limiter.check()
        req_headers = self._build_headers(headers)

        if self.enable_logging:
            self.logger.info("POST %s with json=%s", url, json)
        start_time = datetime.now(UTC)

        async def _make_request():
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                return await client.post(url, data=data, json=json, headers=req_headers)

        try:
            response = await self.retry_policy.execute_async(_make_request)
            response.raise_for_status()
            result = response.json()
            self.circuit_breaker.record_success()
            self.rate_limiter.record_request()
            if self.enable_logging:
                elapsed = (datetime.now(UTC) - start_time).total_seconds()
                self.logger.info("POST %s succeeded in %ss", url, elapsed)
            return cast(dict[str, Any], result)
        except (RateLimitError, CircuitBreakerOpenError):
            raise
        except RetryError as e:
            self.circuit_breaker.record_failure()
            raise NetworkError(f"POST request failed: {e}") from e
        except httpx.HTTPError as e:
            self.circuit_breaker.record_failure()
            raise NetworkError(f"POST request failed: {e}") from e

    async def put(
        self,
        endpoint: str,
        data: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """
        Perform async PUT request.

        Args:
            endpoint: API endpoint
            data: Form data
            json: JSON data
            headers: Additional headers

        Returns:
            Response data as dictionary

        Raises:
            NetworkError: If request fails
            CircuitBreakerOpenError: If circuit breaker is open
            RateLimitError: If rate limit is exceeded
        """
        url = self._build_url(endpoint)
        self.circuit_breaker.check()
        self.rate_limiter.check()
        req_headers = self._build_headers(headers)

        if self.enable_logging:
            self.logger.info("PUT %s with json=%s", url, json)
        start_time = datetime.now(UTC)

        async def _make_request():
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                return await client.put(url, data=data, json=json, headers=req_headers)

        try:
            response = await self.retry_policy.execute_async(_make_request)
            response.raise_for_status()
            result = response.json()
            self.circuit_breaker.record_success()
            self.rate_limiter.record_request()
            if self.enable_logging:
                elapsed = (datetime.now(UTC) - start_time).total_seconds()
                self.logger.info("PUT %s succeeded in %ss", url, elapsed)
            return cast(dict[str, Any], result)
        except (RateLimitError, CircuitBreakerOpenError):
            raise
        except RetryError as e:
            self.circuit_breaker.record_failure()
            raise NetworkError(f"PUT request failed: {e}") from e
        except httpx.HTTPError as e:
            self.circuit_breaker.record_failure()
            raise NetworkError(f"PUT request failed: {e}") from e

    async def delete(
        self, endpoint: str, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None
    ) -> dict[str, Any]:
        """
        Perform async DELETE request.

        Args:
            endpoint: API endpoint
            params: Query parameters
            headers: Additional headers

        Returns:
            Response data as dictionary

        Raises:
            NetworkError: If request fails
            CircuitBreakerOpenError: If circuit breaker is open
            RateLimitError: If rate limit is exceeded
        """
        url = self._build_url(endpoint)
        self.circuit_breaker.check()
        self.rate_limiter.check()
        req_headers = self._build_headers(headers)

        if self.enable_logging:
            self.logger.info("DELETE %s with params=%s", url, params)
        start_time = datetime.now(UTC)

        async def _make_request():
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                return await client.delete(url, params=params, headers=req_headers)

        try:
            response = await self.retry_policy.execute_async(_make_request)
            response.raise_for_status()
            result = response.json() if response.content else {}
            self.circuit_breaker.record_success()
            self.rate_limiter.record_request()
            if self.enable_logging:
                elapsed = (datetime.now(UTC) - start_time).total_seconds()
                self.logger.info("DELETE %s succeeded in %ss", url, elapsed)
            return cast(dict[str, Any], result)
        except (RateLimitError, CircuitBreakerOpenError):
            raise
        except RetryError as e:
            self.circuit_breaker.record_failure()
            raise NetworkError(f"DELETE request failed: {e}") from e
        except httpx.HTTPError as e:
            self.circuit_breaker.record_failure()
            raise NetworkError(f"DELETE request failed: {e}") from e

    async def close(self) -> None:
        """Close the async HTTP client (no-op for requests)."""
        pass

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
