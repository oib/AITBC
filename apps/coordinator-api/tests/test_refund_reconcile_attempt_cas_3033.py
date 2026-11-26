"""#3033 pins: stale refund-audit evidence must not overwrite a newer attempt.

``_audit_one_refund_hash`` snapshots ``refund_transaction_hash`` before the
chain awaits; ``_requeue_dead_refund`` / ``_readopt_refund_hash`` then
refresh the row but historically checked only ``status == "refunded"``. A
concurrent worker persisting a *newer* refund attempt (new hash, row
re-marked refunded) in that window got its evidence destroyed: the stale
audit cleared or overwrote the replacement hash and rolled back the job/
escrow bookkeeping for the previous attempt. The fix CAS-guards both
writes on the recorded hash still being the probed one.
"""

from __future__ import annotations

from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from sqlmodel import Session, select

from aitbc_shared import JobPayment, PaymentEscrow

from coordinator_api.contexts.infrastructure.domain.job import Job
from coordinator_api.contexts.payments.services.settlement_reconciler import SettlementReconciler

JOB_ID = "job-cas-3033"
OLD_HASH = "0xold-dead-attempt"
NEW_HASH = "0xnewer-attempt"
SEALED_OTHER = "0xsealed-replacement"


def _seed(db_session) -> tuple[Job, JobPayment, PaymentEscrow]:
    now = datetime.now(UTC)
    job = Job(
        id=JOB_ID,
        client_id="client-1",
        state="FAILED",
        payload={},
        constraints={},
        expires_at=now + timedelta(hours=1),
        payment_status="refunded",
    )
    payment = JobPayment(
        job_id=JOB_ID,
        amount=Decimal("1.0"),
        status="refunded",
        refund_transaction_hash=OLD_HASH,
        refunded_at=now - timedelta(hours=2),
        meta_data={},
    )
    db_session.add(job)
    db_session.add(payment)
    db_session.flush()
    escrow = PaymentEscrow(
        payment_id=payment.id,
        amount=Decimal("1.0"),
        address="0xescrow",
        is_active=False,
        is_refunded=True,
        refunded_at=now - timedelta(hours=2),
    )
    db_session.add(escrow)
    db_session.commit()
    return job, payment, escrow


def _persist_newer_attempt(db_engine, payment_id: str) -> None:
    """The 'other worker': a separate transaction persists a newer refund
    attempt — new hash on the still-refunded row."""
    with Session(db_engine) as other:
        payment = other.get(JobPayment, payment_id)
        assert payment is not None
        payment.refund_transaction_hash = NEW_HASH
        payment.refunded_at = datetime.now(UTC)
        job = other.get(Job, JOB_ID)
        assert job is not None
        job.payment_status = "refunded"
        other.add(payment)
        other.add(job)
        other.commit()


def _reconciler(db_session) -> SettlementReconciler:
    return SettlementReconciler(session_factory=lambda: nullcontext(db_session), batch_size=2, min_age_seconds=60)


@pytest.mark.asyncio
async def test_stale_requeue_cannot_clobber_a_newer_attempt(db_session, db_engine):
    """Recorded hash proves dead + no sealed refund → requeue. A newer
    attempt lands mid-probe: the requeue must NOT fire — the row keeps its
    new hash, refunded status, and the job/escrow bookkeeping stays put."""
    job, payment, escrow = _seed(db_session)

    async def _sealed_after_newer_attempt(_self, client, rpc, job_id, tx_type):
        _persist_newer_attempt(db_engine, payment.id)
        return set()  # no sealed ESCROW_REFUND → would requeue on stale evidence

    reconciler = _reconciler(db_session)
    with (
        patch.object(SettlementReconciler, "_recorded_hash_state", new=AsyncMock(return_value=False)),
        patch.object(SettlementReconciler, "_sealed_settlement_hashes", new=_sealed_after_newer_attempt),
    ):
        counts = await reconciler._audit_refund_hashes()

    assert counts["refund_requeued"] == 0
    db_session.expire_all()
    fresh = db_session.get(JobPayment, payment.id)
    assert fresh.status == "refunded"
    assert fresh.refund_transaction_hash == NEW_HASH
    assert db_session.get(Job, JOB_ID).payment_status == "refunded"
    esc = db_session.execute(select(PaymentEscrow).where(PaymentEscrow.payment_id == payment.id)).scalars().first()
    assert esc.is_refunded is True and esc.is_active is False


@pytest.mark.asyncio
async def test_stale_readopt_cannot_overwrite_a_newer_attempt(db_session, db_engine):
    """Recorded hash dead + exactly one other sealed refund → readopt. A
    newer attempt lands mid-probe: the adoption must NOT fire — the row
    keeps the newer hash instead of the audit's stale replacement."""
    job, payment, escrow = _seed(db_session)

    async def _sealed_after_newer_attempt(_self, client, rpc, job_id, tx_type):
        _persist_newer_attempt(db_engine, payment.id)
        return {SEALED_OTHER}

    reconciler = _reconciler(db_session)
    with (
        patch.object(SettlementReconciler, "_recorded_hash_state", new=AsyncMock(return_value=False)),
        patch.object(SettlementReconciler, "_sealed_settlement_hashes", new=_sealed_after_newer_attempt),
    ):
        counts = await reconciler._audit_refund_hashes()

    assert counts["refund_hash_readopted"] == 0
    db_session.expire_all()
    fresh = db_session.get(JobPayment, payment.id)
    assert fresh.status == "refunded"
    assert fresh.refund_transaction_hash == NEW_HASH


@pytest.mark.asyncio
async def test_uncontended_requeue_still_fires(db_session):
    """Control: with no concurrent write the dead-hash requeue proceeds
    exactly as before — the CAS only blocks *changed* attempts."""
    job, payment, escrow = _seed(db_session)

    reconciler = _reconciler(db_session)
    with (
        patch.object(SettlementReconciler, "_recorded_hash_state", new=AsyncMock(return_value=False)),
        patch.object(SettlementReconciler, "_sealed_settlement_hashes", new=AsyncMock(return_value=set())),
    ):
        counts = await reconciler._audit_refund_hashes()

    assert counts["refund_requeued"] == 1
    db_session.expire_all()
    fresh = db_session.get(JobPayment, payment.id)
    assert fresh.status == "settlement_failed"
    assert fresh.refund_transaction_hash is None
    assert db_session.get(Job, JOB_ID).payment_status == "settlement_failed"
    esc = db_session.execute(select(PaymentEscrow).where(PaymentEscrow.payment_id == payment.id)).scalars().first()
    assert esc.is_refunded is False and esc.is_active is True
