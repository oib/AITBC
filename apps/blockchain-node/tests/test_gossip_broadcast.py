from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from aitbc_chain.app import create_app
from aitbc_chain.gossip import BroadcastGossipBackend, InMemoryGossipBackend, gossip_broker


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
    backend = BroadcastGossipBackend("memory://")
    await gossip_broker.set_backend(backend)

    app = create_app()

    loop = asyncio.get_running_loop()

    def _sync_test() -> None:
        with TestClient(app) as client:
            with client.websocket_connect("/rpc/ws/transactions") as ws_a, client.websocket_connect(
                "/rpc/ws/transactions"
            ) as ws_b:
                payload = {
                    "tx_hash": "0x01",
                    "sender": "alice",
                    "recipient": "bob",
                    "payload": {"amount": 1},
                    "nonce": 0,
                    "fee": 0,
                    "type": "TRANSFER",
                }
                fut = asyncio.run_coroutine_threadsafe(gossip_broker.publish("transactions", payload), loop)
                fut.result(timeout=5.0)
                assert ws_a.receive_json() == payload
                assert ws_b.receive_json() == payload

    await _run_in_thread(_sync_test)


@pytest.mark.asyncio
async def test_broadcast_backend_decodes_cursorless_payload():
    backend = BroadcastGossipBackend("memory://")
    await gossip_broker.set_backend(backend)

    app = create_app()

    loop = asyncio.get_running_loop()

    def _sync_test() -> None:
        with TestClient(app) as client:
            with client.websocket_connect("/rpc/ws/blocks") as ws:
                payload = [
                    {"height": 1, "hash": "0xabc"},
                    {"height": 2, "hash": "0xdef"},
                ]
                fut = asyncio.run_coroutine_threadsafe(gossip_broker.publish("blocks", payload), loop)
                fut.result(timeout=5.0)
                assert ws.receive_json() == payload

    await _run_in_thread(_sync_test)
