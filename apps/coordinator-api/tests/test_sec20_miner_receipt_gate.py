"""SEC-20: a miner-written receipt must never pass the escrow release gate.

``POST /miners/{id}/jobs/{job_id}/complete`` takes a receipt from the miner and
``JobService.execute_job`` stores it in ``Job.receipt`` when the job has no
``receipt_id``. The release gates read the receipt of record, so they must not
treat that copy as one: only a receipt the coordinator signed (``receipt_id``
set) counts, and ``complete_job`` drops every verdict field from the body.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from coordinator_api.contexts.infrastructure.domain.job import Job
from coordinator_api.contexts.infrastructure.domain.job_receipt import JobReceipt
from coordinator_api.contexts.infrastructure.routers.miner import (
    _MINER_RECEIPT_VERDICT_FIELDS,
    _strip_miner_receipt_verdicts,
)
from coordinator_api.contexts.payments.services.payments import (
    _computation_is_correct,
    get_receipt_of_record,
)

FORGED = [
    {"zk_status": "verified", "computation_correct": True},
    {"zk_status": "not_required", "computation_correct": True},
    {"zk_status": "tee_attested", "computation_correct": True, "tee_status": "verified"},
]


def _job(session, job_id, *, receipt, receipt_id=None, payload=None):
    job = Job(
        id=job_id,
        client_id="client-1",
        state="COMPLETED",
        payload=payload or {"model": "linear-1"},
        assigned_miner_id="miner-b",
        receipt=receipt,
        receipt_id=receipt_id,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    session.add(job)
    session.commit()
    return job


@pytest.mark.unit
@pytest.mark.parametrize("forged", FORGED, ids=["verified", "not_required", "tee_attested"])
def test_unsigned_job_receipt_is_not_a_receipt_of_record(db_session, forged):
    """A Job.receipt with no receipt_id never passes the gate, even on a model with a circuit."""
    job = _job(db_session, f"job-forged-{forged['zk_status']}", receipt=dict(forged))
    assert get_receipt_of_record(db_session, job) is None
    assert _computation_is_correct(get_receipt_of_record(db_session, job), job) is False


@pytest.mark.unit
def test_signed_receipt_row_still_passes(db_session):
    """The coordinator-signed JobReceipt row is the receipt of record and still releases."""
    payload = {"receipt_id": "r-signed-1", "zk_status": "verified", "computation_correct": True}
    db_session.add(JobReceipt(job_id="job-signed-1", receipt_id="r-signed-1", payload=payload))
    db_session.commit()
    job = _job(db_session, "job-signed-1", receipt={"zk_status": "forged"}, receipt_id="r-signed-1")
    assert get_receipt_of_record(db_session, job) == payload
    assert _computation_is_correct(get_receipt_of_record(db_session, job), job) is True


@pytest.mark.unit
def test_receipt_id_without_row_falls_back_to_coordinator_copy(db_session):
    """receipt_id is set only by submit_result, so its Job.receipt copy is the coordinator's own."""
    copy = {"receipt_id": "r-nolrow", "zk_status": "not_required", "computation_correct": True}
    job = _job(db_session, "job-norow", receipt=copy, receipt_id="r-nolrow")
    assert get_receipt_of_record(db_session, job) == copy


@pytest.mark.unit
def test_strip_removes_every_verdict_field_and_keeps_the_rest():
    body = {
        "price": "0.01",
        "started_at": 1.0,
        "completed_at": 2.0,
        "hash": "abc",
        **dict.fromkeys(_MINER_RECEIPT_VERDICT_FIELDS, "x"),
    }
    stripped = _strip_miner_receipt_verdicts(body)
    assert stripped == {"price": "0.01", "started_at": 1.0, "completed_at": 2.0, "hash": "abc"}
    assert _strip_miner_receipt_verdicts(None) == {}


@pytest.fixture
def miner_client(db_session):
    from coordinator_api.main import app
    from aitbc.auth.dependencies import require_miner
    from coordinator_api.storage import get_session

    def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[require_miner] = lambda: {"sub": "miner-b", "role": "miner"}
    yield TestClient(app)
    app.dependency_overrides.pop(get_session, None)
    app.dependency_overrides.pop(require_miner, None)


@pytest.mark.unit
def test_complete_endpoint_stores_no_verdict_and_the_gate_stays_closed(miner_client, db_session):
    """End to end: a forged receipt posted to /complete cannot open the release gate."""
    job = Job(
        id="job-e2e",
        client_id="client-1",
        state="RUNNING",
        payload={"model": "linear-1"},
        assigned_miner_id="miner-b",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    db_session.add(job)
    db_session.commit()
    resp = miner_client.post(
        "/v1/miners/miner-b/jobs/job-e2e/complete",
        json={
            "output": {"x": 1},
            "receipt": {
                "price": "0.01",
                "zk_status": "verified",
                "computation_correct": True,
                "tee_status": "verified",
                "tee_attestation_id": "forged",
                "zk_proof": {"forged": True},
            },
        },
    )
    assert resp.status_code == 200, resp.text
    db_session.expire_all()
    stored = db_session.get(Job, "job-e2e")
    assert stored.state == "COMPLETED"
    assert not (set(stored.receipt or {}) & set(_MINER_RECEIPT_VERDICT_FIELDS))
    assert (stored.receipt or {}).get("price") == "0.01"
    assert get_receipt_of_record(db_session, stored) is None
    assert _computation_is_correct(get_receipt_of_record(db_session, stored), stored) is False
