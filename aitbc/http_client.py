"""
AITBC HTTP Client
Base HTTP client with common utilities for AITBC applications
"""

import requests
import time
import asyncio
from typing import Dict, Any, Optional, Union
from datetime import datetime, timedelta
from functools import lru_cache
from .exceptions import NetworkError, RetryError, CircuitBreakerOpenError, RateLimitError
from .aitbc_logging import get_logger


class AITBCHTTPClient:
    """
    Base HTTP client for AITBC applications.
    Provides common HTTP methods with error handling.
    """
    
    def __init__(
        self,
        base_url: str = "",
        timeout: int = 30,
        headers: Optional[Dict[str, str]] = None,
        max_retries: int = 3,
        enable_cache: bool = False,
        cache_ttl: int = 300,
        enable_logging: bool = False,
        circuit_breaker_threshold: int = 5,
        rate_limit: Optional[int] = None
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
        
        # Cache storage: {url: (data, timestamp)}
        self._cache: Dict[str, tuple] = {}
        
        # Circuit breaker state
        self._failure_count = 0
        self._circuit_open = False
        self._circuit_open_time = None
        
        # Rate limiting state
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
            # Check if circuit should be reset (after 60 seconds)
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
            self.logger.warning(f"Circuit breaker opened after {self._failure_count} failures")
    
    def _check_rate_limit(self) -> None:
        """Check if rate limit is exceeded and raise exception if so."""
        if not self.rate_limit:
            return
        
        now = datetime.now()
        # Remove requests older than 1 minute
        self._request_times = [t for t in self._request_times if (now - t).total_seconds() < 60]
        
        if len(self._request_times) >= self.rate_limit:
            raise RateLimitError(f"Rate limit exceeded: {self.rate_limit} requests per minute")
    
    def _record_request(self) -> None:
        """Record a request timestamp for rate limiting."""
        if self.rate_limit:
            self._request_times.append(datetime.now())
    
    def _get_cache_key(self, url: str, params: Optional[Dict[str, Any]] = None) -> str:
        """Generate cache key from URL and params."""
        if params:
            import hashlib
            param_str = str(sorted(params.items()))
            return f"{url}:{hashlib.md5(param_str.encode()).hexdigest()}"
        return url
    
    def _get_cache(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Get cached response if available and not expired."""
        if not self.enable_cache:
            return None
        
        if cache_key in self._cache:
            data, timestamp = self._cache[cache_key]
            if (datetime.now() - timestamp).total_seconds() < self.cache_ttl:
                if self.enable_logging:
                    self.logger.info(f"Cache hit for {cache_key}")
                return data
            else:
                # Expired, remove from cache
                del self._cache[cache_key]
        return None
    
    def _set_cache(self, cache_key: str, data: Dict[str, Any]) -> None:
        """Cache response data."""
        if self.enable_cache:
            self._cache[cache_key] = (data, datetime.now())
            if self.enable_logging:
                self.logger.info(f"Cached response for {cache_key}")
    
    def _retry_request(self, request_func, *args, **kwargs) -> Dict[str, Any]:
        """Execute request with retry logic and exponential backoff."""
        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                if attempt > 0:
                    backoff_time = 2 ** (attempt - 1)
                    if self.enable_logging:
                        self.logger.info(f"Retry attempt {attempt}/{self.max_retries} after {backoff_time}s backoff")
                    time.sleep(backoff_time)
                
                return request_func(*args, **kwargs)
            except requests.RequestException as e:
                last_error = e
                if attempt < self.max_retries:
                    if self.enable_logging:
                        self.logger.warning(f"Request failed (attempt {attempt + 1}/{self.max_retries + 1}): {e}")
                    continue
                else:
                    if self.enable_logging:
                        self.logger.error(f"All retry attempts exhausted: {e}")
                    raise RetryError(f"Retry attempts exhausted: {e}")
        
        raise NetworkError(f"Request failed: {last_error}")
    
    def get(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
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
        
        # Check cache first
        cached_data = self._get_cache(cache_key)
        if cached_data is not None:
            return cached_data
        
        # Check circuit breaker and rate limit
        self._check_circuit_breaker()
        self._check_rate_limit()
        
        req_headers = {**self.headers, **(headers or {})}
        
        if self.enable_logging:
            self.logger.info(f"GET {url} with params={params}")
        
        start_time = datetime.now()
        
        def _make_request():
            response = self.session.get(
                url,
                params=params,
                headers=req_headers,
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()
        
        try:
            result = self._retry_request(_make_request)
            
            # Cache successful GET requests
            self._set_cache(cache_key, result)
            
            # Record success for circuit breaker
            self._failure_count = 0
            self._record_request()
            
            if self.enable_logging:
                elapsed = (datetime.now() - start_time).total_seconds()
                self.logger.info(f"GET {url} succeeded in {elapsed:.3f}s")
            
            return result
        except (RetryError, CircuitBreakerOpenError, RateLimitError):
            raise
        except requests.RequestException as e:
            self._record_failure()
            raise NetworkError(f"GET request failed: {e}")
    
    def post(
        self,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
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
        
        # Check circuit breaker and rate limit
        self._check_circuit_breaker()
        self._check_rate_limit()
        
        req_headers = {**self.headers, **(headers or {})}
        
        if self.enable_logging:
            self.logger.info(f"POST {url} with json={json}")
        
        start_time = datetime.now()
        
        def _make_request():
            response = self.session.post(
                url,
                data=data,
                json=json,
                headers=req_headers,
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()
        
        try:
            result = self._retry_request(_make_request)
            
            # Record success for circuit breaker
            self._failure_count = 0
            self._record_request()
            
            if self.enable_logging:
                elapsed = (datetime.now() - start_time).total_seconds()
                self.logger.info(f"POST {url} succeeded in {elapsed:.3f}s")
            
            return result
        except (RetryError, CircuitBreakerOpenError, RateLimitError):
            raise
        except requests.RequestException as e:
            self._record_failure()
            raise NetworkError(f"POST request failed: {e}")
    
    def put(
        self,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
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
        
        # Check circuit breaker and rate limit
        self._check_circuit_breaker()
        self._check_rate_limit()
        
        req_headers = {**self.headers, **(headers or {})}
        
        if self.enable_logging:
            self.logger.info(f"PUT {url} with json={json}")
        
        start_time = datetime.now()
        
        def _make_request():
            response = self.session.put(
                url,
                data=data,
                json=json,
                headers=req_headers,
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()
        
        try:
            result = self._retry_request(_make_request)
            
            # Record success for circuit breaker
            self._failure_count = 0
            self._record_request()
            
            if self.enable_logging:
                elapsed = (datetime.now() - start_time).total_seconds()
                self.logger.info(f"PUT {url} succeeded in {elapsed:.3f}s")
            
            return result
        except (RetryError, CircuitBreakerOpenError, RateLimitError):
            raise
        except requests.RequestException as e:
            self._record_failure()
            raise NetworkError(f"PUT request failed: {e}")
    
    def delete(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
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
        
        # Check circuit breaker and rate limit
        self._check_circuit_breaker()
        self._check_rate_limit()
        
        req_headers = {**self.headers, **(headers or {})}
        
        if self.enable_logging:
            self.logger.info(f"DELETE {url} with params={params}")
        
        start_time = datetime.now()
        
        def _make_request():
            response = self.session.delete(
                url,
                params=params,
                headers=req_headers,
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.json() if response.content else {}
        
        try:
            result = self._retry_request(_make_request)
            
            # Record success for circuit breaker
            self._failure_count = 0
            self._record_request()
            
            if self.enable_logging:
                elapsed = (datetime.now() - start_time).total_seconds()
                self.logger.info(f"DELETE {url} succeeded in {elapsed:.3f}s")
            
            return result
        except (RetryError, CircuitBreakerOpenError, RateLimitError):
            raise
        except requests.RequestException as e:
            self._record_failure()
            raise NetworkError(f"DELETE request failed: {e}")
    
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
        headers: Optional[Dict[str, str]] = None,
        max_retries: int = 3,
        enable_cache: bool = False,
        cache_ttl: int = 300,
        enable_logging: bool = False,
        circuit_breaker_threshold: int = 5,
        rate_limit: Optional[int] = None
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
        
        # Cache storage: {url: (data, timestamp)}
        self._cache: Dict[str, tuple] = {}
        
        # Circuit breaker state
        self._failure_count = 0
        self._circuit_open = False
        self._circuit_open_time = None
        
        # Rate limiting state
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
            self.logger.warning(f"Circuit breaker opened after {self._failure_count} failures")
    
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
    
    def _get_cache_key(self, url: str, params: Optional[Dict[str, Any]] = None) -> str:
        """Generate cache key from URL and params."""
        if params:
            import hashlib
            param_str = str(sorted(params.items()))
            return f"{url}:{hashlib.md5(param_str.encode()).hexdigest()}"
        return url
    
    def _get_cache(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Get cached response if available and not expired."""
        if not self.enable_cache:
            return None
        
        if cache_key in self._cache:
            data, timestamp = self._cache[cache_key]
            if (datetime.now() - timestamp).total_seconds() < self.cache_ttl:
                if self.enable_logging:
                    self.logger.info(f"Cache hit for {cache_key}")
                return data
            else:
                del self._cache[cache_key]
        return None
    
    def _set_cache(self, cache_key: str, data: Dict[str, Any]) -> None:
        """Cache response data."""
        if self.enable_cache:
            self._cache[cache_key] = (data, datetime.now())
            if self.enable_logging:
                self.logger.info(f"Cached response for {cache_key}")
    
    async def _retry_request(self, request_func, *args, **kwargs) -> Dict[str, Any]:
        """Execute async request with retry logic and exponential backoff."""
        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                if attempt > 0:
                    backoff_time = 2 ** (attempt - 1)
                    if self.enable_logging:
                        self.logger.info(f"Retry attempt {attempt}/{self.max_retries} after {backoff_time}s backoff")
                    await asyncio.sleep(backoff_time)
                
                return await request_func(*args, **kwargs)
            except Exception as e:
                last_error = e
                if attempt < self.max_retries:
                    if self.enable_logging:
                        self.logger.warning(f"Request failed (attempt {attempt + 1}/{self.max_retries + 1}): {e}")
                    continue
                else:
                    if self.enable_logging:
                        self.logger.error(f"All retry attempts exhausted: {e}")
                    raise RetryError(f"Retry attempts exhausted: {e}")
        
        raise NetworkError(f"Request failed: {last_error}")
    
    async def async_get(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
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
            self.logger.info(f"ASYNC GET {url} with params={params}")
        
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
                self.logger.info(f"ASYNC GET {url} succeeded in {elapsed:.3f}s")
            
            return result
        except (RetryError, CircuitBreakerOpenError, RateLimitError):
            raise
        except Exception as e:
            self._record_failure()
            raise NetworkError(f"ASYNC GET request failed: {e}")
    
    async def async_post(
        self,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
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
            self.logger.info(f"ASYNC POST {url} with json={json}")
        
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
                self.logger.info(f"ASYNC POST {url} succeeded in {elapsed:.3f}s")
            
            return result
        except (RetryError, CircuitBreakerOpenError, RateLimitError):
            raise
        except Exception as e:
            self._record_failure()
            raise NetworkError(f"ASYNC POST request failed: {e}")
