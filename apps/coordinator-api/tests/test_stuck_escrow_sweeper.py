"""Tests for the stuck-escrow auto-refund sweeper."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlmodel import Session

from aitbc_shared import JobPayment, PaymentEscrow
from coordinator_api.contexts.infrastructure.domain.job import Job
from coordinator_api.contexts.payments.acceptance import DISPUTED
from coordinator_api.contexts.payments.services.stuck_escrow_sweeper import (
    StuckEscrowSweeper,
    stuck_escrow_sweeper_enabled,
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
    state: str = "CANCELED",
    payment_status: str = "escrowed",
    updated_at: datetime | None = None,
    meta_data: dict | None = None,
    window_seconds: int = 0,
) -> tuple[Job, JobPayment]:
    """Create a job/payment/escrow row for stuck-escrow tests."""
    client_id = "client-1"
    if updated_at is None:
        updated_at = datetime.now(UTC) - timedelta(seconds=300)

    job = Job(
        id=job_id,
        client_id=client_id,
        state=state,
        payload={"type": "inference", "model": "linear-1"},
        constraints={},
        payment_id=payment_id,
        payment_status=payment_status,
        requested_at=datetime.now(UTC) - timedelta(seconds=600),
        expires_at=datetime.now(UTC) + timedelta(seconds=600),
    )
    if meta_data and window_seconds > 0:
        opened_at = updated_at
        meta_data = dict(meta_data)
        meta_data["acceptance_opened_at"] = opened_at.isoformat()
        meta_data["acceptance_deadline"] = (opened_at + timedelta(seconds=window_seconds)).isoformat()

    payment = JobPayment(
        id=payment_id,
        job_id=job_id,
        client_id=client_id,
        amount=Decimal("0.001"),
        currency="AITBC",
        status=payment_status,
        payment_method="aitbc_token",
        escrow_address="escrow_abc123",
        updated_at=updated_at,
        meta_data=meta_data or {},
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
class TestStuckEscrowSweeper:
    """StuckEscrowSweeper refunds held escrows for terminal job states."""

    @patch("coordinator_api.contexts.payments.services.stuck_escrow_sweeper.PaymentService")
    def test_sweeper_refunds_canceled_job(self, mock_service_cls, sweep_session):
        """A canceled job with an escrowed payment is refunded."""
        _make_job_and_payment(sweep_session, "job-cancel-1", "pay-cancel-1", state="CANCELED")

        mock_service = MagicMock()
        mock_service.refund_payment = AsyncMock(return_value=True)
        mock_service_cls.return_value = mock_service

        counts = asyncio.run(StuckEscrowSweeper(session_factory=lambda: sweep_session).run_once())

        assert counts["candidates"] == 1
        assert counts["refunded"] == 1
        assert counts["failed"] == 0
        mock_service.refund_payment.assert_called_once()

    @patch("coordinator_api.contexts.payments.services.stuck_escrow_sweeper.PaymentService")
    def test_sweeper_refunds_failed_job(self, mock_service_cls, sweep_session):
        """A failed job with an escrowed payment is refunded."""
        _make_job_and_payment(sweep_session, "job-fail-1", "pay-fail-1", state="FAILED")

        mock_service = MagicMock()
        mock_service.refund_payment = AsyncMock(return_value=True)
        mock_service_cls.return_value = mock_service

        counts = asyncio.run(StuckEscrowSweeper(session_factory=lambda: sweep_session).run_once())

        assert counts["candidates"] == 1
        assert counts["refunded"] == 1

    @patch("coordinator_api.contexts.payments.services.stuck_escrow_sweeper.PaymentService")
    def test_sweeper_refunds_expired_job(self, mock_service_cls, sweep_session):
        """An expired job with an escrowed payment is refunded."""
        _make_job_and_payment(sweep_session, "job-expire-1", "pay-expire-1", state="EXPIRED")

        mock_service = MagicMock()
        mock_service.refund_payment = AsyncMock(return_value=True)
        mock_service_cls.return_value = mock_service

        counts = asyncio.run(StuckEscrowSweeper(session_factory=lambda: sweep_session).run_once())

        assert counts["candidates"] == 1
        assert counts["refunded"] == 1

    @patch("coordinator_api.contexts.payments.services.stuck_escrow_sweeper.PaymentService")
    def test_sweeper_refunds_disputed_job(self, mock_service_cls, sweep_session):
        """A disputed payment older than the dispute grace period is refunded."""
        disputed_at = datetime.now(UTC) - timedelta(seconds=90000)
        _make_job_and_payment(
            sweep_session,
            "job-dispute-1",
            "pay-dispute-1",
            state="COMPLETED",
            payment_status=DISPUTED,
            meta_data={"disputed_at": disputed_at.isoformat()},
        )

        mock_service = MagicMock()
        mock_service.refund_payment = AsyncMock(return_value=True)
        mock_service_cls.return_value = mock_service

        counts = asyncio.run(StuckEscrowSweeper(session_factory=lambda: sweep_session).run_once())

        assert counts["candidates"] == 1
        assert counts["refunded"] == 1

    @patch("coordinator_api.contexts.payments.services.stuck_escrow_sweeper.PaymentService")
    def test_sweeper_skips_recent_dispute(self, mock_service_cls, sweep_session):
        """A recent dispute is not refunded before the operator can rule."""
        disputed_at = datetime.now(UTC) - timedelta(seconds=60)
        _make_job_and_payment(
            sweep_session,
            "job-dispute-2",
            "pay-dispute-2",
            state="COMPLETED",
            payment_status=DISPUTED,
            meta_data={"disputed_at": disputed_at.isoformat()},
        )

        mock_service = MagicMock()
        mock_service_cls.return_value = mock_service

        counts = asyncio.run(StuckEscrowSweeper(session_factory=lambda: sweep_session).run_once())

        assert counts["candidates"] == 0
        mock_service.refund_payment.assert_not_called()

    @patch("coordinator_api.contexts.payments.services.stuck_escrow_sweeper.PaymentService")
    def test_sweeper_skips_recent_cancel(self, mock_service_cls, sweep_session):
        """A recently canceled job is not refunded until the min-age passes."""
        _make_job_and_payment(
            sweep_session,
            "job-cancel-2",
            "pay-cancel-2",
            state="CANCELED",
            updated_at=datetime.now(UTC) - timedelta(seconds=10),
        )

        mock_service = MagicMock()
        mock_service_cls.return_value = mock_service

        counts = asyncio.run(
            StuckEscrowSweeper(
                session_factory=lambda: sweep_session,
                min_age_seconds=120,
            ).run_once()
        )

        assert counts["candidates"] == 0
        mock_service.refund_payment.assert_not_called()

    @patch("coordinator_api.contexts.payments.services.stuck_escrow_sweeper.PaymentService")
    def test_sweeper_skips_released_payments(self, mock_service_cls, sweep_session):
        """A canceled job whose payment is already released is not a candidate."""
        _make_job_and_payment(sweep_session, "job-cancel-3", "pay-cancel-3", state="CANCELED", payment_status="released")

        mock_service = MagicMock()
        mock_service_cls.return_value = mock_service

        counts = asyncio.run(StuckEscrowSweeper(session_factory=lambda: sweep_session).run_once())

        assert counts["candidates"] == 0
        mock_service.refund_payment.assert_not_called()

    def test_stuck_escrow_sweeper_enabled_default(self):
        """The stuck-escrow sweeper is enabled by default."""
        old = os.environ.pop("COORDINATOR_STUCK_ESCROW_SWEEP_ENABLED", None)
        try:
            assert stuck_escrow_sweeper_enabled() is True
        finally:
            if old is not None:
                os.environ["COORDINATOR_STUCK_ESCROW_SWEEP_ENABLED"] = old
