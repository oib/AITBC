"""Tests for the ZK-failure auto-refund sweeper."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlmodel import Session

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
) -> tuple[Job, object]:
    """Create a completed job, payment, and escrow row."""
    from aitbc_shared import JobPayment, PaymentEscrow

    client_id = "client-1"
    constraints = {}
    if zk_required:
        constraints["zk_proof_required"] = True
    payload = {"type": "inference", "model": "linear-1"}
    if completed_at is None:
        completed_at = datetime.now(UTC) - timedelta(seconds=300)

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
        escrowed_at=completed_at,
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
class TestZkRefundSweeper:
    """ZkRefundSweeper finds and refunds jobs whose ZK receipt did not verify."""

    @patch("coordinator_api.contexts.payments.services.zk_refund_sweeper.PaymentService")
    def test_sweeper_refunds_failed_zk_escrowed_job(self, mock_service_cls, sweep_session):
        """An escrowed, completed job with a failed ZK receipt is refunded."""
        from aitbc_shared import JobPayment

        job_id = "job-zk-fail-1"
        payment_id = "pay-zk-fail-1"
        _make_job_and_payment(
            sweep_session,
            job_id,
            payment_id,
            receipt={"zk_status": "unsupported_model", "computation_correct": False},
        )

        mock_service = MagicMock()
        mock_service.refund_payment = AsyncMock(return_value=True)
        mock_service_cls.return_value = mock_service

        counts = asyncio.run(ZkRefundSweeper(session_factory=lambda: sweep_session).run_once())

        assert counts["candidates"] == 1
        assert counts["refunded"] == 1
        assert counts["failed"] == 0
        mock_service.refund_payment.assert_called_once()

        job = sweep_session.get(Job, job_id)
        assert job.payment_status == "refunded"
        payment = sweep_session.get(JobPayment, payment_id)
        assert payment.status == "escrowed"  # PaymentService mock did not update it; real service does.

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
        mock_service.refund_payment = AsyncMock(return_value=True)
        mock_service_cls.return_value = mock_service

        counts = asyncio.run(ZkRefundSweeper(session_factory=lambda: sweep_session).run_once())

        assert counts["candidates"] == 1
        assert counts["refunded"] == 1
        mock_service.refund_payment.assert_called_once()

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
