"""
Tests for rate limiting utilities
"""

from unittest.mock import Mock

from fastapi import Request

from aitbc.rate_limiting import (
    get_rate_limit_headers,
    get_rate_limiter,
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


class TestRateLimitMiddleware:
    """Tests for RateLimitMiddleware"""


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


class TestRateLimitingEnvironment:
    """Tests for rate limiting environment behavior"""

    def test_rate_limit_cannot_be_disabled_in_production(self, monkeypatch):
        """Test that AITBC_ENABLE_RATE_LIMITING=false is ignored in production"""
        from aitbc.rate_limiting import _is_rate_limiting_enabled

        monkeypatch.setenv("AITBC_ENABLE_RATE_LIMITING", "false")
        monkeypatch.setenv("ENVIRONMENT", "production")

        assert _is_rate_limiting_enabled() is True

    def test_rate_limit_disabled_in_non_production(self, monkeypatch):
        """Test that AITBC_ENABLE_RATE_LIMITING=false disables rate limiting outside production"""
        from aitbc.rate_limiting import _is_rate_limiting_enabled

        monkeypatch.setenv("AITBC_ENABLE_RATE_LIMITING", "false")
        monkeypatch.setenv("ENVIRONMENT", "development")

        assert _is_rate_limiting_enabled() is False
