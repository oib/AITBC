from __future__ import annotations

import asyncio
from contextlib import ExitStack

from aitbc_chain.app import create_app
from aitbc_chain.config import settings
from aitbc_chain.gossip import gossip_broker
from aitbc_chain.rpc import websocket as websocket_module
from aitbc.security import RateLimiter
from fastapi.testclient import TestClient
import pytest
from starlette.websockets import WebSocketDisconnect


@pytest.fixture(autouse=True)
def _gossip_test_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Disable auth and raise rate limits for the functional websocket tests."""
    monkeypatch.setattr(settings, "gossip_auth_enabled", False)
    monkeypatch.setattr(settings, "gossip_max_messages_per_minute", 1_000_000)
    monkeypatch.setattr(settings, "gossip_max_concurrent_connections_per_ip", 100)
    monkeypatch.setattr(
        websocket_module,
        "_gossip_msg_rate",
        RateLimiter(rate=1_000_000, per=60),
    )


def _publish(topic: str, message: dict) -> None:
    """Publish directly to the in-memory backend from the app's event loop.

    This wakes websocket subscribers without depending on cross-loop-safe
    asyncio primitives in the broker's global dedup/priority path.
    """
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


def test_gossip_websocket_public_topic_stream() -> None:
    """The /rpc/gossip/ws endpoint supports arbitrary public topics."""
    topic = "transactions"
    with TestClient(create_app()) as client:
        with client.websocket_connect(f"/rpc/gossip/ws?topic={topic}") as websocket:
            payload = {
                "tx_hash": "0x" + "b" * 64,
                "sender": "alice",
                "recipient": "carol",
                "payload": {"amount": 2},
                "nonce": 7,
                "fee": 1,
                "type": "TRANSFER",
            }
            _publish(topic, payload)
            message = websocket.receive_json()
            assert message == payload


def test_gossip_websocket_multiple_subscribers_receive_all_payloads() -> None:
    topic = "transactions"
    with TestClient(create_app()) as client, ExitStack() as stack:
        sockets = [stack.enter_context(client.websocket_connect(f"/rpc/gossip/ws?topic={topic}")) for _ in range(3)]

        payloads = [
            {
                "tx_hash": "0x" + "b" * 64,
                "sender": "alice",
                "recipient": f"user-{i}",
                "payload": {"amount": i},
                "nonce": i,
                "fee": 1,
                "type": "TRANSFER",
            }
            for i in range(5)
        ]

        for payload in payloads:
            _publish(topic, payload)

        for socket in sockets:
            received = [socket.receive_json() for _ in payloads]
            assert received == payloads

        final_payload = {
            "tx_hash": "0x" + "f" * 64,
            "sender": "alice",
            "recipient": "zoe",
            "payload": {"amount": 99},
            "nonce": 99,
            "fee": 1,
            "type": "TRANSFER",
        }
        _publish(topic, final_payload)

        for socket in sockets:
            assert socket.receive_json() == final_payload


def test_gossip_websocket_high_volume_load() -> None:
    message_count = 40
    subscriber_count = 4
    topic = "transactions"

    with TestClient(create_app()) as client, ExitStack() as stack:
        sockets = [
            stack.enter_context(client.websocket_connect(f"/rpc/gossip/ws?topic={topic}")) for _ in range(subscriber_count)
        ]

        payloads = []
        for i in range(message_count):
            payload = {
                "tx_hash": "0x" + f"{i + 100:064x}",
                "sender": "alice",
                "recipient": f"user-{i}",
                "payload": {"amount": i},
                "nonce": i,
                "fee": 1,
                "type": "TRANSFER",
            }
            payloads.append(payload)
            _publish(topic, payload)

        for socket in sockets:
            received = [socket.receive_json() for _ in payloads]
            assert received == payloads


def test_gossip_websocket_topic_isolation() -> None:
    """Subscribers to one gossip topic must not receive messages from another."""
    topic_a = "transactions"
    topic_b = "status.ait-mainnet"
    with TestClient(create_app()) as client:
        with client.websocket_connect(f"/rpc/gossip/ws?topic={topic_a}") as ws_a:
            with client.websocket_connect(f"/rpc/gossip/ws?topic={topic_b}") as ws_b:
                _publish(topic_a, {"msg": "for a"})
                assert ws_a.receive_json() == {"msg": "for a"}
                _publish(topic_b, {"msg": "for b"})
                assert ws_b.receive_json() == {"msg": "for b"}


def test_gossip_websocket_missing_topic_rejects() -> None:
    """The endpoint requires a topic query parameter."""
    with TestClient(create_app()) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/rpc/gossip/ws"):
                pass
