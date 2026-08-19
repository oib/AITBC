from __future__ import annotations

import asyncio
from contextlib import ExitStack

import pytest
from aitbc_chain.app import create_app
from aitbc_chain.config import settings
from aitbc_chain.gossip import gossip_broker
from fastapi.testclient import TestClient


def _publish(topic: str, message: object) -> None:
    """Publish through the broker's backend on the app's captured event loop."""
    loop = getattr(gossip_broker, "_app_loop", None)
    if loop is None:
        loop = asyncio.get_event_loop()

    async def _do_publish():
        backend = gossip_broker._backend
        if backend is None:
            raise RuntimeError("Gossip broker has no backend")
        await backend.publish(topic, message)

    fut = asyncio.run_coroutine_threadsafe(_do_publish(), loop)
    fut.result(timeout=5.0)


@pytest.fixture
def _broadcast_backend(monkeypatch):
    """Force the broadcast gossip backend backed by the local Redis for these tests."""
    monkeypatch.setattr(settings, "gossip_backend", "broadcast")
    monkeypatch.setattr(settings, "gossip_broadcast_url", "redis://localhost:6379/0")


def test_websocket_fanout_with_broadcast_backend(_broadcast_backend) -> None:
    """A message published via the broadcast backend reaches multiple websocket subscribers."""
    with TestClient(create_app()) as client, ExitStack() as stack:
        sockets = [stack.enter_context(client.websocket_connect("/rpc/transactions")) for _ in range(2)]

        payload = {
            "tx_hash": "0x" + "d" * 64,
            "sender": "alice",
            "recipient": "bob",
            "payload": {"amount": 5},
            "nonce": 0,
            "fee": 1,
            "type": "TRANSFER",
        }
        _publish("transactions", payload)

        for socket in sockets:
            assert socket.receive_json() == payload


def test_broadcast_backend_decodes_cursorless_payload(_broadcast_backend) -> None:
    """A batched/cursorless block payload is decoded and delivered correctly."""
    with TestClient(create_app()) as client:
        with client.websocket_connect("/rpc/blocks") as websocket:
            payload = [
                {"height": 1, "hash": "0x" + "a" * 64},
                {"height": 2, "hash": "0x" + "b" * 64},
            ]
            _publish("blocks", payload)
            received = [websocket.receive_json() for _ in payload]
            assert received == payload
