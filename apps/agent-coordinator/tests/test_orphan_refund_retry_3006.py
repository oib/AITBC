"""#3006 pins: an orphan refund must carry the verified lock identity.

``refund_orphaned`` used to record ``tx_hash_refund`` without ever
backfilling ``tx_hash_lock`` — normal for an orphan, whose original
submit died before ``lock()`` ran. When the refund tx is then
apply-rejected, ``reconcile_rejected_refund`` restores LOCKED, but the
expire sweep's ``_escrow_refund_submitter`` keys off ``tx_hash_lock``:
missing → bookkeeping-only → ``expire_stale`` marks REFUNDED with **no
chain transaction**, stranding the on-chain funds forever.

The sweeper already holds the chain point-read's ``lock_tx_hash`` /
``contract_id`` at refund time — they are now handed to
``refund_orphaned`` and persisted *before* the refund submitter runs, so
a rejected refund retries on-chain like any other locked escrow.
"""

from __future__ import annotations

import os
import time
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("JWT_SECRET", "test-secret-for-agent-coordinator-tests" * 2)

pytest.importorskip("fastapi", reason="agent-coordinator app dependencies not installed")

from agent_app import state  # noqa: E402
from agent_app.lifespan import _escrow_refund_submitter  # noqa: E402
from agent_app.services.chain_escrow import reconcile_rejected_refund  # noqa: E402
from agent_app.services.orphan_escrow_sweeper import OrphanedTaskEscrowSweeper  # noqa: E402

from aitbc.crypto import EscrowStatus, PaymentEscrow  # noqa: E402

CHAIN_ID = "ait-test-chain"
TASK_ID = "atask_3006_orphan"
LOCK_TX = "0x" + "aa" * 32
REFUND_TX = "0x" + "bb" * 32
REFUND_TX_2 = "0x" + "cc" * 32
CONTRACT_ID = "contract-9"


def _live_record() -> dict:
    return {
        "job_id": TASK_ID,
        "contract_id": CONTRACT_ID,
        "state": "funded",
        "status": "locked",
        "buyer": "0xBuyer",
        "provider": "0xAgent",
        "amount": "0.05",
        "released_amount": "0",
        "lock_tx_hash": LOCK_TX,
        "created_at": "2026-11-26T15:00:00+00:00",
    }


class _StubChain:
    """Duck-typed ChainEscrowClient: escrow point-read + refund + tx status."""

    def __init__(self, record=None, tx_status=None, refund_hash=REFUND_TX_2):
        self.record = record
        self.tx_status = tx_status or {}
        self.refunds: list[tuple[str, str]] = []
        self._refund_hash = refund_hash

    def get_escrow_record(self, job_id: str):
        return self.record

    def refund(self, job_id: str, *, reason: str = "timeout"):
        self.refunds.append((job_id, reason))
        return self._refund_hash

    def transaction_status(self, tx_hash: str, chain_id=None):
        return self.tx_status.get(tx_hash)


def _orphan(escrow: PaymentEscrow, age: float = 10_000.0):
    entry = escrow.create_escrow(
        task_id=TASK_ID,
        chain_id=CHAIN_ID,
        requester="0xBuyer",
        agent="0xAgent",
        amount=100,
        fee=1,
    )
    entry.created_at = time.time() - age
    return entry


def _sweeper(escrow: PaymentEscrow, client) -> OrphanedTaskEscrowSweeper:
    return OrphanedTaskEscrowSweeper(
        payment_escrow=escrow,
        escrow_rpc=client,
        load_balancer=MagicMock(get_assignment=MagicMock(return_value=None)),
        grace_seconds=900.0,
    )


def test_refund_orphaned_backfills_lock_identity():
    """Unit: the verified lock hash/contract land on the row even though the
    original submit never recorded them."""
    escrow = PaymentEscrow()
    entry = _orphan(escrow)
    out = escrow.refund_orphaned(
        entry,
        submitter=lambda *_a: REFUND_TX,
        tx_hash_lock=LOCK_TX,
        contract_id=CONTRACT_ID,
    )
    assert out.status == EscrowStatus.REFUNDED
    assert out.tx_hash_lock == LOCK_TX
    assert out.contract_id == CONTRACT_ID
    assert out.metadata["contract_id"] == CONTRACT_ID


def test_refund_orphaned_without_identity_unchanged():
    """Back-compat: no kwargs → no lock fields invented."""
    escrow = PaymentEscrow()
    entry = _orphan(escrow)
    out = escrow.refund_orphaned(entry, submitter=lambda *_a: REFUND_TX)
    assert out.tx_hash_lock is None
    assert out.contract_id is None


def test_sweeper_refund_carries_chain_lock_identity():
    """The sweeper hands the point-read's lock_tx_hash/contract_id through —
    the row is REFUNDED *with* its verified lock identity attached."""
    escrow = PaymentEscrow()
    entry = _orphan(escrow)
    client = _StubChain(record=_live_record())
    counts = _sweeper(escrow, client).run_once()
    assert counts["refunded"] == 1
    refreshed = escrow.get_escrow(entry.escrow_id)
    assert refreshed.status == EscrowStatus.REFUNDED
    assert refreshed.tx_hash_lock == LOCK_TX
    assert refreshed.contract_id == CONTRACT_ID


def test_rejected_orphan_refund_retries_on_chain(monkeypatch):
    """Headline defect: refund tx apply-rejected → row must return to a
    retryable LOCKED **with** tx_hash_lock, and the expire sweep must submit
    a real chain refund — never the bookkeeping-only silent REFUNDED."""
    escrow = PaymentEscrow()
    entry = _orphan(escrow)
    chain = _StubChain(record=_live_record(), refund_hash=REFUND_TX)
    assert _sweeper(escrow, chain).run_once()["refunded"] == 1
    assert len(chain.refunds) == 1  # orphan refund submitted (reason=orphaned_lock_no_payment_row)

    # The refund tx dies on-chain; the reconcile proves it and restores LOCKED.
    rejected_rpc = _StubChain(tx_status={REFUND_TX: {"status": "rejected", "rejected_reason": "nonce too low"}})
    assert reconcile_rejected_refund(rejected_rpc, entry) is True
    refreshed = escrow.get_escrow(entry.escrow_id)
    assert refreshed.status == EscrowStatus.LOCKED
    assert refreshed.tx_hash_lock == LOCK_TX  # the backfill survived the transition

    # Past expiry: the expire sweep must build a REAL submitter — the
    # bookkeeping branch (tx_hash_lock missing → submitter None → silent
    # REFUNDED) is exactly the stranding this row fixes.
    refreshed.expires_at = time.time() - 1
    escrow.persist_entry(refreshed)
    expire_chain = _StubChain()
    monkeypatch.setattr(state, "escrow_rpc", expire_chain)

    expired = escrow.expire_stale(refund_submitter_for=_escrow_refund_submitter)

    assert len(expired) == 1
    assert expire_chain.refunds == [(TASK_ID, "expired")]  # chain refund actually submitted
    final = escrow.get_escrow(entry.escrow_id)
    assert final.status == EscrowStatus.REFUNDED
    assert final.tx_hash_refund == REFUND_TX_2
