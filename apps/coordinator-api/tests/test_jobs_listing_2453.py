"""AI-JOBS-LISTING-1 (#2453): ``GET /v1/jobs`` and ``/v1/jobs/history`` must
report the true match count (not the page length), expose ``has_more``, and
``GET /v1/jobs/inflight`` must answer the cheap queued+running headroom check
without returning job rows.
"""

from __future__ import annotations

import pytest

from aitbc.auth import require_admin_or_client
from coordinator_api.custom_types import JobState
from coordinator_api.main import app
from coordinator_api.schemas import JobCreate
from coordinator_api.services import JobService

CLIENT = {"sub": "client1", "role": "client"}


@pytest.fixture(autouse=True)
def _auth_overrides():
    app.dependency_overrides[require_admin_or_client] = lambda: CLIENT
    yield
    app.dependency_overrides.pop(require_admin_or_client, None)


@pytest.fixture
def job_service(db_session):
    return JobService(db_session)


@pytest.fixture
def canned_jobs(db_session, job_service):
    """Four jobs for client1 across states, plus one foreign job."""
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

    # Foreign job owned by a different client — inserted directly because
    # resolve_client only auto-creates wallet-address identities.
    from coordinator_api.contexts.infrastructure.domain.job import Job

    foreign = Job(
        client_id="client2",
        client_ref="client2",
        state="QUEUED",
        payload={"type": "inference", "prompt": "foreign"},
        constraints={},
        ttl_seconds=900,
    )
    db_session.add(foreign)
    db_session.commit()
    return jobs


# --- GET /v1/jobs ------------------------------------------------------------


def test_list_jobs_total_is_true_count_not_page_size(client, canned_jobs):
    resp = client.get("/v1/jobs", params={"limit": 2})
    assert resp.status_code == 200
    payload = resp.json()
    assert len(payload["items"]) == 2
    assert payload["total"] == 4  # client1's four jobs, not the page size
    assert payload["has_more"] is True


def test_list_jobs_last_page_has_more_false(client, canned_jobs):
    resp = client.get("/v1/jobs", params={"limit": 10})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["total"] == 4
    assert payload["has_more"] is False


def test_list_jobs_total_respects_status_filter(client, canned_jobs):
    resp = client.get("/v1/jobs", params={"status": "completed", "limit": 1})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["total"] == 1
    assert payload["has_more"] is False


def test_list_jobs_offset_pages_with_true_total(client, canned_jobs):
    resp = client.get("/v1/jobs", params={"limit": 2, "offset": 2})
    assert resp.status_code == 200
    payload = resp.json()
    assert len(payload["items"]) == 2
    assert payload["total"] == 4
    assert payload["has_more"] is False


# --- GET /v1/jobs/history ----------------------------------------------------


def test_job_history_total_is_true_count(client, canned_jobs):
    resp = client.get("/v1/jobs/history", params={"limit": 2})
    assert resp.status_code == 200
    payload = resp.json()
    assert len(payload["items"]) == 2
    assert payload["total"] == 4
    assert payload["has_more"] is True


# --- GET /v1/jobs/inflight ----------------------------------------------------


def test_jobs_inflight_counts_queued_and_running_only(client, canned_jobs):
    resp = client.get("/v1/jobs/inflight")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["inflight"] == 2  # queued + running; client2's job excluded
    assert payload["cap"] >= 1
    # Aggregate answer: no job rows leak into the headroom check.
    assert "items" not in payload


def test_jobs_inflight_route_not_captured_by_job_id(client, canned_jobs):
    # Regression guard: /jobs/{job_id} must not swallow the literal "inflight".
    resp = client.get("/v1/jobs/inflight")
    assert resp.status_code == 200
    assert "job_id" not in resp.json()
