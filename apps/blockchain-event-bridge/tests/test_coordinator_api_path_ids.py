"""#2769: on-chain tx fields interpolated into coordinator-api URL paths.

``job_id``/``listing_id``/``to`` come from sealed payloads — any tx
submitter controls them. Raw f-string interpolation let ``/``, ``?``,
``#``, ``%`` and dot-segments rewrite the request path against an API
carrying the bridge's bearer key. Values outside a strict path-segment
allowlist are now dropped before the request is built.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from blockchain_event_bridge.action_handlers.coordinator_api import (
    CoordinatorAPIHandler,
    _path_id,
)

ADDR = "0x" + "ab" * 20


def _handler() -> CoordinatorAPIHandler:
    h = CoordinatorAPIHandler("http://localhost:8011", "test-key")
    h._client = AsyncMock()
    return h


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("job-123_abc", "job-123_abc"),
        ("listing_001", "listing_001"),
        (ADDR, ADDR),
        ("0x" + "ab" * 32, "0x" + "ab" * 32),  # tx-hash style job_id
        ("job.id:with-dash", "job.id:with-dash"),
        (123, "123"),
        ("", None),
        (None, None),
        (True, None),
        ({"a": 1}, None),
        (["x"], None),
        ("a/b", None),
        ("../admin", None),
        ("..", None),
        (".", None),
        ("job?x=1", None),
        ("job#frag", None),
        ("job%2F..%2Fadmin", None),
        ("job id", None),
        ("job@evil.com", None),
        ("a" * 200, None),
    ],
)
def test_path_id_allowlist(value, expected):
    assert _path_id(value) == expected


@pytest.mark.asyncio
async def test_ai_job_notify_skips_unsafe_job_id():
    h = _handler()
    tx = {"type": "ai_job", "hash": "0xtx", "payload": {"job_id": "abc/../../admin"}}
    await h.handle_transaction(tx)
    h._client.post.assert_not_called()


@pytest.mark.asyncio
async def test_ai_job_notify_safe_job_id():
    h = _handler()
    tx = {"type": "ai_job", "hash": "0xtx", "payload": {"job_id": "job-123"}}
    await h.handle_transaction(tx)
    h._client.post.assert_called_once_with("/v1/ai-jobs/job-123/notify", json=tx)


@pytest.mark.asyncio
async def test_agent_message_skips_unsafe_recipient():
    h = _handler()
    tx = {"type": "agent_message", "hash": "0xtx", "to": "x/../y?admin=1", "payload": {}}
    await h.handle_transaction(tx)
    h._client.post.assert_not_called()


@pytest.mark.asyncio
async def test_agent_message_safe_recipient():
    h = _handler()
    tx = {"type": "agent_message", "hash": "0xtx", "to": ADDR, "payload": {"m": 1}}
    await h.handle_transaction(tx)
    h._client.post.assert_called_once()
    assert h._client.post.call_args[0][0] == f"/v1/agents/{ADDR}/message"


@pytest.mark.asyncio
async def test_market_sync_skips_unsafe_listing_id():
    h = _handler()
    tx = {"type": "market", "hash": "0xtx", "payload": {"listing_id": "a%2F..%2Fb"}}
    await h.handle_transaction(tx)
    h._client.post.assert_not_called()


@pytest.mark.asyncio
async def test_market_sync_safe_listing_id():
    h = _handler()
    tx = {"type": "market", "hash": "0xtx", "payload": {"listing_id": "listing_042"}}
    await h.handle_transaction(tx)
    h._client.post.assert_called_once_with("/v1/market/listing_042/sync", json={"transaction": tx})
