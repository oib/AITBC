"""#2951: refuse ZK-required jobs whose model has no registered circuit.

Before this, ``--zk-proof-required`` + an unregistered model (e.g.
``llama3.2:3b``) was accepted, escrowed, dispatched and executed — and only
then failed ``zk_status=unsupported_model`` into a refund, leaving the miner
unpaid. The coordinator knows the circuit registry before any escrow moves,
so submission refuses the combination and the dispatch gate is the backstop
for rows that predate the check.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi import HTTPException

from coordinator_api.contexts.infrastructure.domain import Job, Miner
from coordinator_api.contexts.infrastructure.routers import client as client_router
from coordinator_api.contexts.infrastructure.services.jobs import JobService
from coordinator_api.contexts.payments.services import payments as payments_module
from coordinator_api.custom_types import Constraints
from coordinator_api.schemas import JobCreate


@pytest.fixture(autouse=True)
def _zk_gate_env(monkeypatch):
    """Pin the ZK threshold/require env the gate reads so tests are deterministic."""
    monkeypatch.setattr(payments_module, "_ZK_THRESHOLD_AIT", Decimal("10"))
    monkeypatch.setattr(payments_module, "_ZK_REQUIRE_PROOF", False)


def _req(*, model="llama3.2:3b", zk=False, amount=None) -> JobCreate:
    return JobCreate(
        payload={"type": "inference", "prompt": "what is 17 times 23?", "model": model},
        constraints=Constraints(zk_proof_required=zk),
        payment_amount=amount,
    )


# ---------------------------------------------------------------------------
# Submission refusal (client router)
# ---------------------------------------------------------------------------


def test_explicit_zk_required_unregistered_model_is_refused() -> None:
    with pytest.raises(HTTPException) as exc:
        client_router._require_zk_circuit_model(_req(zk=True))
    assert exc.value.status_code == 422
    assert "llama3.2:3b" in exc.value.detail
    assert "circuit" in exc.value.detail


def test_explicit_zk_required_registered_model_passes() -> None:
    client_router._require_zk_circuit_model(_req(model="linear-1", zk=True))


def test_non_zk_unregistered_model_passes() -> None:
    client_router._require_zk_circuit_model(_req(zk=False, amount=Decimal("5")))


def test_high_value_threshold_unregistered_model_is_refused() -> None:
    """The auto-trigger (amount >= threshold) refuses the same way as the flag."""
    with pytest.raises(HTTPException) as exc:
        client_router._require_zk_circuit_model(_req(zk=False, amount=Decimal("10")))
    assert exc.value.status_code == 422


def test_high_value_registered_model_passes() -> None:
    client_router._require_zk_circuit_model(_req(model="linear-1", zk=False, amount=Decimal("10")))


def test_zk_require_env_refuses_unregistered_model(monkeypatch) -> None:
    monkeypatch.setattr(payments_module, "_ZK_REQUIRE_PROOF", True)
    with pytest.raises(HTTPException) as exc:
        client_router._require_zk_circuit_model(_req(zk=False, amount=None))
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_submit_refuses_before_touching_the_database() -> None:
    # session=None: the refusal must come before JobService is built, so no
    # job row and no escrow are ever created for the miner to burn compute on.
    with pytest.raises(HTTPException) as exc:
        await client_router._submit_job_impl(_req(zk=True), None, {"sub": "client-1"})  # type: ignore[arg-type]
    assert exc.value.status_code == 422
    assert "circuit" in exc.value.detail


# ---------------------------------------------------------------------------
# Dispatch backstop (JobService.acquire_next_job)
# ---------------------------------------------------------------------------


@pytest.fixture
def job_service(db_session):
    return JobService(db_session)


@pytest.fixture
def miner(db_session):
    miner = Miner(
        id="miner_zk_gate",
        concurrency=1,
        inflight=0,
        status="ONLINE",
        extra_metadata={},
        capabilities={},
    )
    db_session.add(miner)
    db_session.commit()
    db_session.refresh(miner)
    return miner


def _queued_job(job_service, *, model, zk=True):
    return job_service.create_job(
        client_id="client1",
        req=JobCreate(
            payload={"type": "inference", "prompt": "what is 17 times 23?", "model": model},
            constraints=Constraints(zk_proof_required=zk),
            ttl_seconds=900,
        ),
    )


def test_dispatch_skips_zk_required_unregistered_model(db_session, job_service, miner):
    """A ZK-required job with no circuit must never reach a miner."""
    job = _queued_job(job_service, model="llama3.2:3b")

    assert job_service.acquire_next_job(miner) is None

    refreshed = db_session.get(Job, job.id)
    assert refreshed is not None
    assert refreshed.state == "QUEUED"
    assert refreshed.assigned_miner_id is None


def test_dispatch_allows_zk_required_registered_model(db_session, job_service, miner):
    """The registered circuit model still dispatches — the gate is not a blanket ban."""
    job = _queued_job(job_service, model="linear-1")

    acquired = job_service.acquire_next_job(miner)
    assert acquired is not None
    assert acquired.id == job.id
    assert acquired.state == "RUNNING"


def test_dispatch_allows_non_zk_unregistered_model(db_session, job_service, miner):
    """Without a ZK requirement the same model dispatches normally."""
    job = _queued_job(job_service, model="llama3.2:3b", zk=False)

    acquired = job_service.acquire_next_job(miner)
    assert acquired is not None
    assert acquired.id == job.id
