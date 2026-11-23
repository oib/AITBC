"""Admission refuses a second ESCROW_LOCK for a job that already has one.

CHAIN-ESCROW-DOUBLE-LOCK-IDENTICAL-BINDING-1 (#2673): dead-envelope retries
re-sign a fresh lock each attempt — the new nonce mints a new tx hash, so
hash dedup cannot see the replay, and two payload-equal locks both sealed on
job 97ac1ec8… (@35533+@35534), double-funding custody to 1.0 AIT against a
0.5 AIT job. The door now refuses any second lock for a job_id that already
has a pending (different-hash) or confirmed lock; the create route adopts a
pending identical-binding lock before it reaches this gate.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from aitbc.utils import DEFAULT_TX_FEE_UNITS
from aitbc_chain.base_models import Account, Transaction
from aitbc_chain.database import chain_metadata
from aitbc_chain.mempool import InMemoryMempool
from aitbc_chain.rpc.transactions import _validate_transaction_admission

CHAIN = "ait-test"
BUYER = "0x" + "b0" * 20
PROVIDER = "0x" + "9e" * 20
NODE_WALLET = "0x" + "77" * 20
JOB = "job-double-lock"
OTHER_JOB = "job-other"


@pytest.fixture
def session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    chain_metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Account(chain_id=CHAIN, address=BUYER, balance=1_000_000_000, nonce=0))
        s.commit()
        yield s


@pytest.fixture
def door(session, monkeypatch):
    @contextmanager
    def _scope():
        yield session

    monkeypatch.setattr("aitbc_chain.rpc.transactions.session_scope", _scope)
    monkeypatch.setattr("aitbc_chain.rpc.utils.get_supported_chains", lambda: [CHAIN])
    return session


def _lock_tx(job_id: str = JOB, nonce: int = 0, amount: int = 500, **overrides: Any) -> dict[str, Any]:
    tx: dict[str, Any] = {
        "from": BUYER,
        "to": NODE_WALLET,
        "amount": amount,
        "fee": DEFAULT_TX_FEE_UNITS,
        "nonce": nonce,
        "type": "ESCROW_LOCK",
        "chain_id": CHAIN,
        "payload": {"action": "escrow_lock", "job_id": job_id, "provider": PROVIDER},
    }
    tx.update(overrides)
    return tx


def _sealed_lock(session: Session, job_id: str = JOB, tx_hash: str = "0x" + "aa" * 32, status: str = "confirmed") -> None:
    session.add(
        Transaction(
            chain_id=CHAIN,
            tx_hash=tx_hash,
            sender=BUYER,
            recipient=NODE_WALLET,
            type="ESCROW_LOCK",
            payload={"action": "escrow_lock", "job_id": job_id, "provider": PROVIDER},
            status=status,
            value=500,
        )
    )
    session.commit()


def test_pending_identical_binding_lock_is_refused(door) -> None:
    """The observed failure: a re-signed retry (new nonce → new hash) while the
    first envelope is still pending must not reach the mempool."""
    mempool = InMemoryMempool()
    mempool.add(_lock_tx(nonce=0), chain_id=CHAIN)
    with pytest.raises(ValueError, match="already pending"):
        _validate_transaction_admission(_lock_tx(nonce=1), mempool)


def test_pending_different_binding_lock_is_refused(door) -> None:
    """A second lock with different terms is just as unsafe — ambiguous
    beneficiary sets are unrefundable."""
    mempool = InMemoryMempool()
    mempool.add(_lock_tx(nonce=0), chain_id=CHAIN)
    with pytest.raises(ValueError, match="already pending"):
        _validate_transaction_admission(_lock_tx(nonce=1, amount=900), mempool)


def test_pending_lock_for_other_job_is_admitted(door) -> None:
    mempool = InMemoryMempool()
    mempool.add(_lock_tx(job_id=OTHER_JOB, nonce=0), chain_id=CHAIN)
    _validate_transaction_admission(_lock_tx(nonce=0), mempool)


def test_identical_resubmit_is_exempt_for_hash_dedup(door) -> None:
    """Byte-identical resubmission keeps the old behavior — mempool.add's own
    hash dedup returns the existing hash rather than erroring."""
    mempool = InMemoryMempool()
    tx = _lock_tx(nonce=0)
    mempool.add(tx, chain_id=CHAIN)
    _validate_transaction_admission(dict(tx), mempool)


def test_sealed_lock_refuses_second_lock(door) -> None:
    _sealed_lock(door)
    with pytest.raises(ValueError, match="already sealed"):
        _validate_transaction_admission(_lock_tx(nonce=1), InMemoryMempool())


def test_failed_lock_does_not_block_retry(door) -> None:
    """Only confirmed locks count — a failed apply leaves the job free to
    re-lock, which is the legitimate retry path."""
    _sealed_lock(door, status="failed")
    _validate_transaction_admission(_lock_tx(nonce=0), InMemoryMempool())


def test_sealed_lock_for_other_job_is_admitted(door) -> None:
    _sealed_lock(door, job_id=OTHER_JOB)
    _validate_transaction_admission(_lock_tx(nonce=0), InMemoryMempool())


def test_non_lock_tx_is_unaffected(door) -> None:
    mempool = InMemoryMempool()
    mempool.add(_lock_tx(nonce=0), chain_id=CHAIN)
    transfer = _lock_tx(nonce=1, type="TRANSFER", payload={})
    _validate_transaction_admission(transfer, mempool)


def test_lock_without_job_id_passes_gate(door) -> None:
    """Payload validation belongs to the apply side; the dedup gate only
    engages on a readable job_id."""
    mempool = InMemoryMempool()
    _validate_transaction_admission(_lock_tx(nonce=0, payload={}), mempool)
