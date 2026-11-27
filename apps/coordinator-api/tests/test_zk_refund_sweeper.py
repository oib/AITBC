"""Tests for the ZK-gate escrow sweep (#3079: park for review, never auto-refund).

Every candidate is delivered work — a COMPLETED job whose escrow cannot be
released because the decorative ZK gate failed. Auto-refunding it paid the
buyer for work the provider delivered and left the provider unpaid (the
#3067 forensics). The sweep now marks the payment ``settlement_failed`` —
the operator-review state — and never calls ``PaymentService.refund_payment``.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from sqlmodel import Session, select

from aitbc_shared import JobPayment, PaymentEscrow
from coordinator_api.contexts.infrastructure.domain.job import Job
from coordinator_api.contexts.payments.acceptance import DISPUTED, SETTLEMENT_FAILED
from coordinator_api.contexts.payments.services.zk_refund_sweeper import (
    META_ZK_GATE_REVIEW,
    META_ZK_GATE_REVIEW_STATUS,
    ZkRefundSweeper,
)


@pytest.fixture
def sweep_session(db_engine) -> Generator[Session]:
    with Session(db_engine) as session:
        yield session


def _make_job_and_payment(
    session: Session,
    job_id: str,
    payment_id: str,
    *,
    payment_status: str = "escrowed",
    receipt: dict | None = None,
    completed_at: datetime | None = None,
    zk_required: bool = True,
    window_seconds: int = 0,
) -> tuple[Job, JobPayment]:
    """Create a completed job, payment, and escrow row."""
    client_id = "client-1"
    constraints = {}
    if zk_required:
        constraints["zk_proof_required"] = True
    payload = {"type": "inference", "model": "linear-1"}
    if completed_at is None:
        completed_at = datetime.now(UTC) - timedelta(seconds=300)
    escrowed_at = completed_at

    job = Job(
        id=job_id,
        client_id=client_id,
        state="COMPLETED",
        payload=payload,
        constraints=constraints,
        payment_id=payment_id,
        payment_status=payment_status,
        completed_at=completed_at,
        receipt=receipt,
        # A receipt of record needs a receipt_id (SEC-20): without one the gate sees no receipt.
        receipt_id=f"r-{job_id}" if receipt else None,
    )
    meta = {}
    if window_seconds > 0:
        opened_at = completed_at
        meta["acceptance_opened_at"] = opened_at.isoformat()
        meta["acceptance_deadline"] = (opened_at + timedelta(seconds=window_seconds)).isoformat()
    payment = JobPayment(
        id=payment_id,
        job_id=job_id,
        client_id=client_id,
        amount=Decimal("0.001"),
        currency="AITBC",
        status=payment_status,
        payment_method="aitbc_token",
        escrow_address="escrow_abc123",
        escrowed_at=escrowed_at,
        meta_data=meta,
    )
    escrow = PaymentEscrow(
        payment_id=payment_id,
        amount=Decimal("0.001"),
        currency="AITBC",
        address="escrow_address_for_payment",
        is_active=True,
        is_released=False,
        is_refunded=False,
    )
    session.add(job)
    session.add(payment)
    session.add(escrow)
    session.commit()
    return job, payment


@pytest.mark.unit
class TestZkEscrowSweepParksForReview:
    """ZkRefundSweeper parks gate-failed escrows; it never moves money."""

    def test_sweeper_parks_failed_zk_escrowed_job_without_refunding(self, sweep_session):
        """An escrowed, completed job with a failed ZK receipt is parked, not refunded."""
        job_id = "job-zk-fail-1"
        payment_id = "pay-zk-fail-1"
        _make_job_and_payment(
            sweep_session,
            job_id,
            payment_id,
            receipt={"zk_status": "unsupported_model", "computation_correct": False},
        )

        # Mutation guard: the sweeper module must not even import the refund path.
        import coordinator_api.contexts.payments.services.zk_refund_sweeper as sweeper_module

        assert not hasattr(sweeper_module, "PaymentService")

        counts = asyncio.run(ZkRefundSweeper(session_factory=lambda: sweep_session).run_once())

        assert counts["candidates"] == 1
        assert counts["parked"] == 1
        assert counts["failed"] == 0

        job = sweep_session.get(Job, job_id)
        assert job.payment_status == SETTLEMENT_FAILED
        payment = sweep_session.get(JobPayment, payment_id)
        assert payment.status == SETTLEMENT_FAILED
        assert payment.refund_transaction_hash is None
        assert payment.meta_data[META_ZK_GATE_REVIEW] is True
        assert payment.meta_data[META_ZK_GATE_REVIEW_STATUS] == "unsupported_model"
        # The escrow stays locked on-chain for the operator to resolve.
        escrow = sweep_session.exec(select(PaymentEscrow).where(PaymentEscrow.payment_id == payment_id)).first()
        assert escrow.is_active is True
        assert escrow.is_refunded is False

    def test_park_preserves_concurrent_meta_keys(self, sweep_session):
        """The park merges meta_data — a key written between selection and
        park (e.g. dispute_reason) must survive, not be erased."""
        job_id = "job-zk-meta-1"
        payment_id = "pay-zk-meta-1"
        _make_job_and_payment(
            sweep_session,
            job_id,
            payment_id,
            receipt={"zk_status": "unsupported_model", "computation_correct": False},
        )
        payment = sweep_session.get(JobPayment, payment_id)
        payment.meta_data = {"dispute_reason": "customer rejected output"}
        sweep_session.add(payment)
        sweep_session.commit()

        counts = asyncio.run(ZkRefundSweeper(session_factory=lambda: sweep_session).run_once())

        assert counts["parked"] == 1
        payment = sweep_session.get(JobPayment, payment_id)
        assert payment.status == SETTLEMENT_FAILED
        assert payment.meta_data["dispute_reason"] == "customer rejected output"
        assert payment.meta_data[META_ZK_GATE_REVIEW] is True

    def test_park_loses_cas_when_payment_moved_to_disputed(self, sweep_session, db_engine):
        """Lost-race pin: a payment moved to DISPUTED between candidate
        selection and the park write must NOT be overwritten — the
        conditional UPDATE arbitrates, same as the refund/release CAS paths."""
        job_id = "job-zk-race-1"
        payment_id = "pay-zk-race-1"
        job, stale_payment = _make_job_and_payment(
            sweep_session,
            job_id,
            payment_id,
            receipt={"zk_status": "unsupported_model", "computation_correct": False},
        )
        # Load the attributes into the identity map NOW (the creation commit
        # expired them): from here on stale_payment reads "escrowed" without
        # touching the DB — exactly what _find_candidates hands the park.
        assert stale_payment.status == "escrowed"
        # A second session — the concurrent writer — disputes the payment in
        # the window between _find_candidates and the park commit.
        with Session(db_engine) as other:
            moved = other.get(JobPayment, payment_id)
            moved.status = DISPUTED
            moved.meta_data = {"dispute_reason": "operator reviewing"}
            other.add(moved)
            other.commit()
        assert stale_payment.status == "escrowed"  # identity map never saw the move

        won = ZkRefundSweeper(session_factory=lambda: sweep_session)._park_for_operator_review(
            sweep_session, job, stale_payment
        )

        assert won is False
        sweep_session.expire_all()
        payment = sweep_session.get(JobPayment, payment_id)
        assert payment.status == DISPUTED
        assert payment.meta_data == {"dispute_reason": "operator reviewing"}
        job = sweep_session.get(Job, job_id)
        assert job.payment_status == "escrowed"

    def test_parked_payment_is_not_a_candidate_again(self, sweep_session):
        """settlement_failed rows leave the candidate set — one park, no loop."""
        job_id = "job-zk-parked-1"
        payment_id = "pay-zk-parked-1"
        _make_job_and_payment(
            sweep_session,
            job_id,
            payment_id,
            receipt={"zk_status": "unsupported_model", "computation_correct": False},
        )

        first = asyncio.run(ZkRefundSweeper(session_factory=lambda: sweep_session).run_once())
        assert first["parked"] == 1

        second = asyncio.run(ZkRefundSweeper(session_factory=lambda: sweep_session).run_once())
        assert second["candidates"] == 0
        assert second["parked"] == 0

    def test_sweeper_skips_valid_zk_receipt(self, sweep_session):
        """A job with a valid ZK receipt is not parked."""
        job_id = "job-zk-ok-1"
        payment_id = "pay-zk-ok-1"
        _make_job_and_payment(
            sweep_session,
            job_id,
            payment_id,
            receipt={"zk_status": "verified", "computation_correct": True},
        )

        counts = asyncio.run(ZkRefundSweeper(session_factory=lambda: sweep_session).run_once())

        assert counts["candidates"] == 0
        payment = sweep_session.get(JobPayment, payment_id)
        assert payment.status == "escrowed"

    def test_sweeper_respects_open_acceptance_window(self, sweep_session):
        """A pending_acceptance job inside its acceptance window is not parked yet."""
        job_id = "job-zk-window-1"
        payment_id = "pay-zk-window-1"
        future = datetime.now(UTC) + timedelta(seconds=300)
        _make_job_and_payment(
            sweep_session,
            job_id,
            payment_id,
            payment_status="pending_acceptance",
            receipt={"zk_status": "unsupported_model", "computation_correct": False},
            window_seconds=3600,
            completed_at=future - timedelta(seconds=300),
        )

        counts = asyncio.run(ZkRefundSweeper(session_factory=lambda: sweep_session).run_once())

        assert counts["candidates"] == 0
        payment = sweep_session.get(JobPayment, payment_id)
        assert payment.status == "pending_acceptance"

    def test_sweeper_parks_after_acceptance_window_expires(self, sweep_session):
        """A pending_acceptance job whose window expired and has bad ZK is parked."""
        job_id = "job-zk-expired-1"
        payment_id = "pay-zk-expired-1"
        completed_at = datetime.now(UTC) - timedelta(seconds=4000)
        _make_job_and_payment(
            sweep_session,
            job_id,
            payment_id,
            payment_status="pending_acceptance",
            receipt={"zk_status": "computation_incorrect", "computation_correct": False},
            window_seconds=3600,
            completed_at=completed_at,
        )

        counts = asyncio.run(ZkRefundSweeper(session_factory=lambda: sweep_session).run_once())

        assert counts["candidates"] == 1
        assert counts["parked"] == 1
        payment = sweep_session.get(JobPayment, payment_id)
        assert payment.status == SETTLEMENT_FAILED
        assert payment.refund_transaction_hash is None

    def test_sweeper_skips_jobs_not_completed_long_enough(self, sweep_session):
        """A job completed inside the min-age grace period is not parked."""
        job_id = "job-zk-recent-1"
        payment_id = "pay-zk-recent-1"
        _make_job_and_payment(
            sweep_session,
            job_id,
            payment_id,
            receipt={"zk_status": "unsupported_model", "computation_correct": False},
            completed_at=datetime.now(UTC) - timedelta(seconds=10),
        )

        counts = asyncio.run(
            ZkRefundSweeper(
                session_factory=lambda: sweep_session,
                min_age_seconds=120,
            ).run_once()
        )

        assert counts["candidates"] == 0
        payment = sweep_session.get(JobPayment, payment_id)
        assert payment.status == "escrowed"

    def test_sweeper_skips_payment_with_refund_hash(self, sweep_session):
        """A payment that already has a refund hash is not processed again."""
        job_id = "job-zk-dedup-hash-1"
        payment_id = "pay-zk-dedup-hash-1"
        _make_job_and_payment(
            sweep_session,
            job_id,
            payment_id,
            receipt={"zk_status": "unsupported_model", "computation_correct": False},
        )
        payment = sweep_session.get(JobPayment, payment_id)
        payment.refund_transaction_hash = "0xalreadyrefunded"
        sweep_session.add(payment)
        sweep_session.commit()

        counts = asyncio.run(ZkRefundSweeper(session_factory=lambda: sweep_session).run_once())

        assert counts["candidates"] == 0
        assert counts["parked"] == 0
        assert counts["failed"] == 0

    def test_sweeper_skips_unbacked_payment(self, sweep_session):
        """A payment that was never backed by an on-chain escrow lock is not parked."""
        job_id = "job-zk-unbacked-2"
        payment_id = "pay-zk-unbacked-2"
        _make_job_and_payment(
            sweep_session,
            job_id,
            payment_id,
            receipt={"zk_status": "unsupported_model", "computation_correct": False},
        )
        payment = sweep_session.get(JobPayment, payment_id)
        payment.escrowed_at = None
        sweep_session.add(payment)
        sweep_session.commit()

        counts = asyncio.run(ZkRefundSweeper(session_factory=lambda: sweep_session).run_once())

        assert counts["candidates"] == 0
        assert counts["parked"] == 0

    def test_zk_refund_sweeper_enabled_default(self):
        """The sweeper is enabled by default (it parks; it does not refund)."""
        from coordinator_api.contexts.payments.services.zk_refund_sweeper import (
            zk_refund_sweeper_enabled,
        )

        old = os.environ.pop("COORDINATOR_ZK_REFUND_SWEEP_ENABLED", None)
        try:
            assert zk_refund_sweeper_enabled() is True
        finally:
            if old is not None:
                os.environ["COORDINATOR_ZK_REFUND_SWEEP_ENABLED"] = old

    def test_sweeper_skips_disputed_payment(self, sweep_session):
        """A disputed payment stays with the dispute flow, not the ZK sweep."""
        job_id = "job-zk-disputed-1"
        payment_id = "pay-zk-disputed-1"
        _make_job_and_payment(
            sweep_session,
            job_id,
            payment_id,
            payment_status=DISPUTED,
            receipt={"zk_status": "unsupported_model", "computation_correct": False},
        )

        counts = asyncio.run(ZkRefundSweeper(session_factory=lambda: sweep_session).run_once())

        assert counts["candidates"] == 0
        assert counts["parked"] == 0
        assert counts["failed"] == 0

    def test_sweep_skips_when_another_worker_holds_the_lock(self, sweep_session, tmp_path):
        """The sweep lock is what replaces ``--workers 1``: a second worker skips."""
        import filelock

        lock_path = str(tmp_path / "zk_sweep.lock")
        held = filelock.FileLock(lock_path)
        held.acquire()
        try:
            sweeper = ZkRefundSweeper(session_factory=lambda: sweep_session, lock_path=lock_path)
            counts = asyncio.run(sweeper.run_once())
        finally:
            held.release()

        assert counts == {"candidates": 0, "parked": 0, "failed": 0, "skipped": 1}

    @patch.object(ZkRefundSweeper, "_park_for_operator_review", side_effect=RuntimeError("db exploded"))
    def test_park_failure_counts_failed_and_continues(self, _mock_park, sweep_session):
        """A row that fails to park is counted failed and does not abort the sweep."""
        job_id = "job-zk-failpark-1"
        payment_id = "pay-zk-failpark-1"
        _make_job_and_payment(
            sweep_session,
            job_id,
            payment_id,
            receipt={"zk_status": "unsupported_model", "computation_correct": False},
        )

        counts = asyncio.run(ZkRefundSweeper(session_factory=lambda: sweep_session).run_once())

        assert counts["candidates"] == 1
        assert counts["parked"] == 0
        assert counts["failed"] == 1
        payment = sweep_session.get(JobPayment, payment_id)
        assert payment.status == "escrowed"
