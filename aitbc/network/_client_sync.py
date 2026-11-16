"""Synchronous ``requests``-backed AITBC HTTP client.

Extracted verbatim from ``client.py``; helpers come from ``_client_base``.
"""

from datetime import UTC, datetime
from typing import Any

import requests

from ..aitbc_logging import get_logger
from ..exceptions import CircuitBreakerOpenError, NetworkError, RateLimitError, RetryError
from ._client_base import _CredentialSafeSession, _check_api_key_target, _detail_suffix
from .cache_layer import CacheLayer
from .circuit_breaker import CircuitBreaker
from .json_types import JSONResponse, expect_object
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
        enable_circuit_breaker: bool = True,
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
            enable_circuit_breaker: Set False for callers whose requests must
                never be rejected by accrued failure state — e.g. the escrow
                release relay, which retries a bounded number of times and is
                the only JWT-authed release path; an open breaker there once
                rejected the release outright and stranded a locked escrow.
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.headers = dict(headers or {})
        if api_key:
            self.headers["X-API-Key"] = api_key
        _check_api_key_target(base_url, headers=self.headers)
        self.correlation_id = correlation_id
        self.logger = get_logger(__name__)
        self.session = _CredentialSafeSession()
        self.session.headers.update(self.headers)

        # Initialize components
        self.circuit_breaker = CircuitBreaker(threshold=circuit_breaker_threshold, enabled=enable_circuit_breaker)
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

    def _build_headers(self, headers: dict[str, str] | None = None, idempotency_key: str | None = None) -> dict[str, str]:
        """Build request headers with correlation ID if set."""
        req_headers = {**self.headers, **(headers or {})}
        if self.correlation_id:
            req_headers["X-Request-ID"] = self.correlation_id
        if idempotency_key:
            req_headers["Idempotency-Key"] = idempotency_key
        return req_headers

    def _check_request_target(self, url: str, req_headers: dict[str, str]) -> None:
        """Refuse credentials bound for a host outside the trusted set.

        ``_build_url`` returns absolute endpoints verbatim, so one request
        can be pointed at a foreign host even when ``base_url`` is trusted —
        and per-request ``headers=`` can add credentials the client was not
        built with (PI-SDK-01/PI-SDK-04).
        """
        _check_api_key_target(url, headers=req_headers)

    def get(
        self, endpoint: str, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None
    ) -> dict[str, Any]:
        """
        Perform GET request for an endpoint that returns a JSON object.

        Args:
            endpoint: API endpoint
            params: Query parameters
            headers: Additional headers

        Returns:
            Decoded JSON object

        Raises:
            TypeError: If the endpoint returned a JSON array -- use get_json() for those
            NetworkError: If request fails
            CircuitBreakerOpenError: If circuit breaker is open
            RateLimitError: If rate limit is exceeded
        """
        return expect_object(self.get_json(endpoint, params=params, headers=headers), self._build_url(endpoint))

    def get_json(
        self, endpoint: str, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None
    ) -> JSONResponse:
        """
        Perform GET request.

        Args:
            endpoint: API endpoint
            params: Query parameters
            headers: Additional headers

        Returns:
            Decoded JSON body: an object, or an array for the endpoints that
            return one. The caller must check the shape.

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
        self._check_request_target(url, req_headers)

        if self.enable_logging:
            self.logger.info("GET %s with params=%s", url, params)
        start_time = datetime.now(UTC)

        def _make_request():
            response = self.session.get(url, params=params, headers=req_headers, timeout=self.timeout)
            response.raise_for_status()
            return response.json() if response.content else {}

        try:
            result: JSONResponse = self.retry_policy.execute(_make_request, method="GET")
            self.cache.set(cache_key, result)
            self.circuit_breaker.record_success()
            self.rate_limiter.record_request()
            if self.enable_logging:
                elapsed = (datetime.now(UTC) - start_time).total_seconds()
                self.logger.info("GET %s succeeded in %ss", url, elapsed)
            return result
        except (RateLimitError, CircuitBreakerOpenError):
            raise
        except RetryError as e:
            self.circuit_breaker.record_failure()
            raise NetworkError(f"GET request failed: {e}{_detail_suffix(e)}") from e
        except requests.RequestException as e:
            self.circuit_breaker.record_failure()
            raise NetworkError(f"GET request failed: {e}{_detail_suffix(e)}") from e

    def post(
        self,
        endpoint: str,
        data: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """
        Perform POST request.

        Args:
            endpoint: API endpoint
            data: Form data
            json: JSON data
            headers: Additional headers
            idempotency_key: sent as the Idempotency-Key header; when set,
                ambiguous post-send failures are retried on the assumption
                the upstream deduplicates by key

        Returns:
            Decoded JSON object

        Raises:
            TypeError: If the endpoint returned a JSON array
            AmbiguousRequestError: a post-send failure occurred and no
                idempotency key was given — the write may have committed
            NetworkError: If request fails
            CircuitBreakerOpenError: If circuit breaker is open
            RateLimitError: If rate limit is exceeded
        """
        url = self._build_url(endpoint)
        self.circuit_breaker.check()
        self.rate_limiter.check()
        req_headers = self._build_headers(headers, idempotency_key)
        self._check_request_target(url, req_headers)

        if self.enable_logging:
            self.logger.info("POST %s with json=%s", url, json)
        start_time = datetime.now(UTC)

        def _make_request():
            response = self.session.post(url, data=data, json=json, headers=req_headers, timeout=self.timeout)
            response.raise_for_status()
            return response.json() if response.content else {}

        try:
            result: JSONResponse = self.retry_policy.execute(
                _make_request, method="POST", retry_ambiguous=bool(idempotency_key)
            )
            self.circuit_breaker.record_success()
            self.rate_limiter.record_request()
            if self.enable_logging:
                elapsed = (datetime.now(UTC) - start_time).total_seconds()
                self.logger.info("POST %s succeeded in %ss", url, elapsed)
            return expect_object(result, url)
        except (RateLimitError, CircuitBreakerOpenError):
            raise
        except RetryError as e:
            self.circuit_breaker.record_failure()
            raise NetworkError(f"POST request failed: {e}{_detail_suffix(e)}") from e
        except requests.RequestException as e:
            self.circuit_breaker.record_failure()
            raise NetworkError(f"POST request failed: {e}{_detail_suffix(e)}") from e

    def put(
        self,
        endpoint: str,
        data: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """
        Perform PUT request.

        Args:
            endpoint: API endpoint
            data: Form data
            json: JSON data
            headers: Additional headers
            idempotency_key: sent as the Idempotency-Key header (PUT is
                spec-idempotent, so ambiguous retries are already allowed;
                the key lets the upstream deduplicate explicitly)

        Returns:
            Decoded JSON object

        Raises:
            TypeError: If the endpoint returned a JSON array
            NetworkError: If request fails
            CircuitBreakerOpenError: If circuit breaker is open
            RateLimitError: If rate limit is exceeded
        """
        url = self._build_url(endpoint)
        self.circuit_breaker.check()
        self.rate_limiter.check()
        req_headers = self._build_headers(headers, idempotency_key)
        self._check_request_target(url, req_headers)

        if self.enable_logging:
            self.logger.info("PUT %s with json=%s", url, json)
        start_time = datetime.now(UTC)

        def _make_request():
            response = self.session.put(url, data=data, json=json, headers=req_headers, timeout=self.timeout)
            response.raise_for_status()
            return response.json() if response.content else {}

        try:
            result: JSONResponse = self.retry_policy.execute(_make_request, method="PUT")
            self.circuit_breaker.record_success()
            self.rate_limiter.record_request()
            if self.enable_logging:
                elapsed = (datetime.now(UTC) - start_time).total_seconds()
                self.logger.info("PUT %s succeeded in %ss", url, elapsed)
            return expect_object(result, url)
        except (RateLimitError, CircuitBreakerOpenError):
            raise
        except RetryError as e:
            self.circuit_breaker.record_failure()
            raise NetworkError(f"PUT request failed: {e}{_detail_suffix(e)}") from e
        except requests.RequestException as e:
            self.circuit_breaker.record_failure()
            raise NetworkError(f"PUT request failed: {e}{_detail_suffix(e)}") from e

    def patch(
        self,
        endpoint: str,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """
        Perform PATCH request.

        Args:
            endpoint: API endpoint
            json: JSON body
            headers: Additional headers
            idempotency_key: sent as the Idempotency-Key header; when set,
                ambiguous post-send failures are retried (PATCH is not
                spec-idempotent)

        Returns:
            Decoded JSON object

        Raises:
            AmbiguousRequestError: a post-send failure occurred and no
                idempotency key was given — the write may have committed
        """
        url = self._build_url(endpoint)
        self.circuit_breaker.check()
        self.rate_limiter.check()
        req_headers = self._build_headers(headers, idempotency_key)
        self._check_request_target(url, req_headers)

        if self.enable_logging:
            self.logger.info("PATCH %s with json=%s", url, json)
        start_time = datetime.now(UTC)

        def _make_request():
            response = self.session.patch(url, json=json or {}, headers=req_headers, timeout=self.timeout)
            response.raise_for_status()
            return response.json() if response.content else {}

        try:
            result: JSONResponse = self.retry_policy.execute(
                _make_request, method="PATCH", retry_ambiguous=bool(idempotency_key)
            )
            self.circuit_breaker.record_success()
            self.rate_limiter.record_request()
            if self.enable_logging:
                elapsed = (datetime.now(UTC) - start_time).total_seconds()
                self.logger.info("PATCH %s succeeded in %ss", url, elapsed)
            return expect_object(result, url)
        except (RateLimitError, CircuitBreakerOpenError):
            raise
        except RetryError as e:
            self.circuit_breaker.record_failure()
            raise NetworkError(f"PATCH request failed: {e}{_detail_suffix(e)}") from e
        except requests.RequestException as e:
            self.circuit_breaker.record_failure()
            raise NetworkError(f"PATCH request failed: {e}{_detail_suffix(e)}") from e

    def delete(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """
        Perform DELETE request.

        Args:
            endpoint: API endpoint
            params: Query parameters
            headers: Additional headers
            idempotency_key: sent as the Idempotency-Key header (DELETE is
                spec-idempotent; the key lets the upstream deduplicate
                explicitly)

        Returns:
            Decoded JSON object

        Raises:
            TypeError: If the endpoint returned a JSON array
            NetworkError: If request fails
            CircuitBreakerOpenError: If circuit breaker is open
            RateLimitError: If rate limit is exceeded
        """
        url = self._build_url(endpoint)
        self.circuit_breaker.check()
        self.rate_limiter.check()
        req_headers = self._build_headers(headers, idempotency_key)
        self._check_request_target(url, req_headers)

        if self.enable_logging:
            self.logger.info("DELETE %s with params=%s", url, params)
        start_time = datetime.now(UTC)

        def _make_request():
            response = self.session.delete(url, params=params, headers=req_headers, timeout=self.timeout)
            response.raise_for_status()
            return response.json() if response.content else {}

        try:
            result: JSONResponse = self.retry_policy.execute(_make_request, method="DELETE")
            self.circuit_breaker.record_success()
            self.rate_limiter.record_request()
            if self.enable_logging:
                elapsed = (datetime.now(UTC) - start_time).total_seconds()
                self.logger.info("DELETE %s succeeded in %ss", url, elapsed)
            return expect_object(result, url)
        except (RateLimitError, CircuitBreakerOpenError):
            raise
        except RetryError as e:
            self.circuit_breaker.record_failure()
            raise NetworkError(f"DELETE request failed: {e}{_detail_suffix(e)}") from e
        except requests.RequestException as e:
            self.circuit_breaker.record_failure()
            raise NetworkError(f"DELETE request failed: {e}{_detail_suffix(e)}") from e

    def close(self) -> None:
        """Close the HTTP session."""
        self.session.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
