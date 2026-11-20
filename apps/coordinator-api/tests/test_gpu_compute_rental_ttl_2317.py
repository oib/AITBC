"""#2317: a gpu_compute rental survives miner restart and finishes in-window.

Live job ``4e06c97d…``: rental 1 ran 18 min, the miner restarted, the
coordinator re-dispatched the same RUNNING job via
``GET /v1/miners/{id}/running-jobs``, the new process re-held the FULL
duration, and ``expires_at`` (set once at claim + the #2306 extension) expired
4 min before the second rental could finish — the reaper flipped EXPIRED,
the buyer was refunded and the provider went unpaid.

The fix anchors the rental window on ``job.started_at`` (stamped by the
QUEUED→RUNNING claim CAS):

- ``_gpu_compute_rental_deadline`` = ``started_at + payload duration + slack``
  is the deadline that bounds a RUNNING gpu_compute job — ``_ensure_not_expired``
  and both ``StaleJobReaper`` sweeps honour it instead of ``expires_at``.
- ``assigned_running_jobs`` re-extends ``expires_at`` to
  ``rental_deadline + slack`` while the window is open (idempotent, never
  past that bound) and returns ``gpu_compute`` rental fields so the miner can
  hold only the *remaining* purchased seconds.
- QUEUED expiry is unchanged: a stale rental still must not dispatch.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from aitbc.auth.dependencies import require_miner
from coordinator_api.contexts.infrastructure.domain import Job, Miner
from coordinator_api.contexts.infrastructure.services.jobs import (
    _GPU_COMPUTE_RENTAL_SLACK_SECONDS,
    JobService,
)
from coordinator_api.contexts.infrastructure.services.stale_job_reaper import StaleJobReaper
from coordinator_api.main import app
from coordinator_api.schemas import JobCreate
from coordinator_api.storage import get_session

GPU_PAYLOAD = {"type": "gpu_compute", "task": "general_compute", "duration_seconds": 3600}
MINER = "miner-2317"


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _running_gpu_job(
    session: Session,
    job_id: str,
    *,
    started_at: datetime | None,
    expires_at: datetime | None = None,
    state: str = "RUNNING",
    miner_id: str | None = MINER,
    payload: dict | None = None,
) -> Job:
    job = Job(
        id=job_id,
        client_id="client-1",
        state=state,
        payload=payload if payload is not None else dict(GPU_PAYLOAD),
        constraints={},
        assigned_miner_id=miner_id,
        started_at=started_at,
        expires_at=expires_at if expires_at is not None else datetime.now(UTC) + timedelta(hours=1),
    )
    session.add(job)
    session.commit()
    return job


def _miner(session: Session, miner_id: str = MINER, *, status: str = "ONLINE") -> Miner:
    miner = Miner(
        id=miner_id,
        concurrency=4,
        inflight=1,
        status=status,
        last_heartbeat=datetime.now(UTC),
        extra_metadata={},
        capabilities={},
    )
    session.add(miner)
    session.commit()
    return miner


@pytest.fixture
def job_service(db_session):
    return JobService(db_session)


# ---------------------------------------------------------------- claim stamp


def test_claim_stamps_started_at(db_session, job_service):
    """The QUEUED→RUNNING CAS records when the rental window opened."""
    _miner(db_session)
    job = job_service.create_job(
        client_id="client-1",
        req=JobCreate(payload=dict(GPU_PAYLOAD), ttl_seconds=900),
    )
    assert job.started_at is None

    claimed = job_service.acquire_next_job(db_session.get(Miner, MINER))
    assert claimed is not None
    row = db_session.get(Job, job.id)
    assert row.state == "RUNNING"
    assert row.started_at is not None
    assert abs((_aware(row.started_at) - datetime.now(UTC)).total_seconds()) < 60


# ------------------------------------------------------------- reaper sweeps


def test_reaper_keeps_running_gpu_job_inside_rental_window(db_engine):
    """expires_at past but rental window open → the reaper must not expire."""
    with Session(db_engine) as session:
        _running_gpu_job(
            session,
            "gpu-live",
            started_at=datetime.now(UTC) - timedelta(seconds=100),
            expires_at=datetime.now(UTC) - timedelta(seconds=50),  # queue deadline already past
        )
        reaper = StaleJobReaper(session_factory=lambda: session, batch_size=10)
        counts = reaper.run_once()
        assert counts["ttl_expired"] == 0
        assert session.get(Job, "gpu-live").state == "RUNNING"


def test_reaper_expires_gpu_job_past_rental_deadline(db_engine):
    """Once started_at + duration + slack passes, normal expiry applies."""
    with Session(db_engine) as session:
        _running_gpu_job(
            session,
            "gpu-dead",
            started_at=datetime.now(UTC) - timedelta(seconds=3600 + _GPU_COMPUTE_RENTAL_SLACK_SECONDS + 60),
            expires_at=datetime.now(UTC) - timedelta(seconds=50),
        )
        reaper = StaleJobReaper(session_factory=lambda: session, batch_size=10)
        counts = reaper.run_once()
        assert counts["ttl_expired"] == 1
        assert session.get(Job, "gpu-dead").state == "EXPIRED"


def test_reaper_expires_queued_gpu_job(db_engine):
    """QUEUED expiry is unchanged — a stale rental must not dispatch."""
    with Session(db_engine) as session:
        _running_gpu_job(
            session,
            "gpu-queued",
            state="QUEUED",
            miner_id=None,
            started_at=None,
            expires_at=datetime.now(UTC) - timedelta(seconds=50),
        )
        reaper = StaleJobReaper(session_factory=lambda: session, batch_size=10)
        counts = reaper.run_once()
        assert counts["ttl_expired"] == 1
        assert session.get(Job, "gpu-queued").state == "EXPIRED"


def test_reaper_keeps_gpu_job_with_stale_miner_inside_window(db_engine):
    """Miner-dead sweep honours the rental window too."""
    with Session(db_engine) as session:
        _miner(session, status="OFFLINE")
        miner = session.get(Miner, MINER)
        miner.last_heartbeat = datetime.now(UTC) - timedelta(seconds=3600)
        session.add(miner)
        session.commit()
        _running_gpu_job(
            session,
            "gpu-miner-dead",
            started_at=datetime.now(UTC) - timedelta(seconds=100),
            expires_at=datetime.now(UTC) + timedelta(hours=2),  # TTL sweep must not grab it
        )
        reaper = StaleJobReaper(session_factory=lambda: session, batch_size=10, miner_dead_seconds=600)
        counts = reaper.run_once()
        assert counts["miner_dead"] == 0
        assert session.get(Job, "gpu-miner-dead").state == "RUNNING"


# ------------------------------------------------------- _ensure_not_expired


def test_get_job_does_not_expire_running_gpu_inside_window(db_session, job_service):
    _miner(db_session)
    _running_gpu_job(
        db_session,
        "gpu-ensure-live",
        started_at=datetime.now(UTC) - timedelta(seconds=100),
        expires_at=datetime.now(UTC) - timedelta(seconds=50),
    )
    job = job_service.get_job("gpu-ensure-live")
    assert job.state == "RUNNING"


def test_get_job_expires_running_gpu_past_rental_deadline(db_session, job_service):
    _miner(db_session)
    _running_gpu_job(
        db_session,
        "gpu-ensure-dead",
        started_at=datetime.now(UTC) - timedelta(seconds=3600 + _GPU_COMPUTE_RENTAL_SLACK_SECONDS + 60),
        expires_at=datetime.now(UTC) - timedelta(seconds=50),
    )
    job = job_service.get_job("gpu-ensure-dead")
    assert job.state == "EXPIRED"


def test_get_job_expires_queued_gpu_normally(db_session, job_service):
    _miner(db_session)
    _running_gpu_job(
        db_session,
        "gpu-ensure-queued",
        state="QUEUED",
        miner_id=None,
        started_at=None,
        expires_at=datetime.now(UTC) - timedelta(seconds=50),
    )
    job = job_service.get_job("gpu-ensure-queued")
    assert job.state == "EXPIRED"


# ------------------------------------------------------- reconcile extension


def test_running_jobs_extends_expires_at_inside_window(db_session, job_service):
    _miner(db_session)
    started = datetime.now(UTC) - timedelta(seconds=100)
    _running_gpu_job(
        db_session,
        "gpu-recon",
        started_at=started,
        expires_at=datetime.now(UTC) - timedelta(seconds=10),  # would expire mid-rental
    )

    assigned = job_service.assigned_running_jobs(MINER)

    assert [a.job_id for a in assigned] == ["gpu-recon"]
    row = db_session.get(Job, "gpu-recon")
    # rental_deadline = started + 3600 + slack; expires_at = deadline + slack.
    expected = _aware(started) + timedelta(seconds=3600 + 2 * _GPU_COMPUTE_RENTAL_SLACK_SECONDS)
    assert abs((_aware(row.expires_at) - expected).total_seconds()) < 5
    assert _aware(row.expires_at) > datetime.now(UTC)


def test_running_jobs_extension_is_idempotent_and_capped(db_session, job_service):
    _miner(db_session)
    started = datetime.now(UTC) - timedelta(seconds=100)
    _running_gpu_job(
        db_session,
        "gpu-recon-cap",
        started_at=started,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    first = job_service.assigned_running_jobs(MINER)
    expiry_after_first = _aware(db_session.get(Job, "gpu-recon-cap").expires_at)
    cap = _aware(started) + timedelta(seconds=3600 + 2 * _GPU_COMPUTE_RENTAL_SLACK_SECONDS)
    assert expiry_after_first <= cap + timedelta(seconds=1)

    job_service.assigned_running_jobs(MINER)
    expiry_after_second = _aware(db_session.get(Job, "gpu-recon-cap").expires_at)
    assert expiry_after_second == expiry_after_first
    assert first[0].gpu_compute is not None


def test_running_jobs_returns_gpu_compute_window(db_session, job_service):
    _miner(db_session)
    started = datetime.now(UTC) - timedelta(seconds=100)
    _running_gpu_job(db_session, "gpu-recon-info", started_at=started)

    assigned = job_service.assigned_running_jobs(MINER)

    info = assigned[0].gpu_compute
    assert info is not None
    assert info.started_at == pytest.approx(started.timestamp(), abs=1)
    assert info.duration_seconds == pytest.approx(3600)
    assert info.rental_deadline == pytest.approx(started.timestamp() + 3600 + _GPU_COMPUTE_RENTAL_SLACK_SECONDS, abs=1)


def test_running_jobs_past_window_expires_not_extends(db_session, job_service):
    """remaining <= 0 → no extension; the row expires through the normal path."""
    _miner(db_session)
    _running_gpu_job(
        db_session,
        "gpu-recon-dead",
        started_at=datetime.now(UTC) - timedelta(seconds=3600 + _GPU_COMPUTE_RENTAL_SLACK_SECONDS + 60),
        expires_at=datetime.now(UTC) - timedelta(seconds=10),
    )
    assigned = job_service.assigned_running_jobs(MINER)
    assert assigned == []
    assert db_session.get(Job, "gpu-recon-dead").state == "EXPIRED"


# ------------------------------------------------------------- submit_result


@pytest.fixture
def miner_client(db_session):
    def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[require_miner] = lambda: {"sub": MINER, "role": "miner"}
    yield TestClient(app)
    app.dependency_overrides.pop(get_session, None)
    app.dependency_overrides.pop(require_miner, None)


def test_submit_result_accepted_after_expires_at_inside_window(miner_client, db_session):
    """A result landing after expires_at but before rental_deadline must settle."""
    _miner(db_session)
    _running_gpu_job(
        db_session,
        "gpu-submit",
        started_at=datetime.now(UTC) - timedelta(seconds=100),
        expires_at=datetime.now(UTC) - timedelta(seconds=50),
    )
    resp = miner_client.post(
        "/v1/miners/gpu-submit/result",
        json={"result": {"status": "completed", "output": {"duration_seconds": 100}}, "metrics": {}},
    )
    assert resp.status_code == 200, resp.text
    assert db_session.get(Job, "gpu-submit").state == "COMPLETED"


def test_submit_result_rejected_past_rental_deadline(miner_client, db_session):
    _miner(db_session)
    _running_gpu_job(
        db_session,
        "gpu-submit-dead",
        started_at=datetime.now(UTC) - timedelta(seconds=3600 + _GPU_COMPUTE_RENTAL_SLACK_SECONDS + 60),
        expires_at=datetime.now(UTC) - timedelta(seconds=50),
    )
    resp = miner_client.post(
        "/v1/miners/gpu-submit-dead/result",
        json={"result": {"status": "completed", "output": {}}, "metrics": {}},
    )
    # get_job flips the row to EXPIRED → submit_result answers 409, not 200.
    assert resp.status_code == 409
    assert db_session.get(Job, "gpu-submit-dead").state == "EXPIRED"
