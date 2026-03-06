from __future__ import annotations

import asyncio
from contextlib import ExitStack

from fastapi.testclient import TestClient

from aitbc_chain.app import create_app
from aitbc_chain.gossip import gossip_broker


def _publish(topic: str, message: dict) -> None:
    asyncio.run(gossip_broker.publish(topic, message))
def test_blocks_websocket_stream() -> None:
    client = TestClient(create_app())

    with client.websocket_connect("/rpc/ws/blocks") as websocket:
        payload = {
            "height": 1,
            "hash": "0x" + "1" * 64,
            "parent_hash": "0x" + "0" * 64,
            "timestamp": "2025-01-01T00:00:00Z",
            "tx_count": 2,
        }
        _publish("blocks", payload)
        message = websocket.receive_json()
        assert message == payload


def test_blocks_websocket_multiple_subscribers_receive_all_payloads() -> None:
    with TestClient(create_app()) as client, ExitStack() as stack:
        sockets = [
            stack.enter_context(client.websocket_connect("/rpc/ws/blocks"))
            for _ in range(3)
        ]

        payloads = [
            {
                "height": height,
                "hash": "0x" + f"{height:064x}",
                "parent_hash": (
                    "0x" + f"{height - 1:064x}" if height > 0 else "0x" + "0" * 64
                ),
                "timestamp": f"2025-01-01T00:00:{height:02d}Z",
                "tx_count": height % 3,
            }
            for height in range(5)
        ]

        for payload in payloads:
            _publish("blocks", payload)

        for socket in sockets:
            received = [socket.receive_json() for _ in payloads]
            assert received == payloads

        # Publish another payload to ensure subscribers continue receiving in order.
        final_payload = {
            "height": 99,
            "hash": "0x" + "f" * 64,
            "parent_hash": "0x" + "e" * 64,
            "timestamp": "2025-01-01T00:01:39Z",
            "tx_count": 5,
        }
        _publish("blocks", final_payload)

        for socket in sockets:
            assert socket.receive_json() == final_payload


def test_blocks_websocket_high_volume_load() -> None:
    message_count = 40
    subscriber_count = 4

    with TestClient(create_app()) as client, ExitStack() as stack:
        sockets = [
            stack.enter_context(client.websocket_connect("/rpc/ws/blocks"))
            for _ in range(subscriber_count)
        ]

        payloads = []
        for height in range(message_count):
            payload = {
                "height": height,
                "hash": "0x" + f"{height + 100:064x}",
                "parent_hash": "0x" + f"{height + 99:064x}" if height > 0 else "0x" + "0" * 64,
                "timestamp": f"2025-01-01T00:{height // 60:02d}:{height % 60:02d}Z",
                "tx_count": height % 7,
            }
            payloads.append(payload)
            _publish("blocks", payload)

        for socket in sockets:
            received = [socket.receive_json() for _ in payloads]
            assert received == payloads


def test_transactions_websocket_cleans_up_on_disconnect() -> None:
    client = TestClient(create_app())

    with client.websocket_connect("/rpc/ws/transactions") as websocket:
        payload = {
            "tx_hash": "0x" + "b" * 64,
            "sender": "alice",
            "recipient": "carol",
            "payload": {"amount": 2},
            "nonce": 7,
            "fee": 1,
            "type": "TRANSFER",
        }
        _publish("transactions", payload)
        assert websocket.receive_json() == payload

    # After closing the websocket, publishing again should not raise and should not hang.
    _publish(
        "transactions",
        {
            "tx_hash": "0x" + "c" * 64,
            "sender": "alice",
            "recipient": "dave",
            "payload": {"amount": 3},
            "nonce": 8,
            "fee": 1,
            "type": "TRANSFER",
        },
    )
