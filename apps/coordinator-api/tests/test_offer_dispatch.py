"""D3: a job bought against an offer is dispatched to the offer's provider.

G1 binds the offer to the price and payee at submission. This pins the other half:
dispatch must consult the quoted offer, not just the miner's general capabilities,
so a job quoted against one provider's offer cannot be executed by another.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from aitbc_shared import JobPayment

from coordinator_api.contexts.infrastructure.domain import Job, Miner
from coordinator_api.contexts.infrastructure.services.jobs import JobService
from coordinator_api.contexts.infrastructure.services.miners import MinerService
from coordinator_api.schemas import JobCreate, MinerRegister

PROVIDER = "0x1111111111111111111111111111111111111111"
OUTSIDER = "0x2222222222222222222222222222222222222222"
OFFER_ID = "ollama-llama3.2-3b"


@pytest.fixture
def job_service(db_session):
    return JobService(db_session)


def _miner(db_session, miner_id: str, wallet: str | None, capabilities: dict | None = None) -> Miner:
    payload = MinerRegister(
        capabilities=capabilities or {},
        concurrency=1,
        region=None,
        wallet_address=wallet,
    )
    miner = MinerService(db_session).register(miner_id, payload)
    miner.status = "ONLINE"
    miner.inflight = 0
    db_session.add(miner)
    db_session.commit()
    db_session.refresh(miner)
    return miner


def _offered_job(job_service, db_session, *, provider_address: str, escrowed: bool = True) -> Job:
    """Create a job submitted with an offer_id and a quoted provider."""
    req = JobCreate(
        payload={"type": "inference", "prompt": "test prompt"},
        ttl_seconds=900,
        payment_amount=Decimal("0.001"),
        payment_currency="AITBC",
        offer_id=OFFER_ID,
        provider_address=provider_address,
    )
    job = job_service.create_job(client_id="client1", req=req)
    if escrowed:
        payment = JobPayment(
            job_id=job.id,
            amount=Decimal("0.001"),
            currency="AITBC",
            payment_method="aitbc_token",
            status="escrowed",
            meta_data={
                "provider_address": provider_address,
                "offer_id": OFFER_ID,
            },
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


def test_satisfies_constraints_stores_offer_on_job(job_service, db_session):
    """create_job copies the quoted offer_id and provider_address onto the job."""
    job = _offered_job(job_service, db_session, provider_address=PROVIDER)
    assert job.offer_id == OFFER_ID
    assert job.provider_address == PROVIDER


def test_offer_provider_gets_the_job(db_session, job_service):
    """The miner whose wallet matches the offer's provider may run it."""
    job = _offered_job(job_service, db_session, provider_address=PROVIDER)
    miner = _miner(db_session, "miner_provider", PROVIDER, capabilities={"gpus": [{"name": "RTX4090"}]})

    acquired = job_service.acquire_next_job(miner)
    assert acquired is not None
    assert acquired.id == job.id


def test_other_miner_with_matching_capabilities_is_refused(db_session, job_service):
    """A different miner, even with the right capabilities, cannot take an offer job."""
    job = _offered_job(job_service, db_session, provider_address=PROVIDER)
    miner = _miner(
        db_session,
        "miner_outsider",
        OUTSIDER,
        capabilities={"gpus": [{"name": "RTX4090", "memory_mb": 24576}]},
    )

    # The outsider's capabilities would otherwise satisfy an unconstrained job.
    assert job_service._satisfies_constraints(job, miner) is False
    assert job_service.acquire_next_job(miner) is None

    refreshed = db_session.get(Job, job.id)
    assert refreshed is not None
    assert refreshed.state == "QUEUED"


def test_offer_job_without_provider_fails_closed(db_session, job_service):
    """A malformed offer job (offer_id set but no provider) does not dispatch."""
    req = JobCreate(
        payload={"type": "inference", "prompt": "test prompt"},
        ttl_seconds=900,
        payment_amount=Decimal("0.001"),
        payment_currency="AITBC",
        offer_id=OFFER_ID,
    )
    job = job_service.create_job(client_id="client1", req=req)
    payment = JobPayment(
        job_id=job.id,
        amount=Decimal("0.001"),
        currency="AITBC",
        payment_method="aitbc_token",
        status="escrowed",
        meta_data={"offer_id": OFFER_ID},
    )
    db_session.add(payment)
    db_session.commit()
    db_session.refresh(payment)
    job.payment_id = payment.id
    job.payment_status = "escrowed"
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    miner = _miner(db_session, "miner_any", PROVIDER)
    assert job_service._satisfies_constraints(job, miner) is False


def test_unpriced_offer_job_still_bound_to_provider(db_session, job_service):
    """Even without an escrow, an offer job's provider binding is consulted."""
    req = JobCreate(
        payload={"type": "inference", "prompt": "free"},
        ttl_seconds=900,
        offer_id=OFFER_ID,
        provider_address=PROVIDER,
    )
    job = job_service.create_job(client_id="client1", req=req)
    outsider = _miner(db_session, "miner_outsider_free", OUTSIDER)
    assert job_service._satisfies_constraints(job, outsider) is False
