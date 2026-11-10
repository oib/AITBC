"""Advanced search routes — data-layer stub and direct RPC fallback branches."""

from __future__ import annotations

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from main import app
import routers.search as search_router


@pytest.fixture
def client():
    return TestClient(app)


def test_search_transactions_data_layer_dict_wrapper(monkeypatch):
    layer = AsyncMock()
    layer.get_transactions = AsyncMock(return_value=[{"hash": "0x1"}])
    monkeypatch.setattr(search_router, "get_data_layer", lambda: layer)
    monkeypatch.setattr(search_router, "USE_DATA_LAYER", True)

    out = asyncio.run(search_router.search_transactions(address="0xsender", amount_min=Decimal("1"), limit=5, offset=0))
    assert out == {"transactions": [{"hash": "0x1"}]}
    layer.get_transactions.assert_awaited_once()


def test_search_transactions_rpc_success_list(monkeypatch):
    monkeypatch.setattr(search_router, "USE_DATA_LAYER", False)

    class FakeResponse:
        status_code = 200

        def json(self):
            return [{"hash": "0xabc"}]

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def get(self, url, params=None):
            assert "search/transactions" in url
            assert params["address"] == "0xsender"
            assert params["amount_min"] == "1.5"
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: FakeClient())
    out = asyncio.run(search_router.search_transactions(address="0xsender", amount_min=Decimal("1.5")))
    assert out == {"transactions": [{"hash": "0xabc"}]}


def test_search_transactions_rpc_404_empty(monkeypatch):
    monkeypatch.setattr(search_router, "USE_DATA_LAYER", False)

    class FakeResponse:
        status_code = 404

        text = "missing"

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def get(self, url, params=None):
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: FakeClient())
    out = asyncio.run(search_router.search_transactions())
    assert out == {"transactions": []}


def test_search_transactions_rpc_upstream_error(client, monkeypatch):
    """Non-200 RPC responses propagate their status via HTTPException passthrough."""
    monkeypatch.setattr(search_router, "USE_DATA_LAYER", False)

    class FakeResponse:
        status_code = 502
        text = "bad gateway"

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def get(self, url, params=None):
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: FakeClient())
    resp = client.get("/api/search/transactions")
    assert resp.status_code == 502


def test_search_transactions_rpc_connect_error(monkeypatch):
    monkeypatch.setattr(search_router, "USE_DATA_LAYER", False)

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def get(self, url, params=None):
            raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: FakeClient())
    with pytest.raises(HTTPException) as exc:
        asyncio.run(search_router.search_transactions())
    assert exc.value.status_code == 503


def test_search_blocks_rpc_success_dict(monkeypatch):
    monkeypatch.setattr(search_router, "USE_DATA_LAYER", False)

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"blocks": [{"height": 1}], "total": 1}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def get(self, url, params=None):
            assert "search/blocks" in url
            assert params["min_tx"] == 2
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: FakeClient())
    out = asyncio.run(search_router.search_blocks(validator="0xv", min_tx=2))
    assert out["blocks"][0]["height"] == 1


def test_search_endpoints_clamp_via_client(client, monkeypatch):
    """Sanity: happy path through TestClient with data layer mock (default env)."""
    layer = AsyncMock()
    layer.get_transactions = AsyncMock(return_value={"transactions": []})
    layer.get_blocks = AsyncMock(return_value={"blocks": []})
    monkeypatch.setattr(search_router, "get_data_layer", lambda: layer)
    monkeypatch.setattr(search_router, "USE_DATA_LAYER", True)

    assert client.get("/api/search/transactions", params={"limit": -1}).status_code == 200
    assert client.get("/api/search/blocks", params={"limit": 10**9}).status_code == 200
