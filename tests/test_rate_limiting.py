"""
Tests for rate limiting utilities
"""

from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException, Request
from starlette.responses import Response

from aitbc.rate_limiting import (
    RateLimitMiddleware,
    get_rate_limit_headers,
    get_rate_limiter,
    rate_limit,
    reset_rate_limit,
)


class TestGetRateLimiter:
    """Tests for get_rate_limiter function"""

    def test_get_rate_limiter_new(self):
        """Test get_rate_limiter creates new limiter"""
        limiter = get_rate_limiter("test", rate=10, per=60)

        assert limiter.rate == 10
        assert limiter.per == 60

    def test_get_rate_limiter_cached(self):
        """Test get_rate_limiter returns cached limiter"""
        limiter1 = get_rate_limiter("test", rate=10, per=60)
        limiter2 = get_rate_limiter("test", rate=20, per=30)

        # Should return the same instance
        assert limiter1 is limiter2
        # Original values preserved
        assert limiter2.rate == 10
        assert limiter2.per == 60


class TestRateLimitDecorator:
    """Tests for rate_limit decorator"""

    @pytest.mark.asyncio
    async def test_rate_limit_within_limit(self):
        """Test rate_limit allows requests within limit"""

        @rate_limit(rate=5, per=60)
        async def test_endpoint(request: Request):
            return {"status": "ok"}

        request = Mock(spec=Request)
        request.client = Mock(host="127.0.0.1")
        request.url = Mock(path="/test")

        for _ in range(5):
            result = await test_endpoint(request)
            assert result == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_rate_limit_exceeded(self):
        """Test rate_limit blocks requests exceeding limit"""

        @rate_limit(rate=2, per=60)
        async def test_endpoint(request: Request):
            return {"status": "ok"}

        request = Mock(spec=Request)
        request.client = Mock(host="127.0.0.1")
        request.url = Mock(path="/test")

        # First 2 requests should succeed
        await test_endpoint(request)
        await test_endpoint(request)

        # Third request should fail
        with pytest.raises(HTTPException) as exc_info:
            await test_endpoint(request)

        assert exc_info.value.status_code == 429
        assert "Rate limit exceeded" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_rate_limit_custom_key_func(self):
        """Test rate_limit with custom key function"""

        def custom_key(request: Request) -> str:
            return request.headers.get("X-API-Key", "unknown")

        @rate_limit(rate=2, per=60, key_func=custom_key)
        async def test_endpoint(request: Request):
            return {"status": "ok"}

        request = Mock(spec=Request)
        request.client = Mock(host="127.0.0.1")
        request.url = Mock(path="/test")
        request.headers = {"X-API-Key": "key1"}

        # 2 requests with same key should succeed
        await test_endpoint(request)
        await test_endpoint(request)

        # Third should fail
        with pytest.raises(HTTPException):
            await test_endpoint(request)

    @pytest.mark.asyncio
    async def test_rate_limit_no_request(self):
        """Test rate_limit without request skips limiting"""

        @rate_limit(rate=2, per=60)
        async def test_endpoint():
            return {"status": "ok"}

        # Should succeed even without request
        result = await test_endpoint()
        assert result == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_rate_limit_custom_error_message(self):
        """Test rate_limit with custom error message"""

        @rate_limit(rate=1, per=60, error_message="Custom limit message")
        async def test_endpoint(request: Request):
            return {"status": "ok"}

        request = Mock(spec=Request)
        request.client = Mock(host="127.0.0.1")
        request.url = Mock(path="/test")

        await test_endpoint(request)

        with pytest.raises(HTTPException) as exc_info:
            await test_endpoint(request)

        assert exc_info.value.detail == "Custom limit message"


