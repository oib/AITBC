"""
Rate limiting utilities for FastAPI applications
Provides decorators and middleware for API rate limiting
"""

import asyncio
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar, cast

from fastapi import HTTPException, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from .aitbc_logging import get_logger
from .security_hardening import RateLimiter

logger = get_logger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


# Global rate limiters for different endpoints
_rate_limiters: dict[str, RateLimiter] = {}


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


def rate_limit(
    rate: int = 100,
    per: int = 60,
    key_func: Callable[[Request], str] | None = None,
    error_message: str = "Rate limit exceeded"
) -> Callable[[F], F]:
    """
    Decorator for rate limiting FastAPI endpoints

    Args:
        rate: Number of requests allowed per time period
        per: Time period in seconds
        key_func: Function to extract rate limit key from request (defaults to client IP)
        error_message: Custom error message

    Returns:
        Decorated function with rate limiting
    """
    from typing import ParamSpec

    P = ParamSpec("P")

    def decorator(func: Callable[P, Any]) -> Callable[P, Any]:
        limiter = RateLimiter(rate=rate, per=per)
        is_async = asyncio.iscoroutinefunction(func)

        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
            # Extract request from args (FastAPI passes request as first arg for dependency injection)
            request = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break

            if request is None:
                # Try to get request from kwargs
                request = kwargs.get('request')
                if is_async:
                    return await func(*args, **kwargs)
                else:
                    return func(*args, **kwargs)

            # Get rate limit key
            if key_func:
                key = key_func(request)
            else:
                key = request.client.host if request.client else "unknown"

            # Check rate limit
            if not limiter.is_allowed(key):
                logger.warning(f"Rate limit exceeded for {key} on {request.url.path}")
                raise HTTPException(
                    status_code=429,
                    detail=error_message,
                    headers={"Retry-After": str(per)}
                )

            if is_async:
                return await func(*args, **kwargs)
            else:
                return func(*args, **kwargs)

        return cast(F, wrapper)
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
        error_message: str = "Rate limit exceeded"
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

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request with rate limiting

        Args:
            request: Incoming request
            call_next: Next middleware or endpoint

        Returns:
            Response
        """
        # Get rate limit key
        if self.key_func:
            key = self.key_func(request)
        else:
            key = request.client.host if request.client else "unknown"

        # Check rate limit
        if not self._limiter.is_allowed(key):
            logger.warning(f"Rate limit exceeded for {key} on {request.url.path}")
            return Response(
                content='{"detail": "' + self.error_message + '"}',
                status_code=429,
                media_type="application/json",
                headers={"Retry-After": str(self.per)}
            )

        return await call_next(request)


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
    remaining = limiter.get_remaining_requests(key)

    return {
        "X-RateLimit-Limit": str(limiter.rate),
        "X-RateLimit-Remaining": str(remaining),
        "X-RateLimit-Reset": str(limiter.per)
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
