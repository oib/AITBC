"""Tests for aitbc.network.http_client and new modular components"""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
import requests

from aitbc.exceptions import CircuitBreakerOpenError, NetworkError, RateLimitError, RetryError
from aitbc.network import AITBCHTTPClient
from aitbc.network.circuit_breaker import CircuitBreaker
from aitbc.network.rate_limiter import RateLimiter
from aitbc.network.cache_layer import CacheLayer
from aitbc.network.retry_policy import RetryPolicy


class TestInit:
    def test_init_defaults(self):
        client = AITBCHTTPClient()
        assert client.base_url == ""
        assert client.timeout == 30
        assert client.headers == {}

    def test_init_custom(self):
        client = AITBCHTTPClient(
            base_url="https://api.example.com/",
            timeout=10,
            headers={"X-Auth": "token"},
            max_retries=5,
            enable_cache=True,
            cache_ttl=60,
            enable_logging=True,
            circuit_breaker_threshold=3,
            rate_limit=100,
        )
        assert client.base_url == "https://api.example.com"
        assert client.timeout == 10
        assert client.headers == {"X-Auth": "token"}
        assert client.enable_logging is True
        assert client.circuit_breaker.threshold == 3
        assert client.rate_limiter.rate_limit == 100

    def test_base_url_trailing_slash(self):
        client = AITBCHTTPClient(base_url="https://api.example.com/")
        assert client.base_url == "https://api.example.com"


class TestBuildUrl:
    def test_full_url(self):
        client = AITBCHTTPClient(base_url="https://api.example.com")
        assert client._build_url("https://other.com/path") == "https://other.com/path"

    def test_relative_endpoint(self):
        client = AITBCHTTPClient(base_url="https://api.example.com")
        assert client._build_url("/users") == "https://api.example.com/users"

    def test_relative_no_slash(self):
        client = AITBCHTTPClient(base_url="https://api.example.com")
        assert client._build_url("users") == "https://api.example.com/users"

    def test_empty_base(self):
        client = AITBCHTTPClient()
        assert client._build_url("/users") == "/users"


class TestCircuitBreaker:
    def test_closed_by_default(self):
        cb = CircuitBreaker()
        cb.check()  # should not raise

    def test_opens_after_threshold(self):
        cb = CircuitBreaker(threshold=2)
        cb.record_failure()
        cb.record_failure()
        with pytest.raises(CircuitBreakerOpenError):
            cb.check()

    def test_resets_after_timeout(self):
        cb = CircuitBreaker(threshold=1, timeout=0.01)
        cb.record_failure()
        with pytest.raises(CircuitBreakerOpenError):
            cb.check()
        # Wait for timeout
        import time
        time.sleep(0.02)
        cb.check()  # should reset and not raise
        assert cb.is_open is False

    def test_record_success(self):
        cb = CircuitBreaker(threshold=2)
        cb.record_failure()
        cb.record_success()
        assert cb.failure_count == 0


class TestRateLimit:
    def test_no_limit(self):
        rl = RateLimiter()
        rl.check()  # should not raise

    def test_limit_not_exceeded(self):
        rl = RateLimiter(rate_limit=10)
        rl.check()  # should not raise

    def test_limit_exceeded(self):
        rl = RateLimiter(rate_limit=1)
        rl.record_request()
        with pytest.raises(RateLimitError):
            rl.check()

    def test_old_requests_expired(self):
        rl = RateLimiter(rate_limit=1, window_seconds=0.01)
        rl.record_request()
        import time
        time.sleep(0.02)
        rl.check()  # old request expired, should not raise

    def test_record_request(self):
        rl = RateLimiter(rate_limit=10)
        rl.record_request()
        state = rl.get_state()
        assert state["current_requests"] == 1


class TestCacheLayer:
    def test_cache_key_no_params(self):
        cache = CacheLayer()
        assert cache.get_cache_key("https://api.example.com") == "https://api.example.com"

    def test_cache_key_with_params(self):
        cache = CacheLayer()
        key = cache.get_cache_key("https://api.example.com", {"page": 1})
        assert key.startswith("https://api.example.com:")

    def test_get_cache_disabled(self):
        cache = CacheLayer()
        assert cache.get("key") is None

    def test_get_cache_miss(self):
        cache = CacheLayer(enable=True)
        assert cache.get("key") is None

    def test_get_cache_hit(self):
        cache = CacheLayer(enable=True, ttl=300)
        cache.set("key", {"data": 1})
        assert cache.get("key") == {"data": 1}

    def test_get_cache_expired(self):
        cache = CacheLayer(enable=True, ttl=0)
        cache_key = cache.get_cache_key("key")
        cache.cache[cache_key] = ({"data": 1}, datetime.now(UTC) - timedelta(seconds=10))
        assert cache.get(cache_key) is None

    def test_set_cache(self):
        cache = CacheLayer(enable=True)
        cache.set("key", {"data": 1})
        assert cache.get("key") == {"data": 1}

    def test_set_cache_disabled(self):
        cache = CacheLayer()
        cache.set("key", {"data": 1})
        assert cache.get("key") is None


