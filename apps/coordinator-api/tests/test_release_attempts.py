"""
Regression tests for the bounded escrow-release retry (triage #5).

Before this, a held payment whose release kept failing -- wrong job state, an
unverifiable receipt, a chain RPC that refuses -- was retried by every sweeper
at every interval forever. `release_payment` now counts attempts in
`meta_data["release_attempts"]` and, past `COORDINATOR_RELEASE_MAX_ATTEMPTS`,
moves the payment to the terminal `settlement_failed` status, which is outside
every release sweeper's candidate set. The escrow stays refundable and an
operator can reset the counter through the admin retry-release route.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlmodel import Session

from aitbc_shared import JobPayment, PaymentEscrow

from coordinator_api.contexts.infrastructure.domain.job import Job
from coordinator_api.contexts.payments.services.payments import PaymentService
from coordinator_api.contexts.payments.services.settlement_reconciler import SettlementReconciler
from coordinator_api.contexts.payments.services.stuck_escrow_sweeper import StuckEscrowSweeper


@pytest.fixture
def payment_session(db_engine) -> Session:
    with Session(db_engine) as session:
        yield session


def _make_job_and_payment(
    session: Session,
    job_id: str,
    payment_id: str,
    *,
    job_state: str = "RUNNING",
    payment_status: str = "escrowed",
    meta: dict | None = None,
) -> None:
    """Create a job, payment and escrow row in the test DB."""
    job = Job(
        id=job_id,
        client_id="client-1",
        state=job_state,
        payload={},
        payment_id=payment_id,
        payment_status=payment_status,
    )
    payment = JobPayment(
        id=payment_id,
        job_id=job_id,
        client_id="client-1",
        amount=5,
        currency="AITBC",
        status=payment_status,
        payment_method="aitbc_token",
        escrow_address="escrow_abc123",
        escrowed_at=datetime.now(UTC),
        meta_data=meta,
    )
    escrow = PaymentEscrow(
        payment_id=payment_id,
        amount=5,
        currency="AITBC",
        address="escrow_address_for_payment",
        is_active=True,
    )
    session.add(job)
    session.add(payment)
    session.add(escrow)
    session.commit()


@pytest.mark.unit
class TestReleaseAttemptBound:
    def test_each_blocked_attempt_is_counted(self, payment_session):
        """A release blocked before the chain call still counts as an attempt."""
        job_id, payment_id = "job-rb-1", "pay-rb-1"
        _make_job_and_payment(payment_session, job_id, payment_id)  # RUNNING job blocks release

        service = PaymentService(payment_session)
        result = asyncio.run(service.release_payment("client-1", job_id, payment_id, "test"))

        assert result is False
        payment = payment_session.get(JobPayment, payment_id)
        assert payment.status == "escrowed"
        assert payment.meta_data["release_attempts"] == 1

    def test_terminal_status_at_the_bound(self, payment_session, monkeypatch):
        """Past the bound the payment goes settlement_failed and retries stop."""
        monkeypatch.setenv("COORDINATOR_RELEASE_MAX_ATTEMPTS", "2")
        job_id, payment_id = "job-rb-2", "pay-rb-2"
        _make_job_and_payment(payment_session, job_id, payment_id)

        service = PaymentService(payment_session)
        assert asyncio.run(service.release_payment("client-1", job_id, payment_id, "t")) is False
        assert asyncio.run(service.release_payment("client-1", job_id, payment_id, "t")) is False
        assert asyncio.run(service.release_payment("client-1", job_id, payment_id, "t")) is False

        payment = payment_session.get(JobPayment, payment_id)
        job = payment_session.get(Job, job_id)
        assert payment.status == "settlement_failed"
        assert job.payment_status == "settlement_failed"
        assert payment.meta_data["release_attempts"] == 2
        assert payment.meta_data["release_blocked_at"]

        # Terminal state is outside HELD_STATES: further calls return before any
        # attempt bookkeeping -- the counter does not grow past the bound.
        assert asyncio.run(service.release_payment("client-1", job_id, payment_id, "t")) is False
        payment_session.refresh(payment)
        assert payment.meta_data["release_attempts"] == 2

    def test_reconciler_ignores_settlement_failed(self, payment_session):
        """A terminally blocked payment is not a reconciler candidate."""
        job_id, payment_id = "job-rb-3", "pay-rb-3"
        _make_job_and_payment(payment_session, job_id, payment_id, job_state="COMPLETED", payment_status="settlement_failed")
        job = payment_session.get(Job, job_id)
        job.completed_at = datetime.now(UTC) - timedelta(hours=1)
        payment_session.add(job)
        payment_session.commit()

        reconciler = SettlementReconciler()
        assert reconciler._find_unsettled(payment_session) == []

    def test_stuck_escrow_still_refunds_terminal_payment_on_dead_job(self, payment_session):
        """settlement_failed on a CANCELED job stays inside the refund safety net."""
        job_id, payment_id = "job-rb-4", "pay-rb-4"
        _make_job_and_payment(
            payment_session,
            job_id,
            payment_id,
            job_state="CANCELED",
            payment_status="settlement_failed",
        )
        payment = payment_session.get(JobPayment, payment_id)
        payment.updated_at = datetime.now(UTC) - timedelta(hours=1)
        payment_session.add(payment)
        payment_session.commit()

        sweeper = StuckEscrowSweeper(min_age_seconds=0)
        candidates = sweeper._find_candidates(payment_session)
        assert [p.id for _j, p, _r in candidates] == [payment_id]

    @patch("coordinator_api.contexts.payments.services.payments.AsyncAITBCHTTPClient")
    def test_settlement_failed_stays_refundable(self, mock_client_cls, payment_session):
        """The escrow is still funded, so refund_payment must accept the row."""
        job_id, payment_id = "job-rb-5", "pay-rb-5"
        _make_job_and_payment(payment_session, job_id, payment_id, payment_status="settlement_failed")

        mock_client = AsyncMock()
        mock_client.get.return_value = {"state": "locked"}
        mock_client.post.return_value = {"success": True, "refund_tx_hash": "0xrealrefund"}
        mock_client_cls.return_value = mock_client

        service = PaymentService(payment_session)
        result = asyncio.run(service.refund_payment("client-1", job_id, payment_id, "operator refund"))

        assert result is True
        payment = payment_session.get(JobPayment, payment_id)
        assert payment.status == "refunded"
        assert payment.refund_transaction_hash == "0xrealrefund"


@pytest.mark.unit
class TestAdminRetryRelease:
    def test_retry_resets_and_releases(self, payment_session):
        """The admin route clears the counter, re-arms escrow, and retries once."""
        from coordinator_api.contexts.infrastructure.routers.admin import retry_release

        job_id, payment_id = "job-rb-6", "pay-rb-6"
        _make_job_and_payment(
            payment_session,
            job_id,
            payment_id,
            payment_status="settlement_failed",
            meta={"release_attempts": 20, "release_blocked_at": "2026-09-05T00:00:00+00:00"},
        )

        with patch("coordinator_api.contexts.infrastructure.routers.admin.PaymentService") as svc:
            svc.return_value.release_payment = AsyncMock(return_value=True)
            result = asyncio.run(retry_release(MagicMock(), job_id, payment_session, {"sub": "admin1"}))

        assert result["job_id"] == job_id
        assert result["cleared_attempts"] == 20
        svc.return_value.release_payment.assert_awaited_once()
        job = payment_session.get(Job, job_id)
        payment = payment_session.get(JobPayment, payment_id)
        # The route re-arms the held state; the (real) release call owns the flip
        # to released. The mocked service returns True without writing rows.
        assert payment.status == "escrowed"
        assert job.payment_status == "escrowed"
        assert "release_attempts" not in payment.meta_data
        assert payment.meta_data.get("release_blocked_at") is None

    def test_retry_rejects_non_terminal_payment(self, payment_session):
        """The route only applies to settlement_failed payments."""
        from fastapi import HTTPException

        from coordinator_api.contexts.infrastructure.routers.admin import retry_release

        job_id, payment_id = "job-rb-7", "pay-rb-7"
        _make_job_and_payment(payment_session, job_id, payment_id)

        with pytest.raises(HTTPException) as exc:
            asyncio.run(retry_release(MagicMock(), job_id, payment_session, {"sub": "admin1"}))
        assert exc.value.status_code == 409
