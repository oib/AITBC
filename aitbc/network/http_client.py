"""
AITBC HTTP Client
Base HTTP client with common utilities for AITBC applications
"""

import asyncio
import time
from datetime import datetime
from typing import Any

import requests

from ..aitbc_logging import get_logger
from ..exceptions import CircuitBreakerOpenError, NetworkError, RateLimitError, RetryError


class AITBCHTTPClient:
    """
    Base HTTP client for AITBC applications.
    Provides common HTTP methods with error handling.
    """

    def __init__(
        self,
        base_url: str = "",
        timeout: int = 30,
        headers: dict[str, str] | None = None,
        max_retries: int = 3,
        enable_cache: bool = False,
        cache_ttl: int = 300,
        enable_logging: bool = False,
        circuit_breaker_threshold: int = 5,
        rate_limit: int | None = None,
    ):
        """
        Initialize HTTP client.

        Args:
            base_url: Base URL for all requests
            timeout: Request timeout in seconds
            headers: Default headers for all requests
            max_retries: Maximum retry attempts with exponential backoff
            enable_cache: Enable request/response caching for GET requests
            cache_ttl: Cache time-to-live in seconds
            enable_logging: Enable request/response logging
            circuit_breaker_threshold: Failures before opening circuit breaker
            rate_limit: Rate limit in requests per minute
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.headers = headers or {}
        self.max_retries = max_retries
        self.enable_cache = enable_cache
        self.cache_ttl = cache_ttl
        self.enable_logging = enable_logging
        self.circuit_breaker_threshold = circuit_breaker_threshold
        self.rate_limit = rate_limit
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self.logger = get_logger(__name__)
        self._cache: dict[str, tuple] = {}
        self._failure_count = 0
        self._circuit_open = False
        self._circuit_open_time = None
        self._request_times: list = []

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

    def _check_circuit_breaker(self) -> None:
        """Check if circuit breaker is open and raise exception if so."""
        if self._circuit_open:
            if self._circuit_open_time and (datetime.now() - self._circuit_open_time).total_seconds() > 60:
                self._circuit_open = False
                self._failure_count = 0
                self.logger.info("Circuit breaker reset to half-open state")
            else:
                raise CircuitBreakerOpenError("Circuit breaker is open, rejecting request")

    def _record_failure(self) -> None:
        """Record a failure and potentially open circuit breaker."""
        self._failure_count += 1
        if self._failure_count >= self.circuit_breaker_threshold:
            self._circuit_open = True
            self._circuit_open_time = datetime.now()
            self.logger.warning("Circuit breaker opened after %s failures", self._failure_count)

    def _check_rate_limit(self) -> None:
        """Check if rate limit is exceeded and raise exception if so."""
        if not self.rate_limit:
            return
        now = datetime.now()
        self._request_times = [t for t in self._request_times if (now - t).total_seconds() < 60]
        if len(self._request_times) >= self.rate_limit:
            raise RateLimitError(f"Rate limit exceeded: {self.rate_limit} requests per minute")

    def _record_request(self) -> None:
        """Record a request timestamp for rate limiting."""
        if self.rate_limit:
            self._request_times.append(datetime.now())

    def _get_cache_key(self, url: str, params: dict[str, Any] | None = None) -> str:
        """Generate cache key from URL and params."""
        if params:
            import hashlib

            param_str = str(sorted(params.items()))
            return f"{url}:{hashlib.sha256(param_str.encode()).hexdigest()}"
        return url

    def _get_cache(self, cache_key: str) -> dict[str, Any] | None:
        """Get cached response if available and not expired."""
        if not self.enable_cache:
            return None
        if cache_key in self._cache:
            data, timestamp = self._cache[cache_key]
            if (datetime.now() - timestamp).total_seconds() < self.cache_ttl:
                if self.enable_logging:
                    self.logger.info("Cache hit for %s", cache_key)
                return data
            else:
                del self._cache[cache_key]
        return None

    def _set_cache(self, cache_key: str, data: dict[str, Any]) -> None:
        """Cache response data."""
        if self.enable_cache:
            self._cache[cache_key] = (data, datetime.now())
            if self.enable_logging:
                self.logger.info("Cached response for %s", cache_key)

    def _retry_request(self, request_func, *args, **kwargs) -> dict[str, Any]:
        """Execute request with retry logic and exponential backoff."""
        last_error = None
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
                last_error = e
                if attempt < self.max_retries:
                    if self.enable_logging:
                        self.logger.warning("Request failed (attempt %s/%s): %s", attempt + 1, self.max_retries + 1, e)
                    continue
                else:
                    if self.enable_logging:
                        self.logger.error("All retry attempts exhausted: %s", e)
                    raise RetryError(f"Retry attempts exhausted: {e}") from e
        raise NetworkError(f"Request failed: {last_error}")

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
        cache_key = self._get_cache_key(url, params)
        cached_data = self._get_cache(cache_key)
        if cached_data is not None:
            return cached_data
        self._check_circuit_breaker()
        self._check_rate_limit()
        req_headers = {**self.headers, **(headers or {})}
        if self.enable_logging:
            self.logger.info("GET %s with params=%s", url, params)
        start_time = datetime.now()

        def _make_request():
            response = self.session.get(url, params=params, headers=req_headers, timeout=self.timeout)
            response.raise_for_status()
            return response.json()

        try:
            result = self._retry_request(_make_request)
            self._set_cache(cache_key, result)
            self._failure_count = 0
            self._record_request()
            if self.enable_logging:
                elapsed = (datetime.now() - start_time).total_seconds()
                self.logger.info("GET %s succeeded in %ss", url, elapsed)
            return result
        except (RetryError, CircuitBreakerOpenError, RateLimitError):
            raise
        except requests.RequestException as e:
            self._record_failure()
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
        self._check_circuit_breaker()
        self._check_rate_limit()
        req_headers = {**self.headers, **(headers or {})}
        if self.enable_logging:
            self.logger.info("POST %s with json=%s", url, json)
        start_time = datetime.now()

        def _make_request():
            response = self.session.post(url, data=data, json=json, headers=req_headers, timeout=self.timeout)
            response.raise_for_status()
            return response.json()

        try:
            result = self._retry_request(_make_request)
            self._failure_count = 0
            self._record_request()
            if self.enable_logging:
                elapsed = (datetime.now() - start_time).total_seconds()
                self.logger.info("POST %s succeeded in %ss", url, elapsed)
            return result
        except (RetryError, CircuitBreakerOpenError, RateLimitError):
            raise
        except requests.RequestException as e:
            self._record_failure()
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
        self._check_circuit_breaker()
        self._check_rate_limit()
        req_headers = {**self.headers, **(headers or {})}
        if self.enable_logging:
            self.logger.info("PUT %s with json=%s", url, json)
        start_time = datetime.now()

        def _make_request():
            response = self.session.put(url, data=data, json=json, headers=req_headers, timeout=self.timeout)
            response.raise_for_status()
            return response.json()

        try:
            result = self._retry_request(_make_request)
            self._failure_count = 0
            self._record_request()
            if self.enable_logging:
                elapsed = (datetime.now() - start_time).total_seconds()
                self.logger.info("PUT %s succeeded in %ss", url, elapsed)
            return result
        except (RetryError, CircuitBreakerOpenError, RateLimitError):
            raise
        except requests.RequestException as e:
            self._record_failure()
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
        self._check_circuit_breaker()
        self._check_rate_limit()
        req_headers = {**self.headers, **(headers or {})}
        if self.enable_logging:
            self.logger.info("DELETE %s with params=%s", url, params)
        start_time = datetime.now()

        def _make_request():
            response = self.session.delete(url, params=params, headers=req_headers, timeout=self.timeout)
            response.raise_for_status()
            return response.json() if response.content else {}

        try:
            result = self._retry_request(_make_request)
            self._failure_count = 0
            self._record_request()
            if self.enable_logging:
                elapsed = (datetime.now() - start_time).total_seconds()
                self.logger.info("DELETE %s succeeded in %ss", url, elapsed)
            return result
        except (RetryError, CircuitBreakerOpenError, RateLimitError):
            raise
        except requests.RequestException as e:
            self._record_failure()
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
        timeout: int = 30,
        headers: dict[str, str] | None = None,
        max_retries: int = 3,
        enable_cache: bool = False,
        cache_ttl: int = 300,
        enable_logging: bool = False,
        circuit_breaker_threshold: int = 5,
        rate_limit: int | None = None,
    ):
        """
        Initialize async HTTP client.

        Args:
            base_url: Base URL for all requests
            timeout: Request timeout in seconds
            headers: Default headers for all requests
            max_retries: Maximum retry attempts with exponential backoff
            enable_cache: Enable request/response caching for GET requests
            cache_ttl: Cache time-to-live in seconds
            enable_logging: Enable request/response logging
            circuit_breaker_threshold: Failures before opening circuit breaker
            rate_limit: Rate limit in requests per minute
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.headers = headers or {}
        self.max_retries = max_retries
        self.enable_cache = enable_cache
        self.cache_ttl = cache_ttl
        self.enable_logging = enable_logging
        self.circuit_breaker_threshold = circuit_breaker_threshold
        self.rate_limit = rate_limit
        self.logger = get_logger(__name__)
        self._client = None
        self._cache: dict[str, tuple] = {}
        self._failure_count = 0
        self._circuit_open = False
        self._circuit_open_time = None
        self._request_times: list = []

    async def __aenter__(self):
        """Async context manager entry."""
        import httpx

        self._client = httpx.AsyncClient(timeout=self.timeout, headers=self.headers)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self._client:
            await self._client.aclose()

    def _build_url(self, endpoint: str) -> str:
        """Build full URL from base URL and endpoint."""
        if endpoint.startswith("http://") or endpoint.startswith("https://"):
            return endpoint
        return f"{self.base_url}/{endpoint.lstrip('/')}"

    def _check_circuit_breaker(self) -> None:
        """Check if circuit breaker is open and raise exception if so."""
        if self._circuit_open:
            if self._circuit_open_time and (datetime.now() - self._circuit_open_time).total_seconds() > 60:
                self._circuit_open = False
                self._failure_count = 0
                self.logger.info("Circuit breaker reset to half-open state")
            else:
                raise CircuitBreakerOpenError("Circuit breaker is open, rejecting request")

    def _record_failure(self) -> None:
        """Record a failure and potentially open circuit breaker."""
        self._failure_count += 1
        if self._failure_count >= self.circuit_breaker_threshold:
            self._circuit_open = True
            self._circuit_open_time = datetime.now()
            self.logger.warning("Circuit breaker opened after %s failures", self._failure_count)

    def _check_rate_limit(self) -> None:
        """Check if rate limit is exceeded and raise exception if so."""
        if not self.rate_limit:
            return
        now = datetime.now()
        self._request_times = [t for t in self._request_times if (now - t).total_seconds() < 60]
        if len(self._request_times) >= self.rate_limit:
            raise RateLimitError(f"Rate limit exceeded: {self.rate_limit} requests per minute")

    def _record_request(self) -> None:
        """Record a request timestamp for rate limiting."""
        if self.rate_limit:
            self._request_times.append(datetime.now())

    def _get_cache_key(self, url: str, params: dict[str, Any] | None = None) -> str:
        """Generate cache key from URL and params."""
        if params:
            import hashlib

            param_str = str(sorted(params.items()))
            return f"{url}:{hashlib.sha256(param_str.encode()).hexdigest()}"
        return url

    def _get_cache(self, cache_key: str) -> dict[str, Any] | None:
        """Get cached response if available and not expired."""
        if not self.enable_cache:
            return None
        if cache_key in self._cache:
            data, timestamp = self._cache[cache_key]
            if (datetime.now() - timestamp).total_seconds() < self.cache_ttl:
                if self.enable_logging:
                    self.logger.info("Cache hit for %s", cache_key)
                return data
            else:
                del self._cache[cache_key]
        return None

    def _set_cache(self, cache_key: str, data: dict[str, Any]) -> None:
        """Cache response data."""
        if self.enable_cache:
            self._cache[cache_key] = (data, datetime.now())
            if self.enable_logging:
                self.logger.info("Cached response for %s", cache_key)

    async def _retry_request(self, request_func, *args, **kwargs) -> dict[str, Any]:
        """Execute async request with retry logic and exponential backoff."""
        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                if attempt > 0:
                    backoff_time = 2 ** (attempt - 1)
                    if self.enable_logging:
                        self.logger.info("Retry attempt %s/%s after %ss backoff", attempt, self.max_retries, backoff_time)
                    await asyncio.sleep(backoff_time)
                return await request_func(*args, **kwargs)
            except Exception as e:
                last_error = e
                if attempt < self.max_retries:
                    if self.enable_logging:
                        self.logger.warning("Request failed (attempt %s/%s): %s", attempt + 1, self.max_retries + 1, e)
                    continue
                else:
                    if self.enable_logging:
                        self.logger.error("All retry attempts exhausted: %s", e)
                    raise RetryError(f"Retry attempts exhausted: {e}") from e
        raise NetworkError(f"Request failed: {last_error}")

    async def async_get(
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
        """
        if not self._client:
            raise RuntimeError("Async client not initialized. Use async context manager.")
        url = self._build_url(endpoint)
        cache_key = self._get_cache_key(url, params)
        cached_data = self._get_cache(cache_key)
        if cached_data is not None:
            return cached_data
        self._check_circuit_breaker()
        self._check_rate_limit()
        req_headers = {**self.headers, **(headers or {})}
        if self.enable_logging:
            self.logger.info("ASYNC GET %s with params=%s", url, params)
        start_time = datetime.now()

        async def _make_request():
            response = await self._client.get(url, params=params, headers=req_headers)
            response.raise_for_status()
            return response.json()

        try:
            result = await self._retry_request(_make_request)
            self._set_cache(cache_key, result)
            self._failure_count = 0
            self._record_request()
            if self.enable_logging:
                elapsed = (datetime.now() - start_time).total_seconds()
                self.logger.info("ASYNC GET %s succeeded in %ss", url, elapsed)
            return result
        except (RetryError, CircuitBreakerOpenError, RateLimitError):
            raise
        except Exception as e:
            self._record_failure()
            raise NetworkError(f"ASYNC GET request failed: {e}") from e

    async def async_post(
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
        """
        if not self._client:
            raise RuntimeError("Async client not initialized. Use async context manager.")
        url = self._build_url(endpoint)
        self._check_circuit_breaker()
        self._check_rate_limit()
        req_headers = {**self.headers, **(headers or {})}
        if self.enable_logging:
            self.logger.info("ASYNC POST %s with json=%s", url, json)
        start_time = datetime.now()

        async def _make_request():
            response = await self._client.post(url, data=data, json=json, headers=req_headers)
            response.raise_for_status()
            return response.json()

        try:
            result = await self._retry_request(_make_request)
            self._failure_count = 0
            self._record_request()
            if self.enable_logging:
                elapsed = (datetime.now() - start_time).total_seconds()
                self.logger.info("ASYNC POST %s succeeded in %ss", url, elapsed)
            return result
        except (RetryError, CircuitBreakerOpenError, RateLimitError):
            raise
        except Exception as e:
            self._record_failure()
            raise NetworkError(f"ASYNC POST request failed: {e}") from e
