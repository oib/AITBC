"""
Type tests for rate limiting utilities
Uses mypy's test framework to verify type annotations are correct
"""
from collections.abc import Callable
from typing import Any

from fastapi import Request, Response
from starlette.types import ASGIApp

from aitbc.rate_limiting import (
    RateLimitMiddleware,
    get_rate_limit_headers,
    get_rate_limiter,
    rate_limit,
    reset_rate_limit,
)
from aitbc.security_hardening import RateLimiter


def test_get_rate_limiter_return_type() -> None:
    """Test get_rate_limiter returns RateLimiter"""
    limiter: RateLimiter = get_rate_limiter("test", rate=10, per=60)
    assert limiter.rate == 10


def test_rate_limit_decorator_return_type() -> None:
    """Test rate_limit decorator returns callable"""
    @rate_limit(rate=100, per=60)
    async def endpoint(request: Request) -> dict[str, str]:
        return {"status": "ok"}
    
    # The decorated function should be callable
    decorated: Callable[[Request], Any] = endpoint
    assert callable(decorated)


def test_rate_limit_with_key_func() -> None:
    """Test rate_limit with custom key function"""
    def custom_key(request: Request) -> str:
        return request.client.host if request.client else "unknown"
    
    @rate_limit(rate=100, per=60, key_func=custom_key)
    async def endpoint(request: Request) -> dict[str, str]:
        return {"status": "ok"}


def test_rate_limit_middleware_init() -> None:
    """Test RateLimitMiddleware initialization types"""
    app: ASGIApp = lambda scope, receive, send: None  # type: ignore
    
    middleware = RateLimitMiddleware(
        app,
        rate=100,
        per=60,
        key_func=lambda r: r.client.host if r.client else "unknown",
        error_message="Custom message"
    )
    
    assert middleware.rate == 100
    assert middleware.per == 60


def test_get_rate_limit_headers_return_type() -> None:
    """Test get_rate_limit_headers returns dict[str, str]"""
    request = Request(scope={"type": "http"})
    headers: dict[str, str] = get_rate_limit_headers(request, "test")
    assert isinstance(headers, dict)


def test_reset_rate_limit_signature() -> None:
    """Test reset_rate_limit accepts correct types"""
    # Test with specific limiter
    reset_rate_limit("127.0.0.1", "test")
    
    # Test with all limiters
    reset_rate_limit("127.0.0.1")


def test_rate_limit_decorator_preserves_function_signature() -> None:
    """Test that rate_limit decorator preserves function signature"""
    @rate_limit(rate=100, per=60)
    async def endpoint(
        request: Request,
        param1: str,
        param2: int = 42
    ) -> dict[str, Any]:
        return {"param1": param1, "param2": param2}
    
    # The decorated function should accept the same parameters
    # This is a type-level test - mypy should verify the signature is compatible


def test_rate_limit_with_sync_function() -> None:
    """Test rate_limit with synchronous function"""
    @rate_limit(rate=100, per=60)
    def sync_endpoint(request: Request) -> str:
        return "ok"


def test_rate_limit_custom_error_message_type() -> None:
    """Test rate_limit custom error message is string"""
    @rate_limit(rate=100, per=60, error_message="Custom error")
    async def endpoint(request: Request) -> dict[str, str]:
        return {"status": "ok"}


def test_rate_limit_parameters_are_optional() -> None:
    """Test rate_limit parameters have correct defaults"""
    @rate_limit()
    async def endpoint(request: Request) -> dict[str, str]:
        return {"status": "ok"}
    
    @rate_limit(rate=50)
    async def endpoint2(request: Request) -> dict[str, str]:
        return {"status": "ok"}
    
    @rate_limit(per=30)
    async def endpoint3(request: Request) -> dict[str, str]:
        return {"status": "ok"}


def test_middleware_dispatch_signature() -> None:
    """Test middleware dispatch has correct signature"""
    from collections.abc import Awaitable
    
    app: ASGIApp = lambda scope, receive, send: None  # type: ignore
    middleware = RateLimitMiddleware(app, rate=100, per=60)
    
    async def call_next(request: Request) -> Response:
        return Response()
    
    # The dispatch method should accept Request and callable
    # This is verified by mypy
