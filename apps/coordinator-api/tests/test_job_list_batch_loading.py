"""D4: job list endpoints batch-load JobPayment instead of querying per job.

`JobService.to_view` did one `session.get(JobPayment, ...)` per job, so
`GET /v1/jobs`, `GET /v1/jobs/history`, and `POST /v1/miners/{id}/jobs` were N+1 --
list size queries, not three. `to_views()` loads every `JobPayment` the batch needs
in a single `IN` query. These pin both halves: the batch method must return exactly
what calling `to_view()` job-by-job would have returned, and it must actually do it
in one query instead of one-per-job.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from aitbc_shared import JobPayment

from coordinator_api.contexts.infrastructure.domain import Job
from coordinator_api.contexts.infrastructure.services.jobs import JobService
from coordinator_api.schemas import JobCreate

PROVIDER = "0x1111111111111111111111111111111111111111"


@pytest.fixture
def job_service(db_session):
    return JobService(db_session)


def _job(job_service, *, prompt: str) -> Job:
    req = JobCreate(payload={"type": "inference", "prompt": prompt}, ttl_seconds=900)
    return job_service.create_job(client_id="client1", req=req)


def _attach_payment(db_session, job: Job, *, offer_id: str | None, unit_price: str | None) -> JobPayment:
    meta: dict = {}
    if offer_id:
        meta["offer_id"] = offer_id
    if unit_price:
        meta["offer_unit_price"] = unit_price
        meta["offer_price_unit"] = "per_1k_tokens"
    payment = JobPayment(
        job_id=job.id,
        amount=Decimal("1"),
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
    return payment


def test_to_views_matches_to_view_for_each_job(db_session, job_service):
    """The batch path must return the same view as the per-job path, field for field."""
    priced = _job(job_service, prompt="priced")
    _attach_payment(db_session, priced, offer_id="ollama-llama3.2-3b", unit_price="0.001")
    unpaid = _job(job_service, prompt="unpaid")

    expected = [job_service.to_view(priced), job_service.to_view(unpaid)]
    batched = job_service.to_views([priced, unpaid])

    assert [v.model_dump() for v in batched] == [v.model_dump() for v in expected]


def test_to_views_maps_each_job_to_its_own_payment(db_session, job_service):
    """Two jobs with two different payments must not cross-wire in the batch lookup."""
    job_a = _job(job_service, prompt="a")
    _attach_payment(db_session, job_a, offer_id="offer-a", unit_price="1")
    job_b = _job(job_service, prompt="b")
    _attach_payment(db_session, job_b, offer_id="offer-b", unit_price="2")

    views = {v.job_id: v for v in job_service.to_views([job_a, job_b])}

    assert views[job_a.id].offer_id == "offer-a"
    assert views[job_b.id].offer_id == "offer-b"


def test_to_views_handles_a_job_with_no_payment(db_session, job_service):
    """An unpriced job has no payment_id at all -- must not be looked up or crash."""
    job = _job(job_service, prompt="free")

    views = job_service.to_views([job])

    assert len(views) == 1
    assert views[0].payment_id is None
    assert views[0].offer_id is None


def test_to_views_handles_an_empty_list(db_session, job_service):
    """Zero jobs must not issue a query at all, let alone crash on an empty IN ()."""
    assert job_service.to_views([]) == []


def test_to_views_does_not_query_jobpayment_once_per_job(db_session, job_service, monkeypatch):
    """The actual N+1 regression guard: to_view() used session.get(JobPayment, ...)
    once per job; to_views() must not call session.get for JobPayment at all --
    only the single batched `select(JobPayment).where(...in_(...))` executed
    inside to_views() itself.
    """
    jobs = [_job(job_service, prompt=f"job-{i}") for i in range(3)]
    for job in jobs:
        _attach_payment(db_session, job, offer_id="offer", unit_price="1")

    real_get = db_session.get
    get_calls: list[type] = []

    def counting_get(model, *args, **kwargs):
        get_calls.append(model)
        return real_get(model, *args, **kwargs)

    monkeypatch.setattr(db_session, "get", counting_get)

    views = job_service.to_views(jobs)

    assert len(views) == 3
    assert JobPayment not in get_calls, (
        f"to_views() called session.get(JobPayment, ...) {get_calls.count(JobPayment)} time(s) "
        "-- the N+1 query pattern D4 fixed has regressed"
    )
