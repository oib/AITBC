"""
S-3: Auto-adjudication of disputes with spot-check mismatch evidence.

When a dispute has spot-check evidence showing a mismatch, the auto-adjudicator
refunds the customer and slashes the provider's bond. Disputes without evidence
or with matching output are left for manual resolution.

The spot-check evidence must come from the completed, server-created shadow job,
not from client-writable fields on the original job's constraints.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from sqlmodel import Session

from aitbc_shared import JobPayment

from coordinator_api.contexts.infrastructure.domain.job import Job


@pytest.fixture
def adjudicate_session(db_engine) -> Session:
    with Session(db_engine) as session:
        yield session


def _make_disputed_job(session: Session, job_id: str, payment_id: str) -> tuple[Job, JobPayment]:
    """Create a disputed job + payment, with bond_required set by the client."""
    now = datetime.now(UTC)
    job = Job(
        id=job_id,
        client_id="client-s3",
        state="COMPLETED",
        payload={},
        payment_id=payment_id,
        payment_status="disputed",
        constraints={"bond_required": True},
    )
    payment = JobPayment(
        id=payment_id,
        job_id=job_id,
        client_id="client-s3",
        amount=1,
        currency="AITBC",
        status="disputed",
        escrow_address="0xtest",
        meta_data={"dispute_reason": "wrong output", "disputed_at": now.isoformat()},
    )
    session.add(job)
    session.add(payment)
    session.commit()
    return job, payment


def _make_completed_shadow(session: Session, original: Job, spot_match: bool) -> Job:
    """Create the server-owned shadow job that carries the spot-check result."""
    now = datetime.now(UTC)
    shadow = Job(
        id="shadow-" + original.id,
        client_id=original.client_id,
        state="COMPLETED",
        payload=original.payload,
        constraints={
            "shadow_mode": True,
            "spot_check_for": original.id,
            "deterministic_decoding": True,
            "spot_check_result": {
                "spot_check_job_id": "shadow-" + original.id,
                "original_job_id": original.id,
                "match": spot_match,
                "original_output_hash": "abc123" if not spot_match else "same",
                "spot_output_hash": "def456" if not spot_match else "same",
                "completed_at": now.isoformat(),
            },
        },
        ttl_seconds=original.ttl_seconds,
        requested_at=now,
        expires_at=now,
    )
    session.add(shadow)
    session.commit()
    return shadow


@pytest.mark.asyncio
async def test_auto_adjudicate_mismatch_refunds_and_slashes(adjudicate_session):
    """A dispute with spot-check mismatch is auto-refunded and bond slashed."""
    job, payment = _make_disputed_job(adjudicate_session, "job-s3-mismatch", "pay-s3-mismatch")
    _make_completed_shadow(adjudicate_session, job, spot_match=False)

    with (
        patch(
            "coordinator_api.contexts.payments.services.payments.PaymentService.refund_payment",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch(
            "coordinator_api.contexts.marketplace.services.bond_slashing.BondSlashingService.slash",
            new_callable=AsyncMock,
        ),
    ):
        from coordinator_api.contexts.infrastructure.routers.admin import auto_adjudicate_disputes

        result = await auto_adjudicate_disputes(
            request=None,
            session=adjudicate_session,
            user={"sub": "admin-test"},
        )

    assert result["total_adjudicated"] == 1
    assert result["adjudicated"][0]["outcome"] == "refund"
    assert result["adjudicated"][0]["bond_slashed"] is True


@pytest.mark.asyncio
async def test_auto_adjudicate_match_skips(adjudicate_session):
    """A dispute with spot-check match is skipped (needs manual ruling)."""
    job, payment = _make_disputed_job(adjudicate_session, "job-s3-match", "pay-s3-match")
    _make_completed_shadow(adjudicate_session, job, spot_match=True)

    with patch(
        "coordinator_api.contexts.payments.services.payments.PaymentService.refund_payment",
        new_callable=AsyncMock,
        return_value=True,
    ):
        from coordinator_api.contexts.infrastructure.routers.admin import auto_adjudicate_disputes

        result = await auto_adjudicate_disputes(
            request=None,
            session=adjudicate_session,
            user={"sub": "admin-test"},
        )

    assert result["total_adjudicated"] == 0
    assert result["total_skipped"] == 1
    assert "matched" in result["skipped"][0]["reason"]


@pytest.mark.asyncio
async def test_auto_adjudicate_no_evidence_skips(adjudicate_session):
    """A dispute without spot-check evidence is skipped."""
    job, payment = _make_disputed_job(adjudicate_session, "job-s3-noev", "pay-s3-noev")

    from coordinator_api.contexts.infrastructure.routers.admin import auto_adjudicate_disputes

    result = await auto_adjudicate_disputes(
        request=None,
        session=adjudicate_session,
        user={"sub": "admin-test"},
    )

    assert result["total_adjudicated"] == 0
    assert result["total_skipped"] == 1
    assert "no spot-check evidence" in result["skipped"][0]["reason"]


@pytest.mark.asyncio
async def test_client_forged_spot_check_result_is_ignored(adjudicate_session):
    """A client-supplied spot_check_result on the original job must not trigger adjudication."""
    job, payment = _make_disputed_job(adjudicate_session, "job-s3-forged", "pay-s3-forged")
    # Client tries to smuggle a forged mismatch record into their own constraints.
    job.constraints = {
        "bond_required": True,
        "spot_check_result": {
            "match": False,
            "original_output_hash": "client-fake-original",
            "spot_output_hash": "client-fake-spot",
            "spot_check_job_id": "client-fake-shadow",
            "completed_at": datetime.now(UTC).isoformat(),
        },
    }
    adjudicate_session.add(job)
    adjudicate_session.commit()

    with patch(
        "coordinator_api.contexts.payments.services.payments.PaymentService.refund_payment",
        new_callable=AsyncMock,
        return_value=True,
    ) as mock_refund:
        from coordinator_api.contexts.infrastructure.routers.admin import auto_adjudicate_disputes

        result = await auto_adjudicate_disputes(
            request=None,
            session=adjudicate_session,
            user={"sub": "admin-test"},
        )

    assert result["total_adjudicated"] == 0
    assert result["total_skipped"] == 1
    assert "no spot-check evidence" in result["skipped"][0]["reason"]
    mock_refund.assert_not_called()
