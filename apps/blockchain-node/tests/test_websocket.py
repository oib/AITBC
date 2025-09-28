from __future__ import annotations

import asyncio

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


def test_transactions_websocket_stream() -> None:
    client = TestClient(create_app())

    with client.websocket_connect("/rpc/ws/transactions") as websocket:
        payload = {
            "tx_hash": "0x" + "a" * 64,
            "sender": "alice",
            "recipient": "bob",
            "payload": {"amount": 1},
            "nonce": 1,
            "fee": 0,
            "type": "TRANSFER",
        }
        _publish("transactions", payload)
        message = websocket.receive_json()
        assert message == payload
