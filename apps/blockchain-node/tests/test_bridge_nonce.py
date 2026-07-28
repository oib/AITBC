"""Regression tests for v0.18.0 B5/B6 — bridge replay persistence & nonce correctness.

- Lock/release/refund paths must maintain account nonce sequences (no more
  hardcoded nonce=0, lock must increment the sender nonce).
- Processed proof hashes must survive a bridge-instance restart (persisted
  on the transfer record), not just the in-memory set.
"""

from unittest.mock import patch

import pytest
from aitbc_chain.cross_chain.bridge import CrossChainBridge
from aitbc_chain.models import Account, Transaction
from sqlmodel import Session, SQLModel, create_engine, select
from sqlalchemy.pool import StaticPool


@pytest.fixture
def engine():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def bridge(engine):
    return CrossChainBridge(lambda: Session(engine))


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


def _txs(engine, tx_type: str) -> list[Transaction]:
    with Session(engine) as session:
        return list(session.exec(select(Transaction).where(Transaction.type == tx_type).order_by(Transaction.id)).all())


def test_lock_increments_sender_nonce(bridge, engine):
    _seed(engine, "chain-a", "0xsender", 10_000)

    bridge.initiate_transfer("chain-a", "chain-b", "0xsender", "0xrecipient", 1000)
    bridge.initiate_transfer("chain-a", "chain-b", "0xsender", "0xrecipient", 2000)

    assert _account(engine, "chain-a", "0xsender").nonce == 2
    lock_txs = _txs(engine, "BRIDGE_LOCK")
    assert [tx.nonce for tx in lock_txs] == [0, 1]


def test_lock_then_release_nonce_sequence(bridge, engine):
    _seed(engine, "chain-a", "0xsender", 10_000)
    _seed(engine, "chain-b", "0xrecipient", 0)

    transfer = bridge.initiate_transfer("chain-a", "chain-b", "0xsender", "0xrecipient", 1000)
    with patch.object(bridge, "_validate_proof", return_value=True):
        bridge.confirm_transfer(transfer.transfer_id, {"lock_tx_hash": transfer.transfer_id})

    # Lock: sender 0 -> 1. Release: recipient 0 -> 1.
    assert _account(engine, "chain-a", "0xsender").nonce == 1
    assert _account(engine, "chain-b", "0xrecipient").nonce == 1
    release_txs = _txs(engine, "BRIDGE_RELEASE")
    assert len(release_txs) == 1
    assert release_txs[0].nonce == 0


def test_lock_then_refund_nonce_sequence(bridge, engine):
    _seed(engine, "chain-a", "0xsender", 10_000)

    transfer = bridge.initiate_transfer("chain-a", "chain-b", "0xsender", "0xrecipient", 1000)
    bridge.refund_transfer(transfer.transfer_id, "0xsender")

    # Lock: 0 -> 1. Refund: 1 -> 2.
    assert _account(engine, "chain-a", "0xsender").nonce == 2
    refund_txs = _txs(engine, "BRIDGE_REFUND")
    assert len(refund_txs) == 1
    assert refund_txs[0].nonce == 1


def test_proof_replay_rejected_after_restart(bridge, engine):
    """A fresh bridge instance (empty in-memory set) must still reject a reused proof."""
    _seed(engine, "chain-a", "0xsender", 10_000)
    _seed(engine, "chain-b", "0xrecipient", 0)

    first = bridge.initiate_transfer("chain-a", "chain-b", "0xsender", "0xrecipient", 1000)
    second = bridge.initiate_transfer("chain-a", "chain-b", "0xsender", "0xrecipient", 2000)
    proof = {"lock_tx_hash": "0xshared-proof"}

    with patch.object(bridge, "_validate_proof", return_value=True):
        bridge.confirm_transfer(first.transfer_id, proof)

    # Simulate a node restart: new instance, in-memory _processed_proofs empty.
    restarted = CrossChainBridge(lambda: Session(engine))
    with patch.object(restarted, "_validate_proof", return_value=True):
        with pytest.raises(ValueError, match="Proof already processed"):
            restarted.confirm_transfer(second.transfer_id, proof)
