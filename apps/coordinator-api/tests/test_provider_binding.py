"""Tests for binding the escrow payee to the miner that does the work (G2).

The chain pays whatever address the escrow named at creation, and it is created
before any miner is chosen. These pin the two halves of the fix: dispatch refuses a
miner that is not the payee, and the payment path refuses an escrow that would pay
the buyer their own money back.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from aitbc_shared import JobPayment

from coordinator_api.contexts.infrastructure.domain import Job, Miner
from coordinator_api.contexts.infrastructure.services.jobs import JobService
from coordinator_api.contexts.infrastructure.services.miners import MinerService
from coordinator_api.contexts.payments.provider_binding import miner_wallet_address, same_address
from coordinator_api.schemas import JobCreate, MinerRegister

PROVIDER = "0x1111111111111111111111111111111111111111"
OUTSIDER = "0x2222222222222222222222222222222222222222"


@pytest.fixture
def job_service(db_session):
    return JobService(db_session)


def _miner(db_session, miner_id: str, wallet: str | None) -> Miner:
    """Register a miner through the real service so storage matches production."""
    payload = MinerRegister(capabilities={}, concurrency=1, region=None, wallet_address=wallet)
    miner = MinerService(db_session).register(miner_id, payload)
    miner.status = "ONLINE"
    miner.inflight = 0
    db_session.add(miner)
    db_session.commit()
    db_session.refresh(miner)
    return miner


def _escrowed_job(job_service, db_session, *, provider_address: str | None) -> Job:
    """Create a job with a payment already in the escrowed state."""
    req = JobCreate(
        payload={"type": "inference", "prompt": "test prompt"},
        ttl_seconds=900,
        payment_amount=Decimal("5"),
        payment_currency="AITBC",
    )
    job = job_service.create_job(client_id="client1", req=req)
    meta = {"provider_address": provider_address} if provider_address else {}
    payment = JobPayment(
        job_id=job.id,
        amount=Decimal("5"),
        currency="AITBC",
        payment_method="aitbc_token",
        status="escrowed",
        meta_data=meta or None,
    )
    db_session.add(payment)
    db_session.commit()
    db_session.refresh(payment)
    job.payment_id = payment.id
    job.payment_status = "escrowed"
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    return job


def test_the_payee_gets_the_job(db_session, job_service):
    """The miner whose registered wallet is the escrow provider may run it."""
    job = _escrowed_job(job_service, db_session, provider_address=PROVIDER)
    miner = _miner(db_session, "miner_payee", PROVIDER)

    acquired = job_service.acquire_next_job(miner)
    assert acquired is not None
    assert acquired.id == job.id
    assert acquired.assigned_miner_id == miner.id


def test_a_different_miner_is_refused(db_session, job_service):
    """A miner that is not the payee cannot earn someone else's escrow."""
    job = _escrowed_job(job_service, db_session, provider_address=PROVIDER)
    miner = _miner(db_session, "miner_outsider", OUTSIDER)

    assert job_service.acquire_next_job(miner) is None

    refreshed = db_session.get(Job, job.id)
    assert refreshed is not None
    assert refreshed.state == "QUEUED"
    assert refreshed.assigned_miner_id is None


def test_a_miner_without_a_wallet_is_refused(db_session, job_service):
    """No declared payout address means no escrowed work -- it fails closed."""
    _escrowed_job(job_service, db_session, provider_address=PROVIDER)
    miner = _miner(db_session, "miner_anonymous", None)

    assert job_service.acquire_next_job(miner) is None


def test_an_escrow_without_a_provider_is_refused(db_session, job_service):
    """An escrow that recorded no payee blocks rather than paying anyone."""
    _escrowed_job(job_service, db_session, provider_address=None)
    miner = _miner(db_session, "miner_payee2", PROVIDER)

    assert job_service.acquire_next_job(miner) is None


def test_lowercase_0x_spelling_still_matches(db_session, job_service):
    """Lowercase and checksummed 0x are the same address, and the chain treats them so."""
    job = _escrowed_job(job_service, db_session, provider_address=PROVIDER.lower())
    miner = _miner(db_session, "miner_lower", PROVIDER)

    acquired = job_service.acquire_next_job(miner)
    assert acquired is not None
    assert acquired.id == job.id


def test_unpriced_work_is_unaffected(db_session, job_service):
    """A job with no escrow has no payee to protect, so any miner may take it."""
    req = JobCreate(payload={"type": "inference", "prompt": "free"}, ttl_seconds=900)
    job = job_service.create_job(client_id="client1", req=req)
    miner = _miner(db_session, "miner_anonymous2", None)

    acquired = job_service.acquire_next_job(miner)
    assert acquired is not None
    assert acquired.id == job.id


def test_binding_can_be_disabled_for_operators(db_session, job_service, monkeypatch):
    """COORDINATOR_REQUIRE_PROVIDER_BINDING=false restores the previous behaviour."""
    from coordinator_api.contexts.infrastructure.services import jobs as jobs_module

    monkeypatch.setattr(jobs_module, "_PROVIDER_BINDING_REQUIRE", False)
    job = _escrowed_job(job_service, db_session, provider_address=PROVIDER)
    miner = _miner(db_session, "miner_outsider2", OUTSIDER)

    acquired = job_service.acquire_next_job(miner)
    assert acquired is not None
    assert acquired.id == job.id


def test_the_wallet_survives_a_heartbeat(db_session):
    """heartbeat() replaces extra_metadata wholesale, so the wallet lives elsewhere."""
    from coordinator_api.schemas import MinerHeartbeat

    miner = _miner(db_session, "miner_beating", PROVIDER)
    service = MinerService(db_session)
    service.heartbeat("miner_beating", MinerHeartbeat(inflight=0, status="ONLINE", metadata={"gpu": "busy"}))
    db_session.refresh(miner)

    assert miner_wallet_address(miner) == PROVIDER


def test_same_address_never_matches_a_missing_address():
    """Two unknowns are not a match; that would defeat the whole check."""
    assert not same_address(None, None)
    assert not same_address("", PROVIDER)
    assert same_address(PROVIDER, PROVIDER.lower())
