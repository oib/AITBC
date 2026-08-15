from __future__ import annotations

import asyncio

import pytest
from aitbc_chain.gossip import InMemoryGossipBackend, gossip_broker


@pytest.fixture(autouse=True)
async def reset_broker_backend():
    previous_backend = InMemoryGossipBackend()
    await gossip_broker.set_backend(previous_backend)
    yield
    await gossip_broker.set_backend(InMemoryGossipBackend())


def _run_in_thread(fn):
    loop = asyncio.get_event_loop()
    return loop.run_in_executor(None, fn)


@pytest.mark.asyncio
async def test_websocket_fanout_with_broadcast_backend():
    """Test WebSocket fanout using the BroadcastGossipBackend (Redis pub/sub)."""
    pytest.skip("requires Redis instance — BroadcastGossipBackend needs a real redis:// URL, not memory://")


@pytest.mark.asyncio
async def test_broadcast_backend_decodes_cursorless_payload():
    """Test that BroadcastGossipBackend decodes payloads without cursors."""
    pytest.skip("requires Redis instance — BroadcastGossipBackend needs a real redis:// URL, not memory://")
