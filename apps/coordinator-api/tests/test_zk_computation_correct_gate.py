"""Tests for the computation_correct acceptance/release gate (G3/T4).

A high-value/ZK job whose receipt has ``computation_correct`` set to ``False``
(or missing) must not be accepted by the customer and must not be released by
the sweeper.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from aitbc_shared import JobPayment
from coordinator_api.contexts.infrastructure.domain.job import Job
from coordinator_api.contexts.infrastructure.routers.client import accept_job
from coordinator_api.contexts.payments.acceptance import PENDING_ACCEPTANCE
from coordinator_api.contexts.payments.services.payments import PaymentService


@pytest.fixture
def payment_service(db_session):
    """Return a PaymentService bound to the in-memory test session."""
    return PaymentService(db_session)


def _make_zk_job(db_session, receipt, payment_status=PENDING_ACCEPTANCE, amount=Decimal("15")):
    """Create a job whose constraints require a ZK proof, with a payment in the held state."""
    job = Job(
        client_id="client1",
        payload={"type": "inference", "prompt": "test"},
        constraints={"zk_proof_required": True},
        payment_amount=amount,
        payment_status=payment_status,
        state="COMPLETED",
        completed_at=datetime.now(UTC),
        receipt=receipt,
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    payment = JobPayment(
        job_id=job.id,
        amount=amount,
        currency="AITBC",
        status="escrowed",
        meta_data={"provider_address": "0x1234567890123456789012345678901234567890"},
    )
    db_session.add(payment)
    db_session.commit()
    db_session.refresh(payment)

    job.payment_id = payment.id
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    return job, payment


@pytest.mark.asyncio
async def test_release_payment_blocked_when_computation_correct_false(db_session, payment_service):
    """Escrow release must fail when the ZK receipt is verified but computation_correct is False."""
    receipt = {"zk_status": "verified", "computation_correct": False, "provider": "0x1234567890123456789012345678901234567890"}
    job, payment = _make_zk_job(db_session, receipt)

    with patch(
        "coordinator_api.contexts.payments.services.payments.AITBCHTTPClient",
        return_value=MagicMock(post=MagicMock(return_value={"success": True})),
    ):
        released = await payment_service.release_payment("client1", job.id, payment.id)

    assert released is False
    db_session.refresh(payment)
    assert payment.status == "escrowed"


@pytest.mark.asyncio
async def test_release_payment_blocked_when_computation_correct_missing(db_session, payment_service):
    """Escrow release must fail for a legacy receipt that has no computation_correct key."""
    # Legacy receipt: only zk_status was stored.
    receipt = {"zk_status": "verified", "provider": "0x1234567890123456789012345678901234567890"}
    job, payment = _make_zk_job(db_session, receipt)

    with patch(
        "coordinator_api.contexts.payments.services.payments.AITBCHTTPClient",
        return_value=MagicMock(post=MagicMock(return_value={"success": True})),
    ):
        released = await payment_service.release_payment("client1", job.id, payment.id)

    assert released is False
    db_session.refresh(payment)
    assert payment.status == "escrowed"


@pytest.mark.asyncio
async def test_release_payment_allowed_when_computation_correct_true(db_session, payment_service):
    """Escrow release succeeds when the ZK receipt is verified and computation_correct is True."""
    receipt = {
        "zk_status": "verified",
        "computation_correct": True,
        "provider": "0x1234567890123456789012345678901234567890",
        "zk_proof": {"circuit": "receipt_public"},
    }
    job, payment = _make_zk_job(db_session, receipt)

    with patch(
        "coordinator_api.contexts.payments.services.payments.AITBCHTTPClient",
        return_value=MagicMock(
            post=MagicMock(
                return_value={
                    "success": True,
                    "tx_hash": "0x1234",
                    "released_at": datetime.now(UTC).isoformat(),
                }
            )
        ),
    ):
        released = await payment_service.release_payment("client1", job.id, payment.id)

    assert released is True
    db_session.refresh(payment)
    assert payment.status == "released"


@pytest.mark.asyncio
async def test_accept_job_blocked_when_computation_correct_false(db_session):
    """Customer acceptance must be rejected when computation_correct is False."""
    receipt = {"zk_status": "verified", "computation_correct": False, "provider": "0x1234567890123456789012345678901234567890"}
    job, _payment = _make_zk_job(db_session, receipt)

    with pytest.raises(HTTPException) as exc:
        await accept_job(MagicMock(), job.id, db_session, {"sub": "client1"})
    assert exc.value.status_code == 422
    assert "computation-correctness" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_accept_job_allowed_when_computation_correct_true(db_session):
    """Customer acceptance succeeds when computation_correct is True and the chain releases."""
    receipt = {
        "zk_status": "verified",
        "computation_correct": True,
        "provider": "0x1234567890123456789012345678901234567890",
        "zk_proof": {"circuit": "receipt_public"},
    }
    job, _payment = _make_zk_job(db_session, receipt)

    with patch(
        "coordinator_api.contexts.payments.services.payments.AITBCHTTPClient",
        return_value=MagicMock(
            post=MagicMock(
                return_value={
                    "success": True,
                    "tx_hash": "0x1234",
                    "released_at": datetime.now(UTC).isoformat(),
                }
            )
        ),
    ):
        result = await accept_job(MagicMock(), job.id, db_session, {"sub": "client1"})

    assert result.payment_status == "released"
