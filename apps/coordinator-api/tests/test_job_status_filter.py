"""AIJOBS-STATUS-1 (#444): the ?status= filter on the job-list endpoints must
actually filter, alias ``pending`` -> QUEUED, accept ``all`` as unfiltered, and
answer HTTP 400 for unknown values instead of silently dropping the filter.

Previously ``JobState(status.upper())`` was wrapped in ``except ValueError:
pass`` in ``GET /v1/jobs``, ``GET /v1/jobs/history`` and
``POST /v1/miners/{id}/jobs``, so ``aitbc ai jobs --status pending`` (no PENDING
member in JobState) returned the unfiltered list.
"""

from __future__ import annotations

import pytest

from aitbc.auth import require_admin_or_client, require_miner
from coordinator_api.custom_types import JobState, parse_job_state_filter
from coordinator_api.main import app
from coordinator_api.schemas import JobCreate
from coordinator_api.services import JobService

CLIENT = {"sub": "client1", "role": "client"}
MINER = {"sub": "miner-1", "role": "miner"}


@pytest.fixture(autouse=True)
def _auth_overrides():
    app.dependency_overrides[require_admin_or_client] = lambda: CLIENT
    app.dependency_overrides[require_miner] = lambda: MINER
    yield
    app.dependency_overrides.pop(require_admin_or_client, None)
    app.dependency_overrides.pop(require_miner, None)


@pytest.fixture
def job_service(db_session):
    return JobService(db_session)


@pytest.fixture
def canned_jobs(db_session, job_service):
    """One job per interesting state, all owned by client1."""
    jobs = {}
    for name, state in (
        ("queued", JobState.queued),
        ("running", JobState.running),
        ("completed", JobState.completed),
        ("failed", JobState.failed),
    ):
        req = JobCreate(payload={"type": "inference", "prompt": name}, ttl_seconds=900)
        job = job_service.create_job(client_id="client1", req=req)
        job.state = state
        job.assigned_miner_id = "miner-1"
        db_session.add(job)
        db_session.commit()
        db_session.refresh(job)
        jobs[name] = job
    return jobs


def _states(payload: dict) -> set[str]:
    return {row["state"] for row in payload["items"]}


# --- parse_job_state_filter unit behaviour ---------------------------------


def test_parse_pending_aliases_to_queued():
    assert parse_job_state_filter("pending") is JobState.queued


def test_parse_all_means_unfiltered():
    assert parse_job_state_filter("all") is None
    assert parse_job_state_filter("ANY") is None


def test_parse_valid_state_case_insensitive():
    assert parse_job_state_filter("Completed") is JobState.completed


def test_parse_unknown_raises():
    with pytest.raises(ValueError):
        parse_job_state_filter("bogus")


# --- GET /v1/jobs ------------------------------------------------------------


def test_list_jobs_filters_by_status(client, canned_jobs):
    resp = client.get("/v1/jobs", params={"status": "completed"})
    assert resp.status_code == 200
    payload = resp.json()
    assert _states(payload) == {"COMPLETED"}


def test_list_jobs_pending_alias_returns_queued(client, canned_jobs):
    resp = client.get("/v1/jobs", params={"status": "pending"})
    assert resp.status_code == 200
    assert _states(resp.json()) == {"QUEUED"}


def test_list_jobs_all_returns_everything(client, canned_jobs):
    resp = client.get("/v1/jobs", params={"status": "all"})
    assert resp.status_code == 200
    assert len(resp.json()["items"]) == len(canned_jobs)


def test_list_jobs_invalid_status_answers_400(client, canned_jobs):
    resp = client.get("/v1/jobs", params={"status": "bogus"})
    assert resp.status_code == 400
    assert "completed" in resp.json()["detail"]


# --- GET /v1/jobs/history ----------------------------------------------------


def test_job_history_filters_by_status(client, canned_jobs):
    resp = client.get("/v1/jobs/history", params={"status": "failed"})
    assert resp.status_code == 200
    assert _states(resp.json()) == {"FAILED"}


def test_job_history_invalid_status_answers_400(client, canned_jobs):
    resp = client.get("/v1/jobs/history", params={"status": "bogus"})
    assert resp.status_code == 400


# --- POST /v1/miners/{miner_id}/jobs -----------------------------------------


def test_miner_jobs_filters_by_job_status(client, canned_jobs):
    resp = client.post("/v1/miners/miner-1/jobs", params={"job_status": "pending"})
    assert resp.status_code == 200
    assert {row["state"] for row in resp.json()["jobs"]} == {"QUEUED"}


def test_miner_jobs_invalid_job_status_answers_400(client, canned_jobs):
    resp = client.post("/v1/miners/miner-1/jobs", params={"job_status": "bogus"})
    assert resp.status_code == 400
