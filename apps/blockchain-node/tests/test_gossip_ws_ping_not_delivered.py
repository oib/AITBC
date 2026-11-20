"""Server keepalive pings are control frames: never delivered to topic subscribers."""

from __future__ import annotations

import asyncio
import json

import pytest

from aitbc_chain.gossip.backends.websocket import _CONTROL_FRAME_TYPES, WebsocketGossipBackend


def _backend_with_queue(topic: str) -> tuple[WebsocketGossipBackend, asyncio.Queue]:
    backend = WebsocketGossipBackend("ws://127.0.0.1:1/rpc/gossip/ws")
    queue: asyncio.Queue = asyncio.Queue()
    backend._queues[topic] = [queue]
    return backend, queue


def test_ping_is_a_control_frame() -> None:
    assert "ping" in _CONTROL_FRAME_TYPES
    assert {"peer_auth_ok", "peer_auth_error"} <= _CONTROL_FRAME_TYPES


@pytest.mark.asyncio
async def test_ping_frame_not_delivered_but_payload_is() -> None:
    backend, queue = _backend_with_queue("pbft.prepare.chain-a")
    await backend._handle_inbound("pbft.prepare.chain-a", json.dumps({"type": "ping", "timestamp": 1.0}))
    assert queue.empty()
    vote = {"message_type": "prepare", "sender": "0xabc", "sequence_number": 7, "view_number": 1}
    await backend._handle_inbound("pbft.prepare.chain-a", json.dumps(vote))
    assert queue.get_nowait() == vote
    assert queue.empty()
