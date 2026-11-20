"""Reconcile endpoint tests for #2315 (Refs #2315).

``/v1/miners/poll`` delivers a claimed job only inside the claim response;
a lost response strands the row RUNNING with no miner-side record.
``GET /v1/miners/{miner_id}/running-jobs`` returns the caller's RUNNING
jobs in ``AssignedJob`` dispatch shape so the miner can re-dispatch what
it never received. These tests pin the ownership guard, the dispatch
shape, state filtering, and the expired-row transition.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from aitbc.auth.dependencies import require_miner

from coordinator_api.contexts.infrastructure.domain.job import Job
from coordinator_api.contexts.infrastructure.domain.miner import Miner
from coordinator_api.contexts.infrastructure.services.miners import MinerService
from coordinator_api.main import app
from coordinator_api.schemas import MinerRegister
from coordinator_api.storage import get_session


EVIL = {"sub": "miner-evil", "role": "miner"}
MINER = "miner-recon"
SECRET_PROMPT = "RECON-SECRET-PROMPT"


@pytest.fixture
def caller_client(db_session):
    """TestClient factory: caller identity is swapped per test, in-memory DB."""

    def _make(caller: dict[str, str]) -> TestClient:
        def override_session():
            yield db_session

        app.dependency_overrides[get_session] = override_session
        app.dependency_overrides[require_miner] = lambda: caller
        return TestClient(app)

    yield _make
    app.dependency_overrides.pop(get_session, None)
    app.dependency_overrides.pop(require_miner, None)


def _register(db_session: Session, miner_id: str = MINER) -> None:
    MinerService(db_session).register(
        miner_id,
        MinerRegister(capabilities={"gpu": "probe"}, wallet_address="0x" + "22" * 20),
    )


def _job(
    db_session: Session,
    job_id: str,
    *,
    state: str = "RUNNING",
    miner_id: str | None = MINER,
    expires_at: datetime | None = None,
) -> Job:
    job = Job(
        id=job_id,
        client_id="client-1",
        state=state,
        payload={"type": "inference", "prompt": SECRET_PROMPT},
        constraints={},
        assigned_miner_id=miner_id,
        expires_at=expires_at or (datetime.now(UTC) + timedelta(hours=1)),
    )
    db_session.add(job)
    db_session.commit()
    return job


@pytest.mark.unit
class TestRunningJobsReconcile:
    def test_returns_own_running_job_in_assigned_shape(self, caller_client, db_session):
        _register(db_session)
        _job(db_session, "job-run1")
        _job(db_session, "job-queued", state="QUEUED", miner_id=None)
        _job(db_session, "job-done", state="COMPLETED")
        _job(db_session, "job-other", miner_id="miner-someone-else")
        client = caller_client({"sub": MINER, "role": "miner"})

        resp = client.get(f"/v1/miners/{MINER}/running-jobs")

        assert resp.status_code == 200
        body = resp.json()
        assert body["miner_id"] == MINER
        assert [j["job_id"] for j in body["jobs"]] == ["job-run1"]
        job = body["jobs"][0]
        assert job["payload"]["prompt"] == SECRET_PROMPT
        assert "constraints" in job
        assert isinstance(job["expires_at"], float)

    def test_refuses_other_miner_id(self, caller_client, db_session):
        _register(db_session)
        _job(db_session, "job-run1")
        client = caller_client(EVIL)
        resp = client.get(f"/v1/miners/{MINER}/running-jobs")
        assert resp.status_code == 403
        assert SECRET_PROMPT not in resp.text

    def test_empty_when_nothing_running(self, caller_client, db_session):
        _register(db_session)
        client = caller_client({"sub": MINER, "role": "miner"})
        resp = client.get(f"/v1/miners/{MINER}/running-jobs")
        assert resp.status_code == 200
        assert resp.json()["jobs"] == []

    def test_expired_running_row_is_transitioned_not_returned(self, caller_client, db_session):
        _register(db_session)
        _job(
            db_session,
            "job-stale",
            expires_at=datetime.now(UTC) - timedelta(minutes=1),
        )
        client = caller_client({"sub": MINER, "role": "miner"})

        resp = client.get(f"/v1/miners/{MINER}/running-jobs")

        assert resp.status_code == 200
        assert resp.json()["jobs"] == []
        db_session.expire_all()
        assert db_session.get(Job, "job-stale").state == "EXPIRED"

    def test_does_not_touch_miner_inflight(self, caller_client, db_session):
        _register(db_session)
        _job(db_session, "job-run1")
        client = caller_client({"sub": MINER, "role": "miner"})

        resp = client.get(f"/v1/miners/{MINER}/running-jobs")

        assert resp.status_code == 200
        db_session.expire_all()
        miner = db_session.get(Miner, MINER)
        assert miner.inflight == 0
