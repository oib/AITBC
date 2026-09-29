"""BRIDGE_LOCKS_PAUSED — new bridge locks refuse while the pause is set.

The pause boundary is the lock *request* path: every REST surface
(/bridge/lock, /bridge/batch/lock, /swap, /cross-chain/bridge) returns 503,
and ``initiate_transfer`` — the chokepoint they all funnel through — raises
``BridgeLocksPausedError`` so no internal caller bypasses it. Refunds,
status reads and the confirm path are untouched, and mempool admission is
deliberately NOT gated: a lock issued before the pause must still seal, and
nothing but the bridge itself can produce a valid BRIDGE_LOCK envelope
(v9 requires the bridge authority signature).
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, select

from aitbc_chain.base_models import CrossChainTransfer
from aitbc_chain.config import settings
from aitbc_chain.cross_chain.bridge import CrossChainBridge
from aitbc_chain.cross_chain.bridge_types import BRIDGE_LOCKS_PAUSED_DETAIL, BridgeLocksPausedError
from aitbc_chain.mempool import get_mempool
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.models import Account


@pytest.fixture()
def engine():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    chain_metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture()
def bridge(engine):
    return CrossChainBridge(lambda: Session(engine))


@pytest.fixture()
def paused(monkeypatch):
    monkeypatch.setattr(settings, "bridge_locks_paused", True)
    return True


def _seed(engine, chain_id: str, address: str, balance: int) -> None:
    with Session(engine) as session:
        session.add(Account(chain_id=chain_id, address=address, balance=balance, nonce=0))
        session.commit()


def _account(engine, chain_id: str, address: str) -> Account:
    with Session(engine) as session:
        acc = session.get(Account, (chain_id, address))
        assert acc is not None
        session.expunge(acc)
        return acc


class TestLockEndpointsPaused:
    """Every REST lock surface answers 503 with the documented detail."""

    def test_bridge_lock_503(self, paused):
        from aitbc_chain.rpc.bridge import bridge_lock

        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                bridge_lock(
                    None,  # type: ignore[arg-type]
                    {
                        "target_chain": "chain-b",
                        "sender": "0xsender",
                        "recipient": "0xrecipient",
                        "amount": 1000,
                        "signature": "0xsig",
                    },
                )
            )
        assert exc.value.status_code == 503
        assert exc.value.detail == BRIDGE_LOCKS_PAUSED_DETAIL

    def test_bridge_batch_lock_503(self, paused):
        from aitbc_chain.rpc.bridge import bridge_batch_lock

        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                bridge_batch_lock(
                    None,  # type: ignore[arg-type]
                    {
                        "transfers": [
                            {
                                "source_chain": "chain-a",
                                "target_chain": "chain-b",
                                "sender": "0xs",
                                "recipient": "0xr",
                                "amount": 1,
                            }
                        ]
                    },
                )
            )
        assert exc.value.status_code == 503
        assert exc.value.detail == BRIDGE_LOCKS_PAUSED_DETAIL

    def test_cross_chain_lock_transfer_503(self, paused):
        """/swap and /cross-chain/bridge share _lock_transfer — it must refuse
        the same way (they are lock requests, not exempt paths)."""
        from aitbc_chain.rpc.routers.cross_chain import _lock_transfer

        with pytest.raises(HTTPException) as exc:
            _lock_transfer(
                sign_data={},
                source_chain="chain-a",
                target_chain="chain-b",
                sender="0xsender",
                recipient="0xrecipient",
                amount_units=1000,
                asset="native",
                signature="0xsig",
            )
        assert exc.value.status_code == 503
        assert exc.value.detail == BRIDGE_LOCKS_PAUSED_DETAIL


class TestInitiateTransferPaused:
    """The chokepoint itself refuses, so no non-HTTP caller bypasses the pause."""

    def test_initiate_transfer_raises_and_writes_nothing(self, bridge, engine, paused):
        _seed(engine, "chain-a", "0xsender", 10_000)
        mempool = get_mempool()
        before = mempool.size("chain-a")

        with pytest.raises(BridgeLocksPausedError, match="Bridge paused"):
            bridge.initiate_transfer("chain-a", "chain-b", "0xsender", "0xrecipient", 1000)

        # No debit, no transfer row, no mempool entry — nothing was registered.
        assert _account(engine, "chain-a", "0xsender").balance == 10_000
        assert _account(engine, "chain-a", "0xsender").nonce == 0
        assert mempool.size("chain-a") == before
        with Session(engine) as session:
            assert session.exec(select(CrossChainTransfer)).all() == []

    def test_refund_still_works_while_paused(self, bridge, engine, monkeypatch):
        """A lock taken before the pause stays refundable while locks are
        paused — BRIDGE_REFUND issuance is not part of the pause."""
        _seed(engine, "chain-a", "0xsender", 10_000)
        transfer = bridge.initiate_transfer("chain-a", "chain-b", "0xsender", "0xrecipient", 1000)
        monkeypatch.setattr(settings, "bridge_locks_paused", True)

        bridge.refund_transfer(transfer.transfer_id, "0xsender")

        assert _account(engine, "chain-a", "0xsender").balance == 10_000 - 1  # fee not refunded
        with Session(engine) as session:
            record = session.get(CrossChainTransfer, transfer.transfer_id)
            assert record is not None and record.status == "refunded"


class TestMempoolAdmissionNotGated:
    """The pause boundary is the request path, NOT mempool admission: a lock
    envelope already issued before the pause must still be able to seal
    (BRIDGE_REFUND binds a *sealed* lock since v6, so stranding it would park
    funds — the exact thing the pause prevents)."""

    def test_mempool_still_accepts_bridge_lock_while_paused(self, paused):
        mempool = get_mempool()
        tx_hash = mempool.add(
            {
                "from": "0xsender",
                "to": "bridge_lock",
                "amount": 1000,
                "fee": 1,
                "type": "BRIDGE_LOCK",
                "transfer_id": "0xlock1",
                "target_chain": "chain-b",
                "nonce": 0,
                "chain_id": "chain-a",
            },
            chain_id="chain-a",
        )
        assert mempool.get_pending_transactions("chain-a")
        mempool.remove(tx_hash, chain_id="chain-a")