class TestRetryPolicy:
    def test_success_first_attempt(self):
        policy = RetryPolicy(max_retries=3)
        mock_func = MagicMock(return_value={"ok": True})
        result = policy.execute(mock_func)
        assert result == {"ok": True}
        assert mock_func.call_count == 1

    def test_retry_then_success(self):
        policy = RetryPolicy(max_retries=2)
        mock_func = MagicMock(side_effect=[requests.RequestException("fail"), {"ok": True}])
        with patch("time.sleep"):
            result = policy.execute(mock_func)
        assert result == {"ok": True}
        assert mock_func.call_count == 2

    def test_all_attempts_fail(self):
        policy = RetryPolicy(max_retries=1)
        mock_func = MagicMock(side_effect=requests.RequestException("fail"))
        with patch("time.sleep"):
            with pytest.raises(RetryError):
                policy.execute(mock_func)


class TestHTTPMethods:
    def test_get_success(self):
        client = AITBCHTTPClient(base_url="https://api.example.com")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": 1}
        with patch.object(client.session, "get", return_value=mock_resp):
            result = client.get("/test")
        assert result == {"data": 1}

    def test_get_from_cache(self):
        client = AITBCHTTPClient(base_url="https://api.example.com", enable_cache=True)
        cache_key = client.cache.get_cache_key("https://api.example.com/test")
        client.cache.set(cache_key, {"cached": True})
        with patch.object(client.session, "get") as mock_get:
            result = client.get("/test")
        assert result == {"cached": True}
        mock_get.assert_not_called()

    def test_get_network_error(self):
        client = AITBCHTTPClient(base_url="https://api.example.com")
        with patch.object(client.session, "get", side_effect=requests.RequestException("fail")):
            with patch("aitbc.network.retry_policy.time.sleep"):
                with pytest.raises(NetworkError):
                    client.get("/test")

    def test_get_circuit_open(self):
        client = AITBCHTTPClient(base_url="https://api.example.com", circuit_breaker_threshold=1)
        client.circuit_breaker.record_failure()
        with pytest.raises(CircuitBreakerOpenError):
            client.get("/test")

    def test_post_success(self):
        client = AITBCHTTPClient(base_url="https://api.example.com")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"id": 1}
        with patch.object(client.session, "post", return_value=mock_resp):
            result = client.post("/test", json={"name": "x"})
        assert result == {"id": 1}

    def test_post_network_error(self):
        client = AITBCHTTPClient(base_url="https://api.example.com")
        with patch.object(client.session, "post", side_effect=requests.RequestException("fail")):
            with patch("aitbc.network.retry_policy.time.sleep"):
                with pytest.raises(NetworkError):
                    client.post("/test", json={"name": "x"})

    def test_put_success(self):
        client = AITBCHTTPClient(base_url="https://api.example.com")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"updated": True}
        with patch.object(client.session, "put", return_value=mock_resp):
            result = client.put("/test", json={"name": "x"})
        assert result == {"updated": True}

    def test_delete_success(self):
        client = AITBCHTTPClient(base_url="https://api.example.com")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"deleted": True}
        with patch.object(client.session, "delete", return_value=mock_resp):
            result = client.delete("/test")
        assert result == {"deleted": True}

    def test_delete_network_error(self):
        client = AITBCHTTPClient(base_url="https://api.example.com")
        with patch.object(client.session, "delete", side_effect=requests.RequestException("fail")):
            with patch("aitbc.network.retry_policy.time.sleep"):
                with pytest.raises(NetworkError):
                    client.delete("/test")


class TestAsyncHTTPClient:
    @pytest.mark.skip(reason="pytest-asyncio not configured")
    async def test_async_get(self):
        from aitbc.network import AsyncAITBCHTTPClient
        client = AsyncAITBCHTTPClient(base_url="https://api.example.com")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": 1}
        with patch("httpx.AsyncClient.get", return_value=mock_resp):
            result = await client.get("/test")
        assert result == {"data": 1}
