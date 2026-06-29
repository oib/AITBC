"""Unit tests for aitbc.marketplace.blockchain_rpc (v0.6.6 §A3).

Covers the BlockchainRPCClient with mocked httpx responses. No real
blockchain node required — all HTTP calls are stubbed with AsyncMock.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from aitbc.marketplace.blockchain_rpc import BlockchainRPCClient

RPC_URL = "http://localhost:8202"


def _mock_response(
    status_code: int = 200,
    json_data: dict | list | None = None,
) -> MagicMock:
    """Create a mock httpx.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data if json_data is not None else {}
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error",
            request=MagicMock(),
            response=resp,
        )
    return resp


def _mock_async_client(resp: MagicMock) -> AsyncMock:
    """Create a mock httpx.AsyncClient that returns the given response for all methods."""
    client = AsyncMock()
    client.get = AsyncMock(return_value=resp)
    client.post = AsyncMock(return_value=resp)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    return client


# ---------------------------------------------------------------------------
# rpc_url
# ---------------------------------------------------------------------------


def test_rpc_url_default() -> None:
    client = BlockchainRPCClient()
    assert client.rpc_url == "http://localhost:8202"


def test_rpc_url_custom() -> None:
    client = BlockchainRPCClient(rpc_url="http://node:9000")
    assert client.rpc_url == "http://node:9000"


def test_rpc_url_strips_trailing_slash() -> None:
    client = BlockchainRPCClient(rpc_url="http://localhost:8202/")
    assert client.rpc_url == "http://localhost:8202"


# ---------------------------------------------------------------------------
# query_offers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_query_offers_with_chain_id() -> None:
    resp = _mock_response(200, {"gpus": [{"gpu_id": "gpu1", "model": "RTX 4090"}]})
    client = _mock_async_client(resp)
    rpc = BlockchainRPCClient(rpc_url=RPC_URL)
    with patch("aitbc.marketplace.blockchain_rpc.httpx.AsyncClient", return_value=client):
        offers = await rpc.query_offers(chain_id="ait-hub")
    assert offers == [{"gpu_id": "gpu1", "model": "RTX 4090"}]
    # Verify chain_id was in the request params
    client.get.assert_called_once()
    call_args = client.get.call_args
    params = call_args.kwargs.get("params", {})
    assert params.get("chain_id") == "ait-hub"


@pytest.mark.asyncio
async def test_query_offers_without_chain_id() -> None:
    resp = _mock_response(200, {"gpus": []})
    client = _mock_async_client(resp)
    rpc = BlockchainRPCClient(rpc_url=RPC_URL)
    with patch("aitbc.marketplace.blockchain_rpc.httpx.AsyncClient", return_value=client):
        offers = await rpc.query_offers()
    assert offers == []
    call_args = client.get.call_args
    params = call_args.kwargs.get("params", {})
    assert "chain_id" not in params


@pytest.mark.asyncio
async def test_query_offers_client_side_filter_gpu_model() -> None:
    resp = _mock_response(
        200,
        {
            "gpus": [
                {"gpu_id": "gpu1", "model": "RTX 4090"},
                {"gpu_id": "gpu2", "model": "RTX 3060"},
            ]
        },
    )
    client = _mock_async_client(resp)
    rpc = BlockchainRPCClient(rpc_url=RPC_URL)
    with patch("aitbc.marketplace.blockchain_rpc.httpx.AsyncClient", return_value=client):
        offers = await rpc.query_offers(gpu_model="rtx 4090")
    assert len(offers) == 1
    assert offers[0]["gpu_id"] == "gpu1"


@pytest.mark.asyncio
async def test_query_offers_client_side_filter_region() -> None:
    resp = _mock_response(
        200,
        {
            "gpus": [
                {"gpu_id": "gpu1", "region": "us-east"},
                {"gpu_id": "gpu2", "region": "eu-west"},
            ]
        },
    )
    client = _mock_async_client(resp)
    rpc = BlockchainRPCClient(rpc_url=RPC_URL)
    with patch("aitbc.marketplace.blockchain_rpc.httpx.AsyncClient", return_value=client):
        offers = await rpc.query_offers(region="us-east")
    assert len(offers) == 1
    assert offers[0]["gpu_id"] == "gpu1"


@pytest.mark.asyncio
async def test_query_offers_returns_list_when_response_is_list() -> None:
    """When the RPC returns a bare list (not wrapped in {gpus: ...})."""
    resp = _mock_response(200, [{"gpu_id": "gpu1"}])
    client = _mock_async_client(resp)
    rpc = BlockchainRPCClient(rpc_url=RPC_URL)
    with patch("aitbc.marketplace.blockchain_rpc.httpx.AsyncClient", return_value=client):
        offers = await rpc.query_offers()
    assert offers == [{"gpu_id": "gpu1"}]


@pytest.mark.asyncio
async def test_query_offers_returns_empty_on_non_list() -> None:
    """When the RPC returns unexpected data, return empty list."""
    resp = _mock_response(200, {"unexpected": "data"})
    client = _mock_async_client(resp)
    rpc = BlockchainRPCClient(rpc_url=RPC_URL)
    with patch("aitbc.marketplace.blockchain_rpc.httpx.AsyncClient", return_value=client):
        offers = await rpc.query_offers()
    assert offers == []


