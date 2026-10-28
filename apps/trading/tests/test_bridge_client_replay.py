"""CALLERS-NEWFORM-1: escrow-lock wrappers forward ``issued_at`` / ``nonce``.

Both layers posting to ``POST /bridge/lock`` — ``aitbc.trading.bridge.TradingBridgeClient``
and the ``trading_service`` ``BridgeClient`` wrapper around it — pass the replay
guard fields through to ``BridgeClient.lock()`` instead of dropping them. Both
are dormant today, but a live caller must be able to submit the guarded form.
"""

from __future__ import annotations

from unittest import mock
import pytest


def _args() -> dict[str, object]:
    return {
        "source_chain": "ait-hub",
        "target_chain": "ait-side",
        "sender": "0x" + "aa" * 20,
        "recipient": "0x" + "bb" * 20,
        "amount": 3600000,
        "signature": "0x" + "ee" * 65,
    }


@pytest.mark.asyncio
async def test_trading_bridge_client_forwards_replay_fields():
    from aitbc.trading.bridge import TradingBridgeClient

    client = TradingBridgeClient.__new__(TradingBridgeClient)
    client._bridge = mock.Mock()
    client._bridge.lock = mock.AsyncMock(return_value={"transfer_id": "t-1"})

    await client.lock_escrow(**_args(), issued_at=1760000000, nonce="deadbeef")

    kwargs = client._bridge.lock.call_args.kwargs
    assert kwargs["issued_at"] == 1760000000
    assert kwargs["nonce"] == "deadbeef"


@pytest.mark.asyncio
async def test_trading_bridge_client_defaults_replay_fields_to_none():
    from aitbc.trading.bridge import TradingBridgeClient

    client = TradingBridgeClient.__new__(TradingBridgeClient)
    client._bridge = mock.Mock()
    client._bridge.lock = mock.AsyncMock(return_value={"transfer_id": "t-1"})

    await client.lock_escrow(**_args())

    kwargs = client._bridge.lock.call_args.kwargs
    assert kwargs["issued_at"] is None
    assert kwargs["nonce"] is None


@pytest.mark.asyncio
async def test_service_wrapper_forwards_replay_fields():
    from trading_service.clients.bridge import BridgeClient

    client = BridgeClient.__new__(BridgeClient)
    client._bridge = mock.Mock()
    client._bridge.lock_escrow = mock.AsyncMock(return_value={"transfer_id": "t-1"})

    await client.lock_escrow(
        source_chain="ait-hub",
        target_chain="ait-side",
        sender="0x" + "aa" * 20,
        recipient="0x" + "bb" * 20,
        amount=3600000,
        signature="0x" + "ee" * 65,
        issued_at=1760000000,
        nonce="deadbeef",
    )

    kwargs = client._bridge.lock_escrow.call_args.kwargs
    assert kwargs["issued_at"] == 1760000000
    assert kwargs["nonce"] == "deadbeef"
