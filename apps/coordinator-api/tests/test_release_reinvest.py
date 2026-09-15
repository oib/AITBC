"""
GAP-43: the reinvest outcome of an escrow release must land where readers look.

``release_payment`` is called from every settlement path -- the miner-result
router, the acceptance sweeper, the client-accept route, the admin retry, the
reconciler. The reinvest bookkeeping used to live in the router's
``_attach_reinvest_info``, so a release that did not pass through it (the
sweeper, typically) left ``job.receipt`` -- and therefore the JobView the CLI
prints -- with null reinvest fields even though the chain had staked the share.

The bookkeeping now lives in ``release_payment`` itself: the payment's
``meta_data`` is the settlement record on every path, and the denormalised
``job.receipt`` is patched alongside it. The JobView additionally prefers
``meta_data`` so a view built before the receipt patch commits still shows the
outcome.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from sqlmodel import Session

from aitbc_shared import JobPayment, PaymentEscrow

from coordinator_api.contexts.infrastructure.domain.job import Job
from coordinator_api.contexts.infrastructure.services.jobs import JobService
from coordinator_api.contexts.payments.services.payments import PaymentService

PROVIDER = "0x02B8F2C61DB19B04aB68cfb43d0605E63dE74c5B"


@pytest.fixture
def payment_session(db_engine) -> Session:
    with Session(db_engine) as session:
        yield session


def _make_completed_job_and_payment(
    session: Session,
    job_id: str,
    payment_id: str,
    *,
    meta: dict | None = None,
    receipt: dict | None = None,
    constraints: dict | None = None,
) -> None:
    job = Job(
        id=job_id,
        client_id="client-1",
        state="COMPLETED",
        payload={},
        payment_id=payment_id,
        payment_status="escrowed",
        receipt=receipt,
        constraints=constraints,
    )
    payment = JobPayment(
        id=payment_id,
        job_id=job_id,
        client_id="client-1",
        amount=5,
        currency="AITBC",
        status="escrowed",
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
    session.add_all((job, payment, escrow))
    session.commit()


# A receipt that clears the attestation gate in `release_payment`.
ATTESTED_RECEIPT = {"computation_correct": True, "zk_status": "not_required"}


@patch("coordinator_api.contexts.payments.services.payments.AsyncAITBCHTTPClient")
def test_release_sends_the_percentage_and_records_the_outcome(mock_client_cls, payment_session):
    """The happy path: pct from payment meta reaches the chain; stake id comes back."""
    job_id, payment_id = "job-rv-1", "pay-rv-1"
    _make_completed_job_and_payment(
        payment_session,
        job_id,
        payment_id,
        meta={"provider_address": PROVIDER, "auto_reinvest_pct": 50},
        receipt=dict(ATTESTED_RECEIPT),
    )
    mock_client = AsyncMock()
    mock_client.post.return_value = {
        "success": True,
        "tx_hash": "0xrel",
        "reinvest_stake_id": "9",
        "reinvest_amount": "2.5",
    }
    mock_client_cls.return_value = mock_client

    service = PaymentService(payment_session)
    assert asyncio.run(service.release_payment("client-1", job_id, payment_id, "test")) is True

    sent = mock_client.post.call_args.kwargs["json"]
    assert sent["auto_reinvest_pct"] == "50"
    assert sent["provider_address"] == PROVIDER

    payment = payment_session.get(JobPayment, payment_id)
    assert payment.meta_data["reinvest_status"] == "staked"
    assert payment.meta_data["reinvest_stake_id"] == "9"
    assert payment.meta_data["reinvest_amount"] == "2.5"

    # The receipt mirror is the GAP-43 fix: readers of job.receipt no longer
    # depend on which route happened to run the release.
    job = payment_session.get(Job, job_id)
    assert job.receipt["reinvest_status"] == "staked"
    assert job.receipt["reinvest_stake_id"] == "9"
    assert job.receipt["reinvest_amount"] == "2.5"
    # The attestation fields that were already there survive the patch.
    assert job.receipt["computation_correct"] is True


@patch("coordinator_api.contexts.payments.services.payments.AsyncAITBCHTTPClient")
def test_release_falls_back_to_job_constraints_for_the_pct(mock_client_cls, payment_session):
    """Payments created before the meta carried the pct still honour it."""
    job_id, payment_id = "job-rv-2", "pay-rv-2"
    _make_completed_job_and_payment(
        payment_session,
        job_id,
        payment_id,
        meta={"provider_address": PROVIDER},
        receipt=dict(ATTESTED_RECEIPT),
        constraints={"auto_reinvest_pct": 25},
    )
    mock_client = AsyncMock()
    mock_client.post.return_value = {"success": True, "tx_hash": "0xrel"}
    mock_client_cls.return_value = mock_client

    service = PaymentService(payment_session)
    assert asyncio.run(service.release_payment("client-1", job_id, payment_id, "test")) is True
    assert mock_client.post.call_args.kwargs["json"]["auto_reinvest_pct"] == "25"


@patch("coordinator_api.contexts.payments.services.payments.AsyncAITBCHTTPClient")
def test_view_surfaces_reinvest_from_payment_meta(mock_client_cls, payment_session):
    """The JobView reads meta first, so a receipt that lagged still shows the stake."""
    job_id, payment_id = "job-rv-3", "pay-rv-3"
    _make_completed_job_and_payment(
        payment_session,
        job_id,
        payment_id,
        meta={"provider_address": PROVIDER, "auto_reinvest_pct": 50},
        receipt=dict(ATTESTED_RECEIPT),
        constraints={"auto_reinvest_pct": 50},
    )
    mock_client = AsyncMock()
    mock_client.post.return_value = {"success": True, "tx_hash": "0xrel", "reinvest_stake_id": "9"}
    mock_client_cls.return_value = mock_client

    assert asyncio.run(PaymentService(payment_session).release_payment("client-1", job_id, payment_id, "test")) is True

    # Now simulate the lag the bug produced: meta has the outcome, the receipt
    # copy does not. The view must still report it.
    job = payment_session.get(Job, job_id)
    job.receipt = dict(ATTESTED_RECEIPT)
    payment_session.add(job)
    payment_session.commit()

    view = JobService(payment_session).to_view(job)
    assert view.reinvest_status == "staked"
    assert view.reinvest_stake_id == "9"
    assert str(view.auto_reinvest_pct) == "50"