# ---------------------------------------------------------------------------
# get_offer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_offer_found() -> None:
    resp = _mock_response(200, {"gpu_id": "gpu1", "model": "RTX 4090"})
    client = _mock_async_client(resp)
    rpc = BlockchainRPCClient(rpc_url=RPC_URL)
    with patch("aitbc.marketplace.blockchain_rpc.httpx.AsyncClient", return_value=client):
        offer = await rpc.get_offer("gpu1", chain_id="ait-hub")
    assert offer is not None
    assert offer["gpu_id"] == "gpu1"


@pytest.mark.asyncio
async def test_get_offer_not_found() -> None:
    resp = _mock_response(404)
    client = _mock_async_client(resp)
    rpc = BlockchainRPCClient(rpc_url=RPC_URL)
    with patch("aitbc.marketplace.blockchain_rpc.httpx.AsyncClient", return_value=client):
        offer = await rpc.get_offer("nonexistent")
    assert offer is None


# ---------------------------------------------------------------------------
# submit_transaction
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_submit_transaction_with_chain_id() -> None:
    resp = _mock_response(200, {"status": "ok", "tx_hash": "abc123"})
    client = _mock_async_client(resp)
    rpc = BlockchainRPCClient(rpc_url=RPC_URL)
    with patch("aitbc.marketplace.blockchain_rpc.httpx.AsyncClient", return_value=client):
        result = await rpc.submit_transaction({"chain_id": "ait-hub", "type": "GPU_REGISTER"})
    assert result["tx_hash"] == "abc123"


@pytest.mark.asyncio
async def test_submit_transaction_without_chain_id_raises() -> None:
    rpc = BlockchainRPCClient(rpc_url=RPC_URL)
    with pytest.raises(ValueError, match="must include 'chain_id'"):
        await rpc.submit_transaction({"type": "GPU_REGISTER"})


# ---------------------------------------------------------------------------
# register_gpu
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_gpu_with_chain_id() -> None:
    resp = _mock_response(200, {"status": "registered", "gpu_id": "gpu1"})
    client = _mock_async_client(resp)
    rpc = BlockchainRPCClient(rpc_url=RPC_URL)
    with patch("aitbc.marketplace.blockchain_rpc.httpx.AsyncClient", return_value=client):
        result = await rpc.register_gpu({"chain_id": "ait-hub", "gpu_id": "gpu1", "model": "RTX 4090"})
    assert result["gpu_id"] == "gpu1"


@pytest.mark.asyncio
async def test_register_gpu_without_chain_id_raises() -> None:
    rpc = BlockchainRPCClient(rpc_url=RPC_URL)
    with pytest.raises(ValueError, match="must include 'chain_id'"):
        await rpc.register_gpu({"gpu_id": "gpu1"})


# ---------------------------------------------------------------------------
# allocate_gpu
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_allocate_gpu_with_chain_id() -> None:
    resp = _mock_response(200, {"status": "allocated", "allocation_id": "alloc1"})
    client = _mock_async_client(resp)
    rpc = BlockchainRPCClient(rpc_url=RPC_URL)
    with patch("aitbc.marketplace.blockchain_rpc.httpx.AsyncClient", return_value=client):
        result = await rpc.allocate_gpu({"chain_id": "ait-hub", "gpu_id": "gpu1", "client_id": "client1"})
    assert result["allocation_id"] == "alloc1"


@pytest.mark.asyncio
async def test_allocate_gpu_without_chain_id_raises() -> None:
    rpc = BlockchainRPCClient(rpc_url=RPC_URL)
    with pytest.raises(ValueError, match="must include 'chain_id'"):
        await rpc.allocate_gpu({"gpu_id": "gpu1"})


# ---------------------------------------------------------------------------
# verify_escrow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_escrow_found() -> None:
    resp = _mock_response(200, {"escrow_id": "esc1", "status": "locked"})
    client = _mock_async_client(resp)
    rpc = BlockchainRPCClient(rpc_url=RPC_URL)
    with patch("aitbc.marketplace.blockchain_rpc.httpx.AsyncClient", return_value=client):
        result = await rpc.verify_escrow("esc1")
    assert result is not None
    assert result["status"] == "locked"


@pytest.mark.asyncio
async def test_verify_escrow_not_found() -> None:
    resp = _mock_response(404)
    client = _mock_async_client(resp)
    rpc = BlockchainRPCClient(rpc_url=RPC_URL)
    with patch("aitbc.marketplace.blockchain_rpc.httpx.AsyncClient", return_value=client):
        result = await rpc.verify_escrow("nonexistent")
    assert result is None


# ---------------------------------------------------------------------------
# package re-export
# ---------------------------------------------------------------------------


def test_package_reexport() -> None:
    from aitbc.marketplace import BlockchainRPCClient as ExportedClient

    assert ExportedClient is BlockchainRPCClient
