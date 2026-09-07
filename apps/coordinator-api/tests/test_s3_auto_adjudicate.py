"""
S-3: Auto-adjudication of disputes with spot-check mismatch evidence.

When a dispute has spot-check evidence showing a mismatch, the auto-adjudicator
refunds the customer and slashes the provider's bond. Disputes without evidence
or with matching output are left for manual resolution.
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


def _make_disputed_job_with_evidence(
    session: Session,
    job_id: str,
    payment_id: str,
    spot_match: bool | None,
):
    """Create a disputed job + payment with spot-check evidence on constraints."""
    now = datetime.now(UTC)
    constraints = {"bond_required": True}
    if spot_match is not None:
        constraints["spot_check_result"] = {
            "match": spot_match,
            "original_output_hash": "abc123" if not spot_match else "same",
            "spot_output_hash": "def456" if not spot_match else "same",
            "spot_check_job_id": "shadow-1",
            "completed_at": now.isoformat(),
        }
    job = Job(
        id=job_id,
        client_id="client-s3",
        state="COMPLETED",
        payload={},
        payment_id=payment_id,
        payment_status="disputed",
        constraints=constraints,
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


@pytest.mark.asyncio
async def test_auto_adjudicate_mismatch_refunds_and_slashes(adjudicate_session):
    """A dispute with spot-check mismatch is auto-refunded and bond slashed."""
    job, payment = _make_disputed_job_with_evidence(adjudicate_session, "job-s3-mismatch", "pay-s3-mismatch", spot_match=False)

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

        # Call the function directly
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
    job, payment = _make_disputed_job_with_evidence(adjudicate_session, "job-s3-match", "pay-s3-match", spot_match=True)

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
    job, payment = _make_disputed_job_with_evidence(adjudicate_session, "job-s3-noev", "pay-s3-noev", spot_match=None)

    from coordinator_api.contexts.infrastructure.routers.admin import auto_adjudicate_disputes

    result = await auto_adjudicate_disputes(
        request=None,
        session=adjudicate_session,
        user={"sub": "admin-test"},
    )

    assert result["total_adjudicated"] == 0
    assert result["total_skipped"] == 1
    assert "no spot-check evidence" in result["skipped"][0]["reason"]
