"""
Rate limiting utilities for FastAPI applications
Provides decorators and middleware for API rate limiting
"""

import asyncio
import os
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from .aitbc_logging import get_logger
from .security import RateLimiter

logger = get_logger(__name__)
_rate_limiters: dict[str, RateLimiter] = {}

# Env gate: rate limiting is enabled by default. Set AITBC_ENABLE_RATE_LIMITING=false
# to disable for local development or CI (e.g. when flooding endpoints in tests).
_RATE_LIMITING_ENABLED = os.getenv("AITBC_ENABLE_RATE_LIMITING", "true").lower() in ("true", "1", "yes", "on")


def get_rate_limiter(name: str, rate: int = 100, per: int = 60) -> RateLimiter:
    """
    Get or create a rate limiter for a specific endpoint

    Args:
        name: Unique name for the rate limiter
        rate: Number of requests allowed per time period
        per: Time period in seconds

    Returns:
        RateLimiter instance
    """
    if name not in _rate_limiters:
        _rate_limiters[name] = RateLimiter(rate=rate, per=per)
    return _rate_limiters[name]


def _extract_request(args: tuple[Any, ...], kwargs: dict[str, Any]) -> Request | None:
    """Find the FastAPI Request object in the handler's positional or keyword args."""
    for arg in args:
        if isinstance(arg, Request):
            return arg
    for arg in kwargs.values():
        if isinstance(arg, Request):
            return arg
    return None


def _get_rate_limit_key(request: Request | None, key_func: Callable[[Request], str] | None) -> str:
    """Extract the rate limit key from the request."""
    if request is None:
        return "unknown"
    if key_func:
        return key_func(request)
    return request.client.host if request.client else "unknown"


def rate_limit(
    rate: int = 100,
    per: int = 60,
    key_func: Callable[[Request], str] | None = None,
    error_message: str = "Rate limit exceeded",
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """
    Decorator for rate limiting FastAPI endpoints.

    Uses a token-bucket algorithm via the RateLimiter class. Rate limiting is
    enabled by default; set AITBC_ENABLE_RATE_LIMITING=false to disable (e.g.
    for local development or CI).
    """
    from typing import ParamSpec

    P = ParamSpec("P")
    limiter_name = f"rl_{rate}_{per}_{id(key_func)}"
    _limiter = get_rate_limiter(limiter_name, rate=rate, per=per)

    def decorator(func: Callable[P, Any]) -> Callable[P, Any]:
        if asyncio.iscoroutinefunction(func):

            @wraps(func)
            async def wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
                if not _RATE_LIMITING_ENABLED:
                    return await func(*args, **kwargs)

                request = _extract_request(args, kwargs)
                key = _get_rate_limit_key(request, key_func)
                if not _limiter.is_allowed(key):
                    logger.warning("Rate limit exceeded for %s on %s", key, request.url.path if request else "?", stacklevel=2)
                    return Response(
                        content=f'{{"detail": "{error_message}"}}',
                        status_code=429,
                        media_type="application/json",
                        headers={"Retry-After": str(per)},
                    )
                return await func(*args, **kwargs)

            return wrapper
        else:

            @wraps(func)
            def wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
                if not _RATE_LIMITING_ENABLED:
                    return func(*args, **kwargs)

                request = _extract_request(args, kwargs)
                key = _get_rate_limit_key(request, key_func)
                if not _limiter.is_allowed(key):
                    logger.warning("Rate limit exceeded for %s on %s", key, request.url.path if request else "?", stacklevel=2)
                    return Response(
                        content=f'{{"detail": "{error_message}"}}',
                        status_code=429,
                        media_type="application/json",
                        headers={"Retry-After": str(per)},
                    )
                return func(*args, **kwargs)

            return wrapper

    return decorator


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Middleware for rate limiting all requests

    Applies rate limiting based on client IP address
    """

    def __init__(
        self,
        app: ASGIApp,
        rate: int = 100,
        per: int = 60,
        key_func: Callable[[Request], str] | None = None,
        error_message: str = "Rate limit exceeded",
    ) -> None:
        """
        Initialize rate limit middleware

        Args:
            app: ASGI application
            rate: Number of requests allowed per time period
            per: Time period in seconds
            key_func: Function to extract rate limit key from request
            error_message: Custom error message
        """
        super().__init__(app)
        self.rate = rate
        self.per = per
        self.key_func = key_func
        self.error_message = error_message
        self._limiter = RateLimiter(rate=rate, per=per)

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        """
        Process request with rate limiting

        Args:
            request: Incoming request
            call_next: Next middleware or endpoint

        Returns:
            Response
        """
        key = self.key_func(request) if self.key_func else request.client.host if request.client else "unknown"
        if not self._limiter.is_allowed(key):
            logger.warning("Rate limit exceeded for %s on %s", key, request.url.path, stacklevel=2)
            return Response(
                content=f'{{"detail": "{self.error_message}"}}',
                status_code=429,
                media_type="application/json",
                headers={"Retry-After": str(self.per)},
            )
        response = await call_next(request)
        return response


def get_rate_limit_headers(request: Request, limiter_name: str) -> dict[str, str]:
    """
    Get rate limit headers for response

    Args:
        request: Request object
        limiter_name: Name of the rate limiter

    Returns:
        Dictionary of rate limit headers
    """
    limiter = _rate_limiters.get(limiter_name)
    if not limiter:
        return {}
    key = request.client.host if request.client else "unknown"
    remaining = limiter.get_remaining(key)
    return {
        "X-RateLimit-Limit": str(limiter.rate),
        "X-RateLimit-Remaining": str(remaining),
        "X-RateLimit-Reset": str(limiter.per),
    }


def reset_rate_limit(identifier: str, limiter_name: str | None = None) -> None:
    """
    Reset rate limit for an identifier

    Args:
        identifier: Identifier to reset (e.g., IP address, user ID)
        limiter_name: Name of specific rate limiter, or None for all
    """
    if limiter_name:
        if limiter_name in _rate_limiters:
            _rate_limiters[limiter_name].reset(identifier)
    else:
        for limiter in _rate_limiters.values():
            limiter.reset(identifier)
