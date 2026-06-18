"""Tests for aitbc.network.http_client"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
import requests

from aitbc.exceptions import CircuitBreakerOpenError, RateLimitError, RetryError
from aitbc.network import AITBCHTTPClient


class TestInit:
    def test_init_defaults(self):
        client = AITBCHTTPClient()
        assert client.base_url == ""
        assert client.timeout == 30
        assert client.headers == {}
        assert client.max_retries == 3

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
        assert client.max_retries == 5
        assert client.enable_cache is True
        assert client.cache_ttl == 60
        assert client.enable_logging is True
        assert client.circuit_breaker_threshold == 3
        assert client.rate_limit == 100

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
        client = AITBCHTTPClient()
        client._check_circuit_breaker()

    def test_opens_after_threshold(self):
        client = AITBCHTTPClient(circuit_breaker_threshold=2)
        client._record_failure()
        client._record_failure()
        with pytest.raises(CircuitBreakerOpenError):
            client._check_circuit_breaker()

    def test_resets_after_timeout(self):
        client = AITBCHTTPClient(circuit_breaker_threshold=1)
        client._record_failure()
        with pytest.raises(CircuitBreakerOpenError):
            client._check_circuit_breaker()
        client._circuit_open_time = datetime.now() - timedelta(seconds=120)
        client._check_circuit_breaker()
        assert client._circuit_open is False


class TestRateLimit:
    def test_no_limit(self):
        client = AITBCHTTPClient()
        client._check_rate_limit()

    def test_limit_not_exceeded(self):
        client = AITBCHTTPClient(rate_limit=10)
        client._check_rate_limit()

    def test_limit_exceeded(self):
        client = AITBCHTTPClient(rate_limit=1)
        client._record_request()
        with pytest.raises(RateLimitError):
            client._check_rate_limit()

    def test_old_requests_expired(self):
        client = AITBCHTTPClient(rate_limit=1)
        client._request_times.append(datetime.now() - timedelta(seconds=120))
        client._check_rate_limit()

    def test_record_request(self):
        client = AITBCHTTPClient(rate_limit=10)
        client._record_request()
        assert len(client._request_times) == 1


class TestCache:
    def test_cache_key_no_params(self):
        client = AITBCHTTPClient()
        assert client._get_cache_key("https://api.example.com") == "https://api.example.com"

    def test_cache_key_with_params(self):
        client = AITBCHTTPClient()
        key = client._get_cache_key("https://api.example.com", {"page": 1})
        assert key.startswith("https://api.example.com:")

    def test_get_cache_disabled(self):
        client = AITBCHTTPClient()
        assert client._get_cache("key") is None

    def test_get_cache_miss(self):
        client = AITBCHTTPClient(enable_cache=True)
        assert client._get_cache("key") is None

    def test_get_cache_hit(self):
        client = AITBCHTTPClient(enable_cache=True, cache_ttl=300)
        client._cache["key"] = ({"data": 1}, datetime.now())
        assert client._get_cache("key") == {"data": 1}

    def test_get_cache_expired(self):
        client = AITBCHTTPClient(enable_cache=True, cache_ttl=0)
        client._cache["key"] = ({"data": 1}, datetime.now() - timedelta(seconds=10))
        assert client._get_cache("key") is None
        assert "key" not in client._cache

    def test_set_cache(self):
        client = AITBCHTTPClient(enable_cache=True)
        client._set_cache("key", {"data": 1})
        assert "key" in client._cache

    def test_set_cache_disabled(self):
        client = AITBCHTTPClient()
        client._set_cache("key", {"data": 1})
        assert "key" not in client._cache


class TestRetryRequest:
    def test_success_first_attempt(self):
        client = AITBCHTTPClient()
        mock_func = MagicMock(return_value={"ok": True})
        result = client._retry_request(mock_func)
        assert result == {"ok": True}
        assert mock_func.call_count == 1

    def test_retry_then_success(self):
        client = AITBCHTTPClient(max_retries=2)
        mock_func = MagicMock(side_effect=[requests.RequestException("fail"), {"ok": True}])
        with patch("time.sleep"):
            result = client._retry_request(mock_func)
        assert result == {"ok": True}
        assert mock_func.call_count == 2

    def test_4xx_no_retry(self):
        client = AITBCHTTPClient(max_retries=2)
        resp = MagicMock()
        resp.status_code = 404
        err = requests.HTTPError("Not found")
        err.response = resp
        mock_func = MagicMock(side_effect=err)
        with pytest.raises(requests.HTTPError):
            client._retry_request(mock_func)

    def test_all_attempts_fail(self):
        client = AITBCHTTPClient(max_retries=1)
        mock_func = MagicMock(side_effect=requests.RequestException("fail"))
        with patch("aitbc.network.http_client.time.sleep"):
            with pytest.raises(RetryError):
                client._retry_request(mock_func)


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
        client._cache["https://api.example.com/test"] = ({"cached": True}, datetime.now())
        result = client.get("/test")
        assert result == {"cached": True}

    def test_get_network_error(self):
        client = AITBCHTTPClient(base_url="https://api.example.com")
        with patch.object(client.session, "get", side_effect=requests.RequestException("fail")):
            with patch("aitbc.network.http_client.time.sleep"):
                with pytest.raises(RetryError):
                    client.get("/test")

    def test_get_circuit_open(self):
        client = AITBCHTTPClient(base_url="https://api.example.com", circuit_breaker_threshold=1)
        client._record_failure()
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
            with patch("aitbc.network.http_client.time.sleep"):
                with pytest.raises(RetryError):
                    client.post("/test", json={"name": "x"})

    def test_put_success(self):
        client = AITBCHTTPClient(base_url="https://api.example.com")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"updated": True}
        with patch.object(client.session, "put", return_value=mock_resp):
            result = client.put("/test", json={"name": "x"})
        assert result == {"updated": True}

    def test_put_network_error(self):
        client = AITBCHTTPClient(base_url="https://api.example.com")
        with patch.object(client.session, "put", side_effect=requests.RequestException("fail")):
            with patch("aitbc.network.http_client.time.sleep"):
                with pytest.raises(RetryError):
                    client.put("/test", json={"name": "x"})

    def test_delete_success(self):
        client = AITBCHTTPClient(base_url="https://api.example.com")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"deleted": True}
        mock_resp.content = b'{"deleted": true}'
        with patch.object(client.session, "delete", return_value=mock_resp):
            result = client.delete("/test")
        assert result == {"deleted": True}

    def test_delete_empty_response(self):
        client = AITBCHTTPClient(base_url="https://api.example.com")
        mock_resp = MagicMock()
        mock_resp.content = b""
        with patch.object(client.session, "delete", return_value=mock_resp):
            result = client.delete("/test")
        assert result == {}

    def test_delete_network_error(self):
        client = AITBCHTTPClient(base_url="https://api.example.com")
        with patch.object(client.session, "delete", side_effect=requests.RequestException("fail")):
            with patch("aitbc.network.http_client.time.sleep"):
                with pytest.raises(RetryError):
                    client.delete("/test")


class TestContextManager:
    def test_context_manager(self):
        with AITBCHTTPClient() as client:
            assert isinstance(client, AITBCHTTPClient)

    def test_close(self):
        client = AITBCHTTPClient()
        with patch.object(client.session, "close") as mock_close:
            client.close()
            mock_close.assert_called_once()
