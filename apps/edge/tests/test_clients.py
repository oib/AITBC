"""Basic tests for edge service clients."""

import json

import httpx
import pytest
from aitbc_edge.clients.blockchain_rpc import BlockchainRPCClient
from aitbc_edge.clients.gpu_service import GPUServiceClient


@pytest.mark.asyncio
async def test_blockchain_rpc_client_context_manager_closes():
    """BlockchainRPCClient should be usable as an async context manager and close cleanly."""
    async with BlockchainRPCClient() as client:
        assert client.client is not None
        assert client.base_url == "http://localhost:8202"
    assert client.client is None


@pytest.mark.asyncio
async def test_gpu_service_client_context_manager_closes():
    """GPUServiceClient should be usable as an async context manager and close cleanly."""
    async with GPUServiceClient() as client:
        assert client.client is not None
        assert client.base_url == "http://localhost:8101"
    assert client.client is None


@pytest.mark.asyncio
async def test_blockchain_rpc_client_attaches_api_key_header():
    """verify_rpc_api_key on the rpc side demands X-API-Key — the client
    must carry it on every request once an api key is configured."""
    async with BlockchainRPCClient(api_key="test-secret") as client:
        assert client.client.headers["X-API-Key"] == "test-secret"


@pytest.mark.asyncio
async def test_register_edge_sends_api_key_and_payload():
    """Wire check: register_edge POSTs to /rpc/edge/register carrying the
    X-API-Key header — the omission that got the startup register a 403."""
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["api_key"] = request.headers.get("x-api-key")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"ok": True})

    async with BlockchainRPCClient(api_key="test-secret") as client:
        client.client = httpx.AsyncClient(transport=httpx.MockTransport(handler), headers=client.client.headers)
        result = await client.register_edge({"node_id": "edge-x"}, timeout=5.0)

    assert result == {"ok": True}
    assert seen["path"] == "/rpc/edge/register"
    assert seen["api_key"] == "test-secret"
    assert seen["body"] == {"node_id": "edge-x"}
