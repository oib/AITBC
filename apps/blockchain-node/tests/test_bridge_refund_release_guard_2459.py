"""Tests for #2459: refund_transfer must refuse when a BRIDGE_RELEASE sealed.

``refund_transfer`` gated only on the node-local row status, sender match,
lock-seal evidence and elapsed time — it never looked at the target chain.
A sealed ``BRIDGE_RELEASE`` for the same ``transfer_id`` therefore did not
stop the refund: the sender got the release on the target chain AND a
``BRIDGE_REFUND`` credit on the source chain (double pay). The refund path
now reconciles the row to ``completed`` from chain evidence and raises
when the target-chain store is available; when it is not, the time gates
remain the only guard.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, select

from aitbc_chain.cross_chain.bridge import BridgeStatus, CrossChainBridge
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.models import Account, CrossChainTransfer, Transaction

SOURCE = "chain-a"
TARGET = "chain-b"
SENDER = "0xrefundsender"
AMOUNT = 3000


@pytest.fixture(autouse=True)
def _patch_supported_chains():
    with (
        patch("aitbc_chain.config.settings.supported_chains", f"{SOURCE},{TARGET}"),
        patch("aitbc_chain.config.settings.block_scoped_preregistered_transactions", False),
    ):
        yield


@pytest.fixture
def engine():
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    chain_metadata.create_all(eng)
    yield eng
    chain_metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture
def bridge(engine):
    return CrossChainBridge(lambda: Session(engine))


def _seed(engine) -> None:
    with Session(engine) as session:
        session.add(Account(chain_id=SOURCE, address=SENDER, balance=AMOUNT * 4, nonce=0))
        session.commit()


def _lock_transfer(bridge: CrossChainBridge, engine, *, status: str = "pending", age_seconds: int = 0) -> str:
    """Initiate a transfer, seal its lock tx, and set the row status/age."""
    transfer = bridge.initiate_transfer(
        source_chain=SOURCE,
        target_chain=TARGET,
        sender=SENDER,
        recipient="0xrecipient",
        amount=AMOUNT,
    )
    stamped = datetime.now(UTC) - timedelta(seconds=age_seconds)
    with Session(engine) as session:
        tx = session.exec(select(Transaction).where(Transaction.tx_hash == transfer.transfer_id)).one()
        tx.block_height = 1
        record = session.get(CrossChainTransfer, transfer.transfer_id)
        assert record is not None
        record.status = status
        record.lock_time = stamped
        record.confirm_time = stamped if status == "confirmed" else None
        session.add(tx)
        session.add(record)
        session.commit()
    return transfer.transfer_id


def _seal_release(engine, transfer_id: str, tx_hash: str = "0x" + "77" * 32) -> str:
    """Seal a BRIDGE_RELEASE for ``transfer_id`` on the target chain."""
    with Session(engine) as session:
        session.add(
            Transaction(
                chain_id=TARGET,
                tx_hash=tx_hash,
                type="BRIDGE_RELEASE",
                status="sealed",
                sender="0xrelayer",
                recipient="0xrecipient",
                value=AMOUNT,
                fee=0,
                nonce=0,
                payload={"transfer_id": transfer_id},
                envelope={},
                block_height=9,
            )
        )
        session.commit()
    return tx_hash


def _record(engine, transfer_id: str) -> CrossChainTransfer:
    with Session(engine) as session:
        record = session.get(CrossChainTransfer, transfer_id)
        assert record is not None
        return record


def test_refund_refused_when_release_sealed_confirmed(bridge, engine):
    """Auditor repro 1: confirmed row past the age gate + sealed release."""
    _seed(engine)
    tid = _lock_transfer(bridge, engine, status="confirmed", age_seconds=7200)
    release_hash = _seal_release(engine, tid)

    with pytest.raises(ValueError, match="already released"):
        bridge.refund_transfer(tid, SENDER)

    record = _record(engine, tid)
    assert record.status == "completed"
    assert record.target_tx_hash == release_hash
    assert record.confirm_time is not None


def test_refund_refused_when_release_sealed_pending(bridge, engine):
    """Auditor repro 2: pending row + sealed release."""
    _seed(engine)
    tid = _lock_transfer(bridge, engine, status="pending")
    _seal_release(engine, tid)

    with pytest.raises(ValueError, match="already released"):
        bridge.refund_transfer(tid, SENDER)

    assert _record(engine, tid).status == "completed"


def test_refund_allowed_when_target_store_not_ready(bridge, engine):
    """No target-chain DB on this node → time gates remain the only guard."""
    _seed(engine)
    tid = _lock_transfer(bridge, engine, status="pending")
    _seal_release(engine, tid)

    with patch.object(bridge, "_chain_db_ready", return_value=False):
        refunded = bridge.refund_transfer(tid, SENDER)
    assert refunded.status == BridgeStatus.refunded
    assert _record(engine, tid).status == "refunded"


def test_release_for_other_transfer_does_not_block_refund(bridge, engine):
    """A sealed release naming a different transfer_id must not gate this refund."""
    _seed(engine)
    tid = _lock_transfer(bridge, engine, status="pending")
    _seal_release(engine, "0x" + "99" * 32)

    refunded = bridge.refund_transfer(tid, SENDER)
    assert refunded.status == BridgeStatus.refunded
    assert _record(engine, tid).status == "refunded"


def test_no_release_evidence_refund_still_works(bridge, engine):
    """Baseline: pending row with no release anywhere refunds as before."""
    _seed(engine)
    tid = _lock_transfer(bridge, engine, status="pending")

    refunded = bridge.refund_transfer(tid, SENDER)
    assert refunded.status == BridgeStatus.refunded
    assert _record(engine, tid).status == "refunded"
