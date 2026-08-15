"""Basic tests for edge service clients."""

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
