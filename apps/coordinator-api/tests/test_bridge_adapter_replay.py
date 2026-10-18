"""CALLERS-NEWFORM-1: ``BridgeClientAdapter.lock()`` forwards replay fields.

The adapter is dormant today (no callers) but must not drop ``issued_at`` /
``nonce`` when it is used: ``BridgeClient.lock()`` already accepts them.
"""

from __future__ import annotations

from unittest import mock

import pytest

from coordinator_api.contexts.cross_chain.services.cross_chain.bridge_client_adapter import (
    BridgeClientAdapter,
)


@pytest.mark.asyncio
async def test_lock_forwards_replay_fields():
    adapter = BridgeClientAdapter()
    adapter._client = mock.Mock()
    adapter._client.lock = mock.AsyncMock(return_value={"success": True})

    await adapter.lock(
        target_chain="ait-side",
        sender="0x" + "aa" * 20,
        recipient="0x" + "bb" * 20,
        amount=3600000,
        signature="0x" + "ee" * 65,
        issued_at=1760000000,
        nonce="deadbeef",
    )

    kwargs = adapter._client.lock.call_args.kwargs
    assert kwargs["issued_at"] == 1760000000
    assert kwargs["nonce"] == "deadbeef"


@pytest.mark.asyncio
async def test_lock_defaults_replay_fields_to_none():
    adapter = BridgeClientAdapter()
    adapter._client = mock.Mock()
    adapter._client.lock = mock.AsyncMock(return_value={"success": True})

    await adapter.lock(
        target_chain="ait-side",
        sender="0x" + "aa" * 20,
        recipient="0x" + "bb" * 20,
        amount=3600000,
        signature="0x" + "ee" * 65,
    )

    kwargs = adapter._client.lock.call_args.kwargs
    assert kwargs["issued_at"] is None
    assert kwargs["nonce"] is None
