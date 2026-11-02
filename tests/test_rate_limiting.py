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


class TestRateLimiterKeyRetention:
    """RATELIMIT-KEY-RETENTION-1 (#793): keys that never come back must not
    live in the table forever, and the table has a hard cap."""

    def test_stale_keys_are_swept_without_being_queried_again(self, monkeypatch):
        from aitbc.security.rate_limiter import RateLimiter

        limiter = RateLimiter(rate=100, per=1)
        base = 10_000_000_000.0
        clock = {"now": base}
        monkeypatch.setattr("aitbc.security.rate_limiter.time.time", lambda: clock["now"])

        for i in range(50):
            limiter.is_allowed(f"ip-{i}")
        assert len(limiter._requests) == 50

        # Past the window, one unrelated call triggers the amortised sweep.
        clock["now"] = base + 2.0
        limiter.is_allowed("fresh-ip")

        assert set(limiter._requests) == {"fresh-ip"}

    def test_tracked_key_cap_evicts_stalest(self, monkeypatch):
        import aitbc.security.rate_limiter as rl_mod
        from aitbc.security.rate_limiter import RateLimiter

        monkeypatch.setattr(rl_mod, "_MAX_TRACKED_KEYS", 5)
        limiter = RateLimiter(rate=100, per=60)
        base = 10_000_000_000.0
        clock = {"now": base}
        monkeypatch.setattr("aitbc.security.rate_limiter.time.time", lambda: clock["now"])

        for i in range(5):
            clock["now"] = base + i * 0.001
            limiter.is_allowed(f"ip-{i}")
        clock["now"] = base + 1.0
        limiter.is_allowed("ip-new")

        assert len(limiter._requests) <= 5
        assert "ip-new" in limiter._requests
        assert "ip-0" not in limiter._requests  # stalest evicted first

    def test_is_allowed_and_get_remaining_unchanged(self):
        from aitbc.security.rate_limiter import RateLimiter

        limiter = RateLimiter(rate=2, per=60)
        assert limiter.is_allowed("k") is True
        assert limiter.is_allowed("k") is True
        assert limiter.is_allowed("k") is False
        assert limiter.get_remaining("k") == 0
        assert limiter.get_remaining("other") == 2
