"""Unit tests for aitbc.network.http_pool (A3)."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from aitbc.network.http_pool import SharedHttpClient


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Reset the SharedHttpClient singleton before and after each test."""
    SharedHttpClient.reset()
    yield
    SharedHttpClient.reset()


class TestSharedHttpClientSingleton:
    def test_new_returns_same_instance(self) -> None:
        c1 = SharedHttpClient()
        c2 = SharedHttpClient()
        assert c1 is c2

    def test_reset_creates_new_instance(self) -> None:
        c1 = SharedHttpClient()
        SharedHttpClient.reset()
        c2 = SharedHttpClient()
        assert c1 is not c2


class TestSharedHttpClientLazyInit:
    @pytest.mark.asyncio
    async def test_client_not_created_until_first_request(self) -> None:
        client = SharedHttpClient()
        assert SharedHttpClient._client is None

        # Mock the AsyncClient to avoid real network calls
        with patch("aitbc.network.http_pool.httpx.AsyncClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.get = AsyncMock(return_value=MagicMock(status_code=200))
            mock_client_cls.return_value = mock_client

            await client.get("http://localhost:8006/health")
            assert SharedHttpClient._client is mock_client
            mock_client.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_client_reused_across_calls(self) -> None:
        client = SharedHttpClient()

        with patch("aitbc.network.http_pool.httpx.AsyncClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.get = AsyncMock(return_value=MagicMock(status_code=200))
            mock_client.post = AsyncMock(return_value=MagicMock(status_code=201))
            mock_client_cls.return_value = mock_client

            await client.get("http://localhost:8006/a")
            await client.post("http://localhost:8006/b", json={"x": 1})

            # Only one AsyncClient should have been created
            mock_client_cls.assert_called_once()
            mock_client.get.assert_called_once()
            mock_client.post.assert_called_once()


class TestSharedHttpClientClose:
    @pytest.mark.asyncio
    async def test_close_instance_closes_client(self) -> None:
        client = SharedHttpClient()

        with patch("aitbc.network.http_pool.httpx.AsyncClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.get = AsyncMock(return_value=MagicMock(status_code=200))
            mock_client.aclose = AsyncMock()
            mock_client_cls.return_value = mock_client

            await client.get("http://localhost:8006/health")
            await SharedHttpClient.close_instance()

            mock_client.aclose.assert_called_once()
            assert SharedHttpClient._client is None
            assert SharedHttpClient._instance is None


class TestSharedHttpClientPoolLimits:
    @pytest.mark.asyncio
    async def test_pool_limits_configured(self) -> None:
        client = SharedHttpClient(max_connections=50, max_keepalive=10, timeout=15.0)

        with patch("aitbc.network.http_pool.httpx.AsyncClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.get = AsyncMock(return_value=MagicMock(status_code=200))
            mock_client_cls.return_value = mock_client

            await client.get("http://localhost:8006/health")

            # Verify Limits were configured
            call_kwargs = mock_client_cls.call_args.kwargs
            assert call_kwargs["timeout"] == 15.0
            limits = call_kwargs["limits"]
            assert isinstance(limits, httpx.Limits)
            assert limits.max_connections == 50
            assert limits.max_keepalive_connections == 10
