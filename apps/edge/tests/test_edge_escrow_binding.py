"""EDGE-PAY-1 (#1668): escrow binding, single-use and amount coverage.

Before this change ``POST /v1/serve/requests`` verified the escrow was
``locked`` and discarded the identity — the same locked escrow could
authorize unlimited submissions and nothing bound escrow to request for
settlement/dispute. The verified key and locked amount are now persisted
on ``ComputeRequest`` behind a unique ``escrow_id`` (single-use), and an
optional ``expected_amount`` ceiling is checked against the locked amount.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlmodel import SQLModel, select

import aitbc_edge.services.serve_service as serve_svc_mod
from aitbc.auth import create_access_token
from aitbc_edge.routers import serve as serve_router_mod
from aitbc_edge.schemas.serve import ComputeRequest
from aitbc_edge.services.serve_service import EscrowAlreadyUsedError, ServeService


# ---------------------------------------------------------------------------
# Service layer: persistence + single-use (in-memory sqlite, same convention
# as test_service_branches.py)
# ---------------------------------------------------------------------------


@pytest.fixture
async def engine(tmp_path):
    eng = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/edge.db")
    async with eng.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield eng
    await eng.dispose()


def _patch_sessions(monkeypatch, engine):
    @asynccontextmanager
    async def fake_get_session():
        async with AsyncSession(engine) as session:
            yield session

    monkeypatch.setattr(serve_svc_mod, "get_session", fake_get_session)


@pytest.mark.asyncio
async def test_submit_persists_escrow_binding(engine, monkeypatch):
    _patch_sessions(monkeypatch, engine)
    svc = ServeService()
    result = await svc.submit_compute_request(
        "gpu-1",
        "model-x",
        {"prompt": "hi"},
        owner_id="user-1",
        escrow_id="job_abc",
        escrow_amount=Decimal("2.50000000"),
    )
    assert result["success"] is True
    async with AsyncSession(engine) as session:
        row = (await session.execute(select(ComputeRequest))).scalar_one()
    assert row.escrow_id == "job_abc"
    assert row.escrow_amount == Decimal("2.50000000")
    assert row.owner_id == "user-1"


@pytest.mark.asyncio
async def test_duplicate_escrow_rejected(engine, monkeypatch):
    _patch_sessions(monkeypatch, engine)
    svc = ServeService()
    await svc.submit_compute_request("gpu-1", "m", {}, escrow_id="job_dup", escrow_amount=Decimal("1"))
    with pytest.raises(EscrowAlreadyUsedError):
        await svc.submit_compute_request("gpu-2", "m", {}, escrow_id="job_dup", escrow_amount=Decimal("1"))
    async with AsyncSession(engine) as session:
        rows = (await session.execute(select(ComputeRequest))).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_unpaid_requests_share_null_escrow(engine, monkeypatch):
    _patch_sessions(monkeypatch, engine)
    svc = ServeService()
    first = await svc.submit_compute_request("gpu-1", "m", {})
    second = await svc.submit_compute_request("gpu-1", "m", {})
    assert first["success"] and second["success"]
    async with AsyncSession(engine) as session:
        rows = (await session.execute(select(ComputeRequest))).scalars().all()
    assert len(rows) == 2
    assert all(r.escrow_id is None for r in rows)


@pytest.mark.asyncio
async def test_get_request_exposes_escrow_binding(engine, monkeypatch):
    _patch_sessions(monkeypatch, engine)
    svc = ServeService()
    result = await svc.submit_compute_request("gpu-1", "m", {}, escrow_id="job_view", escrow_amount=Decimal("3"))
    got = await svc.get_compute_request(result["request_id"], owner_id=None)
    assert got is not None
    assert got["escrow_id"] == "job_view"
    assert Decimal(got["escrow_amount"]) == Decimal("3")


# ---------------------------------------------------------------------------
# Router layer: verification -> binding, amount check, 409 on reuse
# ---------------------------------------------------------------------------


def _token(sub: str = "user-1", role: str = "client") -> str:
    return create_access_token(sub, role)


class _CapturingServeService:
    def __init__(self, error: Exception | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._error = error

    async def submit_compute_request(self, gpu_id, model_name, input_data, priority="normal", **kwargs):
        self.calls.append({"gpu_id": gpu_id, **kwargs})
        if self._error is not None:
            raise self._error
        return {"success": True, "request_id": "req_x", "status": "queued"}


class _StubEscrowRPC:
    """Stands in for aitbc.market.BlockchainRPCClient (imported lazily)."""

    reply: dict[str, Any] | None = {"status": "locked", "amount": "5.0", "job_id": "job_1"}
    calls: list[str] = []

    def __init__(self, **kwargs: Any) -> None:
        pass

    async def verify_escrow(self, job_id: str):
        type(self).calls.append(job_id)
        return type(self).reply


@pytest.fixture
def router_env(monkeypatch):
    monkeypatch.setattr(serve_router_mod.settings, "require_payment_verification", True)
    _StubEscrowRPC.reply = {"status": "locked", "amount": "5.0", "job_id": "job_1"}
    _StubEscrowRPC.calls = []
    monkeypatch.setattr("aitbc.market.BlockchainRPCClient", _StubEscrowRPC)
    app = FastAPI()
    app.include_router(serve_router_mod.router, prefix="/v1/serve")
    svc = _CapturingServeService()
    app.dependency_overrides[serve_router_mod.get_serve_service] = lambda: svc
    yield TestClient(app), svc
    app.dependency_overrides.clear()


def _post(client: TestClient, body: dict[str, Any], sub: str = "user-1"):
    return client.post(
        "/v1/serve/requests",
        json={"gpu_id": "g1", "model_name": "m", "input_data": {}, **body},
        headers={"Authorization": f"Bearer {_token(sub)}"},
    )


def test_locked_escrow_is_bound_to_request(router_env):
    client, svc = router_env
    r = _post(client, {"job_id": "job_1", "expected_amount": "4.5"})
    assert r.status_code == 200, r.text
    call = svc.calls[-1]
    assert call["escrow_id"] == "job_1"
    assert call["escrow_amount"] == Decimal("5.0")
    assert call["owner_id"] == "user-1"
    assert _StubEscrowRPC.calls == ["job_1"]


def test_legacy_escrow_id_key_still_accepted(router_env):
    client, svc = router_env
    r = _post(client, {"escrow_id": "legacy_9"})
    assert r.status_code == 200, r.text
    assert svc.calls[-1]["escrow_id"] == "legacy_9"


def test_unlocked_escrow_rejected(router_env):
    client, svc = router_env
    _StubEscrowRPC.reply = {"status": "released", "amount": "5.0"}
    r = _post(client, {"job_id": "job_1"})
    assert r.status_code == 402
    assert not svc.calls


def test_missing_escrow_key_rejected(router_env):
    client, svc = router_env
    r = _post(client, {})
    assert r.status_code == 402
    assert not svc.calls


def test_expected_amount_above_locked_rejected(router_env):
    client, svc = router_env
    r = _post(client, {"job_id": "job_1", "expected_amount": "5.1"})
    assert r.status_code == 402
    assert not svc.calls


def test_expected_amount_equal_locked_accepted(router_env):
    client, svc = router_env
    r = _post(client, {"job_id": "job_1", "expected_amount": "5.0"})
    assert r.status_code == 200, r.text


def test_malformed_expected_amount_rejected(router_env):
    client, svc = router_env
    r = _post(client, {"job_id": "job_1", "expected_amount": "not-a-number"})
    assert r.status_code == 422
    assert not svc.calls


def test_escrow_reuse_maps_to_409(router_env, monkeypatch):
    monkeypatch.setattr(serve_router_mod.settings, "require_payment_verification", True)
    _StubEscrowRPC.reply = {"status": "locked", "amount": "5.0", "job_id": "job_1"}
    monkeypatch.setattr("aitbc.market.BlockchainRPCClient", _StubEscrowRPC)
    app = FastAPI()
    app.include_router(serve_router_mod.router, prefix="/v1/serve")
    app_svc = _CapturingServeService(error=EscrowAlreadyUsedError("job_1"))
    app.dependency_overrides[serve_router_mod.get_serve_service] = lambda: app_svc
    r = _post(TestClient(app), {"job_id": "job_1"})
    assert r.status_code == 409
    app.dependency_overrides.clear()
