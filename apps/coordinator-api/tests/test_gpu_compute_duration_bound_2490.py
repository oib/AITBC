"""#2490: buyer-controlled gpu_compute durations are bounded end to end.

Before the fix a funded ``gpu_compute`` job could carry an arbitrary
``payload.duration_seconds``/``duration_hours``: values ≥ ~2.5e11 made
``_gpu_compute_claim_expiry`` raise ``OverflowError`` inside
``acquire_next_job`` — aborting the whole dispatch poll so every job queued
behind the poison row stalled — while a representable absurd value
(``10**9`` s ≈ 31 years) pushed ``expires_at`` ~11574 days out, an
"immortal" RUNNING rental the stale-job reaper never expired.

Now: submit refuses non-finite or above-cap durations with 422, the shared
``_payload_duration_seconds`` clamps stored legacy rows to
``COORDINATOR_GPU_JOB_MAX_DURATION_SECONDS`` (default 3600, matching the
miner's ``GPU_COMPUTE_MAX_SECONDS``), and ``ArithmeticError`` joins the
per-job ``_OPS_ERRORS`` surface so one bad row skips instead of 500ing
every miner poll.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi import HTTPException

from coordinator_api.contexts.infrastructure.domain import Job, Miner
from coordinator_api.contexts.infrastructure.routers import client as client_router
from coordinator_api.contexts.infrastructure.services import jobs as jobs_mod
from coordinator_api.contexts.infrastructure.services.jobs import (
    _GPU_COMPUTE_CLAIM_SLACK_SECONDS,
    _GPU_COMPUTE_MAX_DURATION_SECONDS,
    _GPU_COMPUTE_RENTAL_SLACK_SECONDS,
    _gpu_compute_rental_deadline,
    _payload_duration_seconds,
    JobService,
)
from coordinator_api.schemas import JobCreate


def _miner(miner_id: str) -> Miner:
    return Miner(
        id=miner_id,
        concurrency=4,
        inflight=0,
        status="ONLINE",
        extra_metadata={},
        capabilities={},
    )


@pytest.fixture
def job_service(db_session):
    return JobService(db_session)


def _aware(dt):
    return dt if dt is None or dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _priced_req(**payload_extra):
    payload = {"type": "gpu_compute", "task": "general_compute", "duration_hours": 1.0}
    payload.update(payload_extra)
    return JobCreate(payload=payload, payment_amount=Decimal("1"))


# --------------------------------------------------------------------------
# Submit-side validation (422 before the job exists)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload_extra",
    [
        {"duration_seconds": 1e12},
        {"duration_seconds": 10**30},
        {"duration_seconds": float("inf")},
        {"duration_seconds": float("nan")},
        {"duration_hours": 1e10},  # ~317 years in hours
        {"duration_seconds": "1e30"},
    ],
)
def test_submit_rejects_out_of_bounds_duration(payload_extra: dict) -> None:
    with pytest.raises(HTTPException) as exc:
        client_router._require_priced_gpu_compute(_priced_req(**payload_extra))
    assert exc.value.status_code == 422
    assert "duration" in exc.value.detail


@pytest.mark.parametrize(
    "payload_extra",
    [
        {},
        {"duration_seconds": _GPU_COMPUTE_MAX_DURATION_SECONDS},
        {"duration_hours": _GPU_COMPUTE_MAX_DURATION_SECONDS / 3600},
        {"duration_seconds": 0},
        {"duration_seconds": -5},
        {"duration_seconds": "abc"},  # unparseable reads as absent, as before
    ],
)
def test_submit_allows_in_bounds_or_inert_duration(payload_extra: dict) -> None:
    client_router._require_priced_gpu_compute(_priced_req(**payload_extra))


def test_unpriced_gpu_compute_still_reports_price_not_duration() -> None:
    req = JobCreate(payload={"type": "gpu_compute", "duration_seconds": 1e30})
    with pytest.raises(HTTPException) as exc:
        client_router._require_priced_gpu_compute(req)
    assert "payment_amount" in exc.value.detail


# --------------------------------------------------------------------------
# Shared duration math: clamp + non-finite safety for stored rows
# --------------------------------------------------------------------------


@pytest.mark.parametrize("raw", [1e12, 1e30, 10**40, float("inf"), float("-inf"), float("nan"), "abc", None])
@pytest.mark.parametrize("key", ["duration_seconds", "duration_hours"])
def test_payload_duration_seconds_is_bounded(raw, key: str) -> None:
    value = _payload_duration_seconds({"type": "gpu_compute", key: raw})
    assert math.isfinite(value)
    assert value <= _GPU_COMPUTE_MAX_DURATION_SECONDS or value <= 0


def test_payload_duration_seconds_clamps_to_cap() -> None:
    assert _payload_duration_seconds({"duration_seconds": 1e12}) == _GPU_COMPUTE_MAX_DURATION_SECONDS
    # duration_hours path: 10 hours > 3600 s cap
    assert _payload_duration_seconds({"duration_hours": 10}) == _GPU_COMPUTE_MAX_DURATION_SECONDS
    # normal value untouched
    assert _payload_duration_seconds({"duration_seconds": 600}) == 600.0


# --------------------------------------------------------------------------
# Dispatch: the auditor's poison-pill and immortal-rental repros, flipped
# --------------------------------------------------------------------------


def _queued_gpu_job(job_service, **payload_extra):
    payload = {"type": "gpu_compute", "task": "general_compute", "duration_hours": 1.0}
    payload.update(payload_extra)
    return job_service.create_job(
        client_id="client1",
        req=JobCreate(payload=payload, ttl_seconds=900),
    )


def test_oversized_stored_row_claims_with_capped_expiry(db_session, job_service):
    """A pre-fix row holding duration_seconds=10**9 no longer yields a
    ~11574-day expires_at — the claim extension is capped like everything
    else, and no OverflowError escapes."""
    miner = _miner("miner-cap-1")
    db_session.add(miner)
    db_session.commit()

    job = _queued_gpu_job(job_service, duration_seconds=10**9)
    before = datetime.now(UTC)

    claimed = job_service.acquire_next_job(miner)
    assert claimed is not None and claimed.id == job.id

    new_expiry = _aware(db_session.get(Job, job.id).expires_at)
    # capped duration + claim slack, measured from ~claim time — nowhere
    # near the 11574 days the raw value produced, and well under any
    # plausible TTL backstop.
    assert new_expiry <= before + timedelta(seconds=_GPU_COMPUTE_MAX_DURATION_SECONDS + _GPU_COMPUTE_CLAIM_SLACK_SECONDS + 60)
    assert new_expiry >= before + timedelta(seconds=_GPU_COMPUTE_MAX_DURATION_SECONDS + _GPU_COMPUTE_CLAIM_SLACK_SECONDS - 60)


def test_queued_job_behind_an_oversized_row_still_dispatches(db_session, job_service):
    """Auditor repro: the poison row used to abort every acquire_next_job
    poll, so the legitimate job queued behind it never dispatched."""
    miner = _miner("miner-cap-2")
    db_session.add(miner)
    db_session.commit()

    poison = _queued_gpu_job(job_service, duration_seconds=10**40)
    legit = _queued_gpu_job(job_service, duration_hours=0.5)

    first = job_service.acquire_next_job(miner)
    assert first is not None  # poison row claims with a capped expiry — no 500
    second_miner = _miner("miner-cap-3")
    db_session.add(second_miner)
    db_session.commit()
    second = job_service.acquire_next_job(second_miner)
    assert second is not None and second.id == legit.id
    assert _aware(db_session.get(Job, poison.id).expires_at) <= datetime.now(UTC) + timedelta(
        seconds=_GPU_COMPUTE_MAX_DURATION_SECONDS + _GPU_COMPUTE_CLAIM_SLACK_SECONDS + 60
    )


def test_overflow_error_in_claim_skips_row_instead_of_aborting_poll(db_session, job_service, monkeypatch):
    """Defence in depth: even if a row still raises ArithmeticError inside
    the claim math, _try_claim_queued_job skips it and the next candidate
    dispatches — the poll never 500s."""
    miner = _miner("miner-cap-4")
    db_session.add(miner)
    db_session.commit()

    bad = _queued_gpu_job(job_service, duration_seconds=10**40)
    legit = _queued_gpu_job(job_service, duration_hours=0.5)

    real_claim_expiry = jobs_mod._gpu_compute_claim_expiry

    def boom(job):
        if job.id == bad.id:
            raise OverflowError("date value out of range")
        return real_claim_expiry(job)

    monkeypatch.setattr(jobs_mod, "_gpu_compute_claim_expiry", boom)

    claimed = job_service.acquire_next_job(miner)
    assert claimed is not None and claimed.id == legit.id
    assert db_session.get(Job, bad.id).state == "QUEUED"


def test_rental_deadline_uses_capped_duration() -> None:
    """The RUNNING-side rental deadline shares the clamp, so the reaper's
    window cannot stretch decades either."""
    started = datetime.now(UTC) - timedelta(seconds=100)
    job = Job(
        id="j-rental",
        client_id="c1",
        state="RUNNING",
        payload={"type": "gpu_compute", "duration_seconds": 10**9},
        started_at=started,
    )
    deadline = _gpu_compute_rental_deadline(job)
    assert deadline is not None
    expected = started + timedelta(seconds=_GPU_COMPUTE_MAX_DURATION_SECONDS + _GPU_COMPUTE_RENTAL_SLACK_SECONDS)
    assert abs((deadline - expected).total_seconds()) < 1
