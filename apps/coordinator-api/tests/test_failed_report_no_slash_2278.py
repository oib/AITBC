"""#2278: a miner-reported job failure must not slash the provider's bond.

``POST /miners/{job_id}/fail`` and ``POST /miners/{job_id}/result`` with
``result.status="failed"`` used to slash ``BAD_RESULT`` (30% of the bond, sent
to the burn address) on a bonded job. The failure is the miner's own unverified
claim and the customer chooses the input that caused it — while the failed job
costs the customer nothing (the escrow stays refundable) — so a customer could
burn a provider's bond for free. Verified faults still slash: the ZK gates,
an operator-ruled refund and the downtime sweeper.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from coordinator_api.contexts.infrastructure.domain.job import Job
from coordinator_api.contexts.infrastructure.domain.miner import Miner
from coordinator_api.contexts.market.services.bond_slashing import SlashingCondition

_SLASH = "coordinator_api.contexts.market.services.bond_slashing.BondSlashingService.slash"


def _bonded_running_job(session: Session, job_id: str, *, bonded: bool = True) -> Job:
    job = Job(
        id=job_id,
        client_id="client-1",
        state="RUNNING",
        payload={"type": "inference", "model": "linear-1"},
        constraints={"bond_required": True} if bonded else {},
        assigned_miner_id="miner-b",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    session.add(job)
    if session.get(Miner, "miner-b") is None:
        session.add(Miner(id="miner-b", inflight=1, status="ONLINE", extra_metadata={}, capabilities={}))
    session.commit()
    return job


@pytest.fixture
def miner_client(db_session):
    from aitbc.auth.dependencies import require_miner

    from coordinator_api.main import app
    from coordinator_api.storage import get_session

    def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[require_miner] = lambda: {"sub": "miner-b", "role": "miner"}
    yield TestClient(app)
    app.dependency_overrides.pop(get_session, None)
    app.dependency_overrides.pop(require_miner, None)


@pytest.mark.unit
def test_failed_result_does_not_slash_bonded_provider(miner_client, db_session):
    """/result with status=failed on a bond_required job: FAILED, no slash."""
    _bonded_running_job(db_session, "job-2278a")
    with patch(_SLASH, new_callable=AsyncMock) as slash:
        resp = miner_client.post(
            "/v1/miners/job-2278a/result",
            json={"result": {"status": "failed", "error": "prompt exceeds context window"}, "metrics": {}},
        )
    assert resp.status_code == 200, resp.text
    assert resp.json()["job_state"] == "FAILED"
    slash.assert_not_awaited()
    db_session.expire_all()
    assert db_session.get(Job, "job-2278a").state == "FAILED"


@pytest.mark.unit
def test_fail_route_does_not_slash_bonded_provider(miner_client, db_session):
    """/fail on a bond_required job: FAILED with the miner's error, no slash."""
    _bonded_running_job(db_session, "job-2278b")
    with patch(_SLASH, new_callable=AsyncMock) as slash:
        resp = miner_client.post(
            "/v1/miners/job-2278b/fail",
            json={"error_code": "ENGINE_ERROR", "error_message": "engine crashed on input"},
        )
    assert resp.status_code == 200, resp.text
    slash.assert_not_awaited()
    db_session.expire_all()
    job = db_session.get(Job, "job-2278b")
    assert job.state == "FAILED"
    assert job.error == "engine crashed on input"


@pytest.mark.unit
def test_zk_gate_failure_still_slashes_bonded_provider(db_session):
    """Positive control: the verified-fault slash path is untouched, so the two
    no-slash pins above are not vacuous."""
    from coordinator_api.contexts.infrastructure.routers.miner import _zk_gate_failure

    job = _bonded_running_job(db_session, "job-2278c")
    with patch(_SLASH, new_callable=AsyncMock) as slash:
        asyncio.run(_zk_gate_failure(db_session, job, "invalid"))
    slash.assert_awaited_once()
    assert slash.await_args.args[1] is SlashingCondition.BAD_RESULT
