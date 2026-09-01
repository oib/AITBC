"""Tests for the ZK-failure auto-refund sweeper."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlmodel import Session, select

from aitbc_shared import JobPayment, PaymentEscrow
from coordinator_api.contexts.infrastructure.domain.job import Job
from coordinator_api.contexts.payments.services.zk_refund_sweeper import ZkRefundSweeper


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


def _fake_refund_success(session: Session, tx_hash: str = "0xdeadbeef"):
    """Return an async callable that simulates a real, on-chain refund."""

    async def _refund(client_id: str, job_id: str, payment_id: str, reason: str) -> bool:
        payment = session.get(JobPayment, payment_id)
        payment.status = "refunded"
        payment.refund_transaction_hash = tx_hash
        payment.refunded_at = datetime.now(UTC)
        payment.updated_at = datetime.now(UTC)
        session.add(payment)
        escrow = session.exec(select(PaymentEscrow).where(PaymentEscrow.payment_id == payment_id)).first()
        if escrow:
            escrow.is_refunded = True
            escrow.is_active = False
            escrow.refunded_at = datetime.now(UTC)
            session.add(escrow)
        session.commit()
        return True

    return _refund


@pytest.mark.unit
class TestZkRefundSweeper:
    """ZkRefundSweeper finds and refunds jobs whose ZK receipt did not verify."""

    @patch("coordinator_api.contexts.payments.services.zk_refund_sweeper.PaymentService")
    def test_sweeper_refunds_failed_zk_escrowed_job(self, mock_service_cls, sweep_session):
        """An escrowed, completed job with a failed ZK receipt is refunded."""
        job_id = "job-zk-fail-1"
        payment_id = "pay-zk-fail-1"
        _make_job_and_payment(
            sweep_session,
            job_id,
            payment_id,
            receipt={"zk_status": "unsupported_model", "computation_correct": False},
        )

        mock_service = MagicMock()
        mock_service.refund_payment = AsyncMock(side_effect=_fake_refund_success(sweep_session))
        mock_service_cls.return_value = mock_service

        counts = asyncio.run(ZkRefundSweeper(session_factory=lambda: sweep_session).run_once())

        assert counts["candidates"] == 1
        assert counts["refunded"] == 1
        assert counts["failed"] == 0
        mock_service.refund_payment.assert_called_once()

        job = sweep_session.get(Job, job_id)
        assert job.payment_status == "refunded"
        payment = sweep_session.get(JobPayment, payment_id)
        assert payment.status == "refunded"
        assert payment.refund_transaction_hash == "0xdeadbeef"

    @patch("coordinator_api.contexts.payments.services.zk_refund_sweeper.PaymentService")
    def test_sweeper_skips_valid_zk_receipt(self, mock_service_cls, sweep_session):
        """A job with a valid ZK receipt is not refunded."""
        job_id = "job-zk-ok-1"
        payment_id = "pay-zk-ok-1"
        _make_job_and_payment(
            sweep_session,
            job_id,
            payment_id,
            receipt={"zk_status": "verified", "computation_correct": True},
        )

        mock_service = MagicMock()
        mock_service_cls.return_value = mock_service

        counts = asyncio.run(ZkRefundSweeper(session_factory=lambda: sweep_session).run_once())

        assert counts["candidates"] == 0
        assert counts["refunded"] == 0
        mock_service.refund_payment.assert_not_called()

    @patch("coordinator_api.contexts.payments.services.zk_refund_sweeper.PaymentService")
    def test_sweeper_skips_tee_attested_unsupported_model(self, mock_service_cls, sweep_session):
        """A llama3.2:3b job attested by a registered TEE is not a failed ZK receipt."""
        job_id = "job-tee-ok-1"
        payment_id = "pay-tee-ok-1"
        job, _payment = _make_job_and_payment(
            sweep_session,
            job_id,
            payment_id,
            receipt={"zk_status": "tee_attested", "computation_correct": True, "tee_status": "verified"},
        )
        job.payload = {"type": "inference", "model": "llama3.2:3b"}
        sweep_session.add(job)
        sweep_session.commit()

        mock_service = MagicMock()
        mock_service_cls.return_value = mock_service

        counts = asyncio.run(ZkRefundSweeper(session_factory=lambda: sweep_session).run_once())

        assert counts["candidates"] == 0
        mock_service.refund_payment.assert_not_called()

    @patch("coordinator_api.contexts.payments.services.zk_refund_sweeper.PaymentService")
    def test_sweeper_respects_open_acceptance_window(self, mock_service_cls, sweep_session):
        """A pending_acceptance job inside its acceptance window is not refunded yet."""
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

        mock_service = MagicMock()
        mock_service_cls.return_value = mock_service

        counts = asyncio.run(ZkRefundSweeper(session_factory=lambda: sweep_session).run_once())

        assert counts["candidates"] == 0
        mock_service.refund_payment.assert_not_called()

    @patch("coordinator_api.contexts.payments.services.zk_refund_sweeper.PaymentService")
    def test_sweeper_refunds_after_acceptance_window_expires(self, mock_service_cls, sweep_session):
        """A pending_acceptance job whose window has expired and has bad ZK is refunded."""
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

        mock_service = MagicMock()
        mock_service.refund_payment = AsyncMock(side_effect=_fake_refund_success(sweep_session, "0xcafebabe"))
        mock_service_cls.return_value = mock_service

        counts = asyncio.run(ZkRefundSweeper(session_factory=lambda: sweep_session).run_once())

        assert counts["candidates"] == 1
        assert counts["refunded"] == 1
        mock_service.refund_payment.assert_called_once()

        job = sweep_session.get(Job, job_id)
        assert job.payment_status == "refunded"
        payment = sweep_session.get(JobPayment, payment_id)
        assert payment.status == "refunded"
        assert payment.refund_transaction_hash == "0xcafebabe"

    @patch("coordinator_api.contexts.payments.services.zk_refund_sweeper.PaymentService")
    def test_sweeper_skips_jobs_not_completed_long_enough(self, mock_service_cls, sweep_session):
        """A job completed inside the min-age grace period is not refunded."""
        job_id = "job-zk-recent-1"
        payment_id = "pay-zk-recent-1"
        _make_job_and_payment(
            sweep_session,
            job_id,
            payment_id,
            receipt={"zk_status": "unsupported_model", "computation_correct": False},
            completed_at=datetime.now(UTC) - timedelta(seconds=10),
        )

        mock_service = MagicMock()
        mock_service_cls.return_value = mock_service

        counts = asyncio.run(
            ZkRefundSweeper(
                session_factory=lambda: sweep_session,
                min_age_seconds=120,
            ).run_once()
        )

        assert counts["candidates"] == 0
        mock_service.refund_payment.assert_not_called()

    @patch("coordinator_api.contexts.payments.services.zk_refund_sweeper.PaymentService")
    def test_sweeper_treats_refund_without_hash_as_failed(self, mock_service_cls, sweep_session):
        """A PaymentService that returns True without an on-chain hash is treated as failed."""
        job_id = "job-zk-unbacked-1"
        payment_id = "pay-zk-unbacked-1"
        _make_job_and_payment(
            sweep_session,
            job_id,
            payment_id,
            receipt={"zk_status": "unsupported_model", "computation_correct": False},
        )

        mock_service = MagicMock()
        # PaymentService says it refunded, but it did not leave an on-chain record.
        mock_service.refund_payment = AsyncMock(return_value=True)
        mock_service_cls.return_value = mock_service

        counts = asyncio.run(ZkRefundSweeper(session_factory=lambda: sweep_session).run_once())

        assert counts["candidates"] == 1
        assert counts["refunded"] == 0
        assert counts["failed"] == 1
        mock_service.refund_payment.assert_called_once()

        job = sweep_session.get(Job, job_id)
        assert job.payment_status == "failed"
        payment = sweep_session.get(JobPayment, payment_id)
        assert payment.status == "failed"
        assert payment.refund_transaction_hash is None
        assert payment.refunded_at is None
        escrow = sweep_session.exec(select(PaymentEscrow).where(PaymentEscrow.payment_id == payment_id)).first()
        assert escrow.is_refunded is False
        assert escrow.is_active is False

    @patch("coordinator_api.contexts.payments.services.zk_refund_sweeper.PaymentService")
    def test_sweeper_skips_payment_with_refund_hash(self, mock_service_cls, sweep_session):
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

        mock_service = MagicMock()
        mock_service_cls.return_value = mock_service

        counts = asyncio.run(ZkRefundSweeper(session_factory=lambda: sweep_session).run_once())

        assert counts["candidates"] == 0
        assert counts["refunded"] == 0
        assert counts["failed"] == 0
        mock_service.refund_payment.assert_not_called()

    @patch("coordinator_api.contexts.payments.services.zk_refund_sweeper.PaymentService")
    def test_sweeper_skips_unbacked_payment(self, mock_service_cls, sweep_session):
        """A payment that was never backed by an on-chain escrow lock is not refunded."""
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

        mock_service = MagicMock()
        mock_service.refund_payment = AsyncMock(return_value=False)
        mock_service_cls.return_value = mock_service

        counts = asyncio.run(ZkRefundSweeper(session_factory=lambda: sweep_session).run_once())

        assert counts["candidates"] == 0
        assert counts["refunded"] == 0
        mock_service.refund_payment.assert_not_called()

    @patch("coordinator_api.contexts.payments.services.zk_refund_sweeper.PaymentService")
    def test_sweeper_downgrades_stale_refunded_without_hash(self, mock_service_cls, sweep_session):
        """A payment marked refunded but with no on-chain hash is downgraded to failed."""
        job_id = "job-zk-stale-1"
        payment_id = "pay-zk-stale-1"
        _make_job_and_payment(
            sweep_session,
            job_id,
            payment_id,
            payment_status="refunded",
            receipt={"zk_status": "unsupported_model", "computation_correct": False},
        )
        payment = sweep_session.get(JobPayment, payment_id)
        payment.refund_transaction_hash = None
        payment.refunded_at = None
        sweep_session.add(payment)
        escrow = sweep_session.exec(select(PaymentEscrow).where(PaymentEscrow.payment_id == payment_id)).first()
        escrow.is_refunded = True
        escrow.is_active = False
        sweep_session.add(escrow)
        sweep_session.commit()

        mock_service = MagicMock()
        # PaymentService could not refund (e.g., escrow not found on chain).
        mock_service.refund_payment = AsyncMock(return_value=False)
        mock_service_cls.return_value = mock_service

        counts = asyncio.run(ZkRefundSweeper(session_factory=lambda: sweep_session).run_once())

        assert counts["candidates"] == 1
        assert counts["refunded"] == 0
        assert counts["failed"] == 1
        mock_service.refund_payment.assert_called_once()

        job = sweep_session.get(Job, job_id)
        payment = sweep_session.get(JobPayment, payment_id)
        escrow = sweep_session.exec(select(PaymentEscrow).where(PaymentEscrow.payment_id == payment_id)).first()
        assert job.payment_status == "failed"
        assert payment.status == "failed"
        assert payment.refund_transaction_hash is None
        assert escrow.is_refunded is False
        assert escrow.is_active is False

    @patch("coordinator_api.contexts.payments.services.zk_refund_sweeper.PaymentService")
    def test_sweeper_backfills_stale_refunded_from_chain_hash(self, mock_service_cls, sweep_session):
        """A stale refunded row can be reconciled when PaymentService supplies a hash."""
        job_id = "job-zk-stale-2"
        payment_id = "pay-zk-stale-2"
        _make_job_and_payment(
            sweep_session,
            job_id,
            payment_id,
            payment_status="refunded",
            receipt={"zk_status": "unsupported_model", "computation_correct": False},
        )
        payment = sweep_session.get(JobPayment, payment_id)
        payment.refund_transaction_hash = None
        payment.refunded_at = None
        sweep_session.add(payment)
        sweep_session.commit()

        mock_service = MagicMock()
        mock_service.refund_payment = AsyncMock(side_effect=_fake_refund_success(sweep_session, "0xrestored"))
        mock_service_cls.return_value = mock_service

        counts = asyncio.run(ZkRefundSweeper(session_factory=lambda: sweep_session).run_once())

        assert counts["candidates"] == 1
        assert counts["refunded"] == 1
        assert counts["failed"] == 0

        job = sweep_session.get(Job, job_id)
        payment = sweep_session.get(JobPayment, payment_id)
        assert job.payment_status == "refunded"
        assert payment.refund_transaction_hash == "0xrestored"

    def test_zk_refund_sweeper_enabled_default(self):
        """The sweeper is enabled by default."""
        from coordinator_api.contexts.payments.services.zk_refund_sweeper import (
            zk_refund_sweeper_enabled,
        )

        old = os.environ.pop("COORDINATOR_ZK_REFUND_SWEEP_ENABLED", None)
        try:
            assert zk_refund_sweeper_enabled() is True
        finally:
            if old is not None:
                os.environ["COORDINATOR_ZK_REFUND_SWEEP_ENABLED"] = old