class TestRateLimitMiddleware:
    """Tests for RateLimitMiddleware"""

    @pytest.mark.asyncio
    async def test_middleware_within_limit(self):
        """Test middleware allows requests within limit"""
        app = Mock()
        middleware = RateLimitMiddleware(app, rate=5, per=60)

        request = Mock(spec=Request)
        request.client = Mock(host="127.0.0.1")
        request.url = Mock(path="/test")

        call_next = AsyncMock()
        response = Mock(spec=Response)
        call_next.return_value = response

        for _ in range(5):
            result = await middleware.dispatch(request, call_next)
            assert result == response

    @pytest.mark.asyncio
    async def test_middleware_exceeded(self):
        """Test middleware blocks requests exceeding limit"""
        app = Mock()
        middleware = RateLimitMiddleware(app, rate=2, per=60)

        request = Mock(spec=Request)
        request.client = Mock(host="127.0.0.1")
        request.url = Mock(path="/test")

        call_next = AsyncMock()
        response = Mock(spec=Response)
        call_next.return_value = response

        # First 2 requests should succeed
        await middleware.dispatch(request, call_next)
        await middleware.dispatch(request, call_next)

        # Third request should fail
        result = await middleware.dispatch(request, call_next)

        assert result.status_code == 429
        assert b"Rate limit exceeded" in result.body

    @pytest.mark.asyncio
    async def test_middleware_custom_key_func(self):
        """Test middleware with custom key function"""

        def custom_key(request: Request) -> str:
            return request.headers.get("X-API-Key", "unknown")

        app = Mock()
        middleware = RateLimitMiddleware(app, rate=2, per=60, key_func=custom_key)

        request = Mock(spec=Request)
        request.client = Mock(host="127.0.0.1")
        request.headers = {"X-API-Key": "key1"}

        call_next = AsyncMock()
        response = Mock(spec=Response)
        call_next.return_value = response

        # 2 requests with same key should succeed
        await middleware.dispatch(request, call_next)
        await middleware.dispatch(request, call_next)

        # Third should fail
        result = await middleware.dispatch(request, call_next)
        assert result.status_code == 429

    @pytest.mark.asyncio
    async def test_middleware_no_client(self):
        """Test middleware handles requests without client"""
        app = Mock()
        middleware = RateLimitMiddleware(app, rate=2, per=60)

        request = Mock(spec=Request)
        request.client = None

        call_next = AsyncMock()
        response = Mock(spec=Response)
        call_next.return_value = response

        # Should use "unknown" as key
        result = await middleware.dispatch(request, call_next)
        assert result == response


class TestGetRateLimitHeaders:
    """Tests for get_rate_limit_headers"""

    def test_get_rate_limit_headers_existing_limiter(self):
        """Test get_rate_limit_headers with existing limiter"""
        get_rate_limiter("test", rate=10, per=60)

        request = Mock(spec=Request)
        request.client = Mock(host="127.0.0.1")

        headers = get_rate_limit_headers(request, "test")

        assert headers["X-RateLimit-Limit"] == "10"
        assert headers["X-RateLimit-Reset"] == "60"
        assert "X-RateLimit-Remaining" in headers

    def test_get_rate_limit_headers_nonexistent_limiter(self):
        """Test get_rate_limit_headers with nonexistent limiter"""
        request = Mock(spec=Request)
        request.client = Mock(host="127.0.0.1")

        headers = get_rate_limit_headers(request, "nonexistent")

        assert headers == {}


class TestResetRateLimit:
    """Tests for reset_rate_limit"""

    def test_reset_rate_limit_specific_limiter(self):
        """Test reset_rate_limit for specific limiter"""
        limiter = get_rate_limiter("test", rate=2, per=60)

        # Make a request
        limiter.is_allowed("127.0.0.1")

        # Reset
        reset_rate_limit("127.0.0.1", "test")

        # Should be allowed again
        assert limiter.is_allowed("127.0.0.1")

    def test_reset_rate_limit_all_limiters(self):
        """Test reset_rate_limit for all limiters"""
        limiter1 = get_rate_limiter("test1", rate=2, per=60)
        limiter2 = get_rate_limiter("test2", rate=2, per=60)

        # Make requests
        limiter1.is_allowed("127.0.0.1")
        limiter2.is_allowed("127.0.0.1")

        # Reset all
        reset_rate_limit("127.0.0.1")

        # Both should be allowed again
        assert limiter1.is_allowed("127.0.0.1")
        assert limiter2.is_allowed("127.0.0.1")
