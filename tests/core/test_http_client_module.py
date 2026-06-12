"""
Tests for AITBC HTTP client module (network/http_client.py)
This module has 11% coverage and 370 statements.
"""

import asyncio
import importlib.util
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

# Load module directly by file path to avoid namespace conflicts
def load_module_from_path(module_name, file_path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

http_client = load_module_from_path(
    "aitbc.network.http_client",
    Path("/opt/aitbc/aitbc/network/http_client.py")
)


# ============================================================================
# AITBCHTTPClient Tests
# ============================================================================

class TestAITBCHTTPClient:
    """Test AITBCHTTPClient class"""

    def test_client_initialization(self):
        client = http_client.AITBCHTTPClient(
            base_url="https://api.example.com",
            timeout=30,
            headers={"Authorization": "Bearer token"},
            max_retries=3
        )
        assert client.base_url == "https://api.example.com"
        assert client.timeout == 30
        assert client.headers == {"Authorization": "Bearer token"}
        assert client.max_retries == 3
        assert client.enable_cache is False
        assert client.enable_logging is False
        assert client._failure_count == 0
        assert client._circuit_open is False

    def test_client_initialization_defaults(self):
        client = http_client.AITBCHTTPClient()
        assert client.base_url == ""
        assert client.timeout == 30
        assert client.headers == {}
        assert client.max_retries == 3
        assert client.enable_cache is False
        assert client.cache_ttl == 300

    def test_client_initialization_with_cache(self):
        client = http_client.AITBCHTTPClient(
            enable_cache=True,
            cache_ttl=600
        )
        assert client.enable_cache is True
        assert client.cache_ttl == 600

    def test_client_initialization_with_circuit_breaker(self):
        client = http_client.AITBCHTTPClient(
            circuit_breaker_threshold=10
        )
        assert client.circuit_breaker_threshold == 10

    def test_client_initialization_with_rate_limit(self):
        client = http_client.AITBCHTTPClient(
            rate_limit=100
        )
        assert client.rate_limit == 100

    def test_build_url_with_base(self):
        client = http_client.AITBCHTTPClient(base_url="https://api.example.com")
        url = client._build_url("/users")
        assert url == "https://api.example.com/users"

    def test_build_url_without_base(self):
        client = http_client.AITBCHTTPClient()
        url = client._build_url("/users")
        assert url == "/users"

    def test_build_url_with_full_url(self):
        client = http_client.AITBCHTTPClient(base_url="https://api.example.com")
        url = client._build_url("https://other.com/users")
        assert url == "https://other.com/users"

    def test_build_url_trailing_slash(self):
        client = http_client.AITBCHTTPClient(base_url="https://api.example.com/")
        assert client.base_url == "https://api.example.com"

    def test_circuit_breaker_closed(self):
        client = http_client.AITBCHTTPClient()
        # Should not raise
        client._check_circuit_breaker()

    def test_circuit_breaker_open(self):
        client = http_client.AITBCHTTPClient()
        client._circuit_open = True
        client._circuit_open_time = datetime.now()
        
        with pytest.raises(http_client.CircuitBreakerOpenError):
            client._check_circuit_breaker()

    def test_record_failure(self):
        client = http_client.AITBCHTTPClient(circuit_breaker_threshold=3)
        client._record_failure()
        assert client._failure_count == 1
        assert client._circuit_open is False

    def test_record_failure_opens_circuit(self):
        client = http_client.AITBCHTTPClient(circuit_breaker_threshold=3)
        client._failure_count = 2
        client._record_failure()
        assert client._failure_count == 3
        assert client._circuit_open is True
        assert client._circuit_open_time is not None

    def test_rate_limit_not_set(self):
        client = http_client.AITBCHTTPClient()
        # Should not raise
        client._check_rate_limit()

    def test_rate_limit_not_exceeded(self):
        client = http_client.AITBCHTTPClient(rate_limit=10)
        client._request_times = [datetime.now()]
        # Should not raise
        client._check_rate_limit()

    def test_rate_limit_exceeded(self):
        client = http_client.AITBCHTTPClient(rate_limit=2)
        client._request_times = [datetime.now(), datetime.now()]
        
        with pytest.raises(http_client.RateLimitError):
            client._check_rate_limit()

    def test_record_request(self):
        client = http_client.AITBCHTTPClient(rate_limit=10)
        client._record_request()
        assert len(client._request_times) == 1

    def test_record_request_no_rate_limit(self):
        client = http_client.AITBCHTTPClient()
        client._record_request()
        assert len(client._request_times) == 0

    def test_get_cache_key_no_params(self):
        client = http_client.AITBCHTTPClient()
        key = client._get_cache_key("https://api.example.com/users")
        assert key == "https://api.example.com/users"

    def test_get_cache_key_with_params(self):
        client = http_client.AITBCHTTPClient()
        key = client._get_cache_key("https://api.example.com/users", {"page": 1, "limit": 10})
        assert "https://api.example.com/users:" in key
        assert len(key) > 50  # SHA256 hash

    def test_get_cache_disabled(self):
        client = http_client.AITBCHTTPClient(enable_cache=False)
        result = client._get_cache("test_key")
        assert result is None

    def test_get_cache_miss(self):
        client = http_client.AITBCHTTPClient(enable_cache=True)
        result = client._get_cache("test_key")
        assert result is None

    def test_get_cache_hit(self):
        client = http_client.AITBCHTTPClient(enable_cache=True)
        client._cache["test_key"] = ({"data": "value"}, datetime.now())
        result = client._get_cache("test_key")
        assert result == {"data": "value"}

    def test_get_cache_expired(self):
        client = http_client.AITBCHTTPClient(enable_cache=True, cache_ttl=0.01)
        import time
        client._cache["test_key"] = ({"data": "value"}, datetime.now())
        time.sleep(0.02)
        result = client._get_cache("test_key")
        assert result is None
        assert "test_key" not in client._cache

    def test_set_cache_disabled(self):
        client = http_client.AITBCHTTPClient(enable_cache=False)
        client._set_cache("test_key", {"data": "value"})
        assert "test_key" not in client._cache

    def test_set_cache_enabled(self):
        client = http_client.AITBCHTTPClient(enable_cache=True)
        client._set_cache("test_key", {"data": "value"})
        assert "test_key" in client._cache

    @patch('requests.Session.get')
    def test_get_success(self, mock_get):
        mock_response = Mock()
        mock_response.json.return_value = {"result": "success"}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        client = http_client.AITBCHTTPClient(base_url="https://api.example.com")
        result = client.get("/test")
        
        assert result == {"result": "success"}
        mock_get.assert_called_once()

    @patch('requests.Session.get')
    def test_get_with_cache_hit(self, mock_get):
        client = http_client.AITBCHTTPClient(base_url="https://api.example.com", enable_cache=True)
        client._cache["https://api.example.com/test"] = ({"cached": True}, datetime.now())
        
        result = client.get("/test")
        
        assert result == {"cached": True}
        mock_get.assert_not_called()

    @patch('requests.Session.get')
    def test_get_with_cache_miss(self, mock_get):
        mock_response = Mock()
        mock_response.json.return_value = {"result": "success"}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        client = http_client.AITBCHTTPClient(base_url="https://api.example.com", enable_cache=True)
        result = client.get("/test")
        
        assert result == {"result": "success"}
        assert "https://api.example.com/test" in client._cache

    @patch('requests.Session.get')
    def test_get_circuit_breaker_open(self, mock_get):
        client = http_client.AITBCHTTPClient(base_url="https://api.example.com")
        client._circuit_open = True
        client._circuit_open_time = datetime.now()
        
        with pytest.raises(http_client.CircuitBreakerOpenError):
            client.get("/test")

    @patch('requests.Session.get')
    def test_get_rate_limit_exceeded(self, mock_get):
        client = http_client.AITBCHTTPClient(base_url="https://api.example.com", rate_limit=1)
        client._request_times = [datetime.now()]
        
        with pytest.raises(http_client.RateLimitError):
            client.get("/test")

    @patch('requests.Session.get')
    def test_get_with_params(self, mock_get):
        mock_response = Mock()
        mock_response.json.return_value = {"result": "success"}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        client = http_client.AITBCHTTPClient(base_url="https://api.example.com")
        result = client.get("/test", params={"page": 1})
        
        assert result == {"result": "success"}
        mock_get.assert_called_once()

    @patch('requests.Session.get')
    def test_get_with_headers(self, mock_get):
        mock_response = Mock()
        mock_response.json.return_value = {"result": "success"}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        client = http_client.AITBCHTTPClient(base_url="https://api.example.com")
        result = client.get("/test", headers={"Custom": "Header"})
        
        assert result == {"result": "success"}

    @patch('requests.Session.post')
    def test_post_success(self, mock_post):
        mock_response = Mock()
        mock_response.json.return_value = {"result": "success"}
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        client = http_client.AITBCHTTPClient(base_url="https://api.example.com")
        result = client.post("/test", json={"data": "value"})
        
        assert result == {"result": "success"}
        mock_post.assert_called_once()

    @patch('requests.Session.post')
    def test_post_circuit_breaker_open(self, mock_post):
        client = http_client.AITBCHTTPClient(base_url="https://api.example.com")
        client._circuit_open = True
        client._circuit_open_time = datetime.now()
        
        with pytest.raises(http_client.CircuitBreakerOpenError):
            client.post("/test")

    @patch('requests.Session.put')
    def test_put_success(self, mock_put):
        mock_response = Mock()
        mock_response.json.return_value = {"result": "success"}
        mock_response.raise_for_status = Mock()
        mock_put.return_value = mock_response

        client = http_client.AITBCHTTPClient(base_url="https://api.example.com")
        result = client.put("/test", json={"data": "value"})
        
        assert result == {"result": "success"}
        mock_put.assert_called_once()

    @patch('requests.Session.delete')
    def test_delete_success(self, mock_delete):
        mock_response = Mock()
        mock_response.json.return_value = {"result": "success"}
        mock_response.raise_for_status = Mock()
        mock_delete.return_value = mock_response

        client = http_client.AITBCHTTPClient(base_url="https://api.example.com")
        result = client.delete("/test")
        
        assert result == {"result": "success"}
        mock_delete.assert_called_once()

    @patch('requests.Session.delete')
    def test_delete_empty_response(self, mock_delete):
        mock_response = Mock()
        mock_response.content = b""
        mock_response.raise_for_status = Mock()
        mock_delete.return_value = mock_response

        client = http_client.AITBCHTTPClient(base_url="https://api.example.com")
        result = client.delete("/test")
        
        assert result == {}

    def test_context_manager(self):
        client = http_client.AITBCHTTPClient(base_url="https://api.example.com")
        with client:
            assert client is not None
        # Session should be closed after context exit

    def test_close(self):
        client = http_client.AITBCHTTPClient(base_url="https://api.example.com")
        client.close()
        # Should not raise


# ============================================================================
# AsyncAITBCHTTPClient Tests
# ============================================================================

class TestAsyncAITBCHTTPClient:
    """Test AsyncAITBCHTTPClient class"""

    def test_async_client_initialization(self):
        client = http_client.AsyncAITBCHTTPClient(
            base_url="https://api.example.com",
            timeout=30,
            headers={"Authorization": "Bearer token"},
            max_retries=3
        )
        assert client.base_url == "https://api.example.com"
        assert client.timeout == 30
        assert client.headers == {"Authorization": "Bearer token"}
        assert client.max_retries == 3
        assert client._client is None

    def test_async_client_initialization_defaults(self):
        client = http_client.AsyncAITBCHTTPClient()
        assert client.base_url == ""
        assert client.timeout == 30
        assert client.headers == {}
        assert client.max_retries == 3

    @pytest.mark.asyncio
    async def test_async_context_manager(self):
        # Skip if httpx is not available
        try:
            import httpx
        except ImportError:
            pytest.skip("httpx not available")
        
        client = http_client.AsyncAITBCHTTPClient(base_url="https://api.example.com")
        async with client:
            assert client._client is not None

    def test_async_build_url(self):
        client = http_client.AsyncAITBCHTTPClient(base_url="https://api.example.com")
        url = client._build_url("/users")
        assert url == "https://api.example.com/users"

    def test_async_circuit_breaker_open(self):
        client = http_client.AsyncAITBCHTTPClient()
        client._circuit_open = True
        client._circuit_open_time = datetime.now()
        
        with pytest.raises(http_client.CircuitBreakerOpenError):
            client._check_circuit_breaker()

    def test_async_record_failure(self):
        client = http_client.AsyncAITBCHTTPClient(circuit_breaker_threshold=3)
        client._record_failure()
        assert client._failure_count == 1

    def test_async_rate_limit_exceeded(self):
        client = http_client.AsyncAITBCHTTPClient(rate_limit=2)
        client._request_times = [datetime.now(), datetime.now()]
        
        with pytest.raises(http_client.RateLimitError):
            client._check_rate_limit()

    def test_async_get_cache_key(self):
        client = http_client.AsyncAITBCHTTPClient()
        key = client._get_cache_key("https://api.example.com/users", {"page": 1})
        assert "https://api.example.com/users:" in key

    def test_async_get_cache_hit(self):
        client = http_client.AsyncAITBCHTTPClient(enable_cache=True)
        client._cache["test_key"] = ({"cached": True}, datetime.now())
        result = client._get_cache("test_key")
        assert result == {"cached": True}

    def test_async_set_cache(self):
        client = http_client.AsyncAITBCHTTPClient(enable_cache=True)
        client._set_cache("test_key", {"data": "value"})
        assert "test_key" in client._cache

    @pytest.mark.asyncio
    async def test_async_get_not_initialized(self):
        client = http_client.AsyncAITBCHTTPClient()
        with pytest.raises(RuntimeError, match="not initialized"):
            await client.async_get("/test")

    @pytest.mark.asyncio
    async def test_async_post_not_initialized(self):
        client = http_client.AsyncAITBCHTTPClient()
        with pytest.raises(RuntimeError, match="not initialized"):
            await client.async_post("/test")
