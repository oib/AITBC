"""Branch coverage for edge services, clients and the compute worker.

Uses the same convention as ``test_island_leave_stale.py``: an in-memory
sqlite engine with each service module's ``get_session`` monkeypatched, and
stub RPC clients for the blockchain boundary. No network, no real DB files.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlmodel import SQLModel, select

import aitbc_edge.services.compute_worker as worker_mod
import aitbc_edge.services.database_service as db_svc_mod
import aitbc_edge.services.gpu_service as gpu_svc_mod
import aitbc_edge.services.island_service as island_svc_mod
import aitbc_edge.services.metrics_service as metrics_svc_mod
import aitbc_edge.services.serve_service as serve_svc_mod
from aitbc_edge.clients.blockchain_rpc import BlockchainRPCClient
from aitbc_edge.clients.gpu_service import GPUServiceClient
from aitbc_edge.schemas.database import EdgeDatabase
from aitbc_edge.schemas.gpu import GPUListing
from aitbc_edge.schemas.island import BridgeRequest, IslandMembership, IslandStatus
from aitbc_edge.schemas.serve import ComputeRequest, ComputeResult
from aitbc_edge.services.compute_worker import (
    _execute_request,
    _execute_stub,
    _extract_prompt,
    process_queued_requests,
)
from aitbc_edge.services.database_service import DatabaseService, SyncNotImplementedError
from aitbc_edge.services.gpu_service import GPUService
from aitbc_edge.services.island_service import IslandService
from aitbc_edge.services.metrics_service import MetricsService
from aitbc_edge.services.serve_service import ServeService


@pytest.fixture
async def engine(tmp_path):
    """In-memory-ish sqlite engine with the full edge schema."""
    eng = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/edge.db")
    async with eng.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield eng
    await eng.dispose()


def _patch_sessions(monkeypatch, engine, *modules):
    """Point each service module's get_session at the test engine."""

    @asynccontextmanager
    async def fake_get_session():
        async with AsyncSession(engine) as session:
            yield session

    for mod in modules:
        monkeypatch.setattr(mod, "get_session", fake_get_session)


class _StubRPC:
    """async context manager replacing BlockchainRPCClient in island_service."""

    def __init__(self, reply: dict[str, Any]):
        self._reply = reply
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def join_island(self, *args, **kwargs):
        self.calls.append(("join", args))
        return self._reply

    async def leave_island(self, island_id):
        self.calls.append(("leave", (island_id,)))
        return self._reply

    async def request_bridge(self, target_island_id):
        self.calls.append(("bridge", (target_island_id,)))
        return self._reply

    async def list_islands(self):
        return self._reply

    async def get_island_info(self, island_id):
        return self._reply


def _patch_island_rpc(monkeypatch, reply: dict[str, Any]) -> _StubRPC:
    stub = _StubRPC(reply)
    monkeypatch.setattr(island_svc_mod, "BlockchainRPCClient", lambda **kw: stub)
    return stub


# ---------------------------------------------------------------------------
# BlockchainRPCClient / GPUServiceClient wire behaviour (MockTransport)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rpc_join_island_payload_and_headers():
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["api_key"] = request.headers.get("x-api-key")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"success": True, "status": "joined"})

    transport = httpx.MockTransport(handler)
    async with BlockchainRPCClient(api_key="k") as client:
        client.client = httpx.AsyncClient(transport=transport, headers=client.client.headers)
        result = await client.join_island("isl-1", "Island One", ["c1", "c2"], role="hub", is_hub=True)

    assert result["success"] is True
    assert seen["path"] == "/rpc/islands/join"
    assert seen["api_key"] == "k"
    assert seen["body"] == {
        "island_id": "isl-1",
        "island_name": "Island One",
        "chain_id": ["c1", "c2"],
        "role": "hub",
        "is_hub": True,
    }


@pytest.mark.asyncio
async def test_rpc_get_island_info_404_returns_none():
    transport = httpx.MockTransport(lambda request: httpx.Response(404, json={"error": "nope"}))
    async with BlockchainRPCClient() as client:
        client.client = httpx.AsyncClient(transport=transport)
        assert await client.get_island_info("missing") is None


@pytest.mark.asyncio
async def test_rpc_get_island_info_500_raises():
    transport = httpx.MockTransport(lambda request: httpx.Response(500, json={"error": "boom"}))
    async with BlockchainRPCClient() as client:
        client.client = httpx.AsyncClient(transport=transport)
        with pytest.raises(httpx.HTTPStatusError):
            await client.get_island_info("isl-1")


@pytest.mark.asyncio
async def test_gpu_client_get_profiles_builds_params():
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/profiles"):
            seen["query"] = dict(request.url.params)
        return httpx.Response(200, json=[{"id": "g1"}])

    async with GPUServiceClient() as client:
        client.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        profiles = await client.get_gpu_profiles(architecture="ampere", edge_optimized=True, min_memory_gb=8)
        metrics = await client.get_gpu_metrics("gpu-9", limit=5)
        gpus = await client.get_miner_gpus("miner-1")

    assert profiles == [{"id": "g1"}]
    assert seen["query"] == {"architecture": "ampere", "edge_optimized": "true", "min_memory_gb": "8"}
    assert metrics == [{"id": "g1"}]
    assert gpus == [{"id": "g1"}]


# ---------------------------------------------------------------------------
# IslandService
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_islands_non_list_payload_returns_empty(monkeypatch):
    _patch_island_rpc(monkeypatch, {"islands": "not-a-list"})
    assert await IslandService().list_islands() == []


@pytest.mark.asyncio
async def test_list_memberships_by_region_filters_extra_data(monkeypatch, engine):
    _patch_sessions(monkeypatch, engine, island_svc_mod)
    async with AsyncSession(engine) as session:
        session.add_all(
            [
                IslandMembership(
                    island_id="i1",
                    island_name="One",
                    chain_id="c",
                    status=IslandStatus.ACTIVE,
                    extra_data={"region": "eu"},
                ),
                IslandMembership(
                    island_id="i2",
                    island_name="Two",
                    chain_id="c",
                    status=IslandStatus.ACTIVE,
                    extra_data={"region": "us"},
                ),
                IslandMembership(
                    island_id="i3",
                    island_name="Three",
                    chain_id="c",
                    status=IslandStatus.ACTIVE,
                    extra_data={},
                ),
            ]
        )
        await session.commit()

    memberships = await IslandService().list_memberships_by_region("eu")
    assert [m.island_id for m in memberships] == ["i1"]


@pytest.mark.asyncio
async def test_join_island_maps_joined_status_to_active(monkeypatch, engine):
    """RPC 'joined' must persist as IslandStatus.ACTIVE (enum has no JOINED row use)."""
    _patch_sessions(monkeypatch, engine, island_svc_mod)
    _patch_island_rpc(monkeypatch, {"success": True, "status": "joined"})

    result = await IslandService().join_island("isl-9", "Nine", "chain-1")
    assert result["success"] is True

    async with AsyncSession(engine) as session:
        rows = (await session.execute(select(IslandMembership))).scalars().all()
    assert len(rows) == 1
    assert rows[0].status == IslandStatus.ACTIVE
    assert rows[0].island_id == "isl-9"


@pytest.mark.asyncio
async def test_join_island_unknown_status_falls_back_to_active(monkeypatch, engine):
    _patch_sessions(monkeypatch, engine, island_svc_mod)
    _patch_island_rpc(monkeypatch, {"success": True, "status": "some_future_state"})
    await IslandService().join_island("isl-x", "X", "chain-1")
    async with AsyncSession(engine) as session:
        row = (await session.execute(select(IslandMembership))).scalar_one()
    assert row.status == IslandStatus.ACTIVE


@pytest.mark.xfail(
    strict=True, reason="edge join_island persists list chain_id into str column -> 500 after successful chain join #1383"
)
@pytest.mark.asyncio
async def test_join_island_list_chain_id_does_not_500_after_chain_join(monkeypatch, engine):
    """#1383: JoinIslandRequest accepts ``chain_id: str | list[str]`` but
    IslandMembership.chain_id is a plain str — a list input joined the island
    on-chain and then crashed writing the local row."""
    _patch_sessions(monkeypatch, engine, island_svc_mod)
    stub = _patch_island_rpc(monkeypatch, {"success": True, "status": "active"})

    result = await IslandService().join_island("isl-list", "List", ["chain-a", "chain-b"])
    assert result["success"] is True

    async with AsyncSession(engine) as session:
        rows = (await session.execute(select(IslandMembership))).scalars().all()
    assert len(rows) == 1
    assert stub.calls[0][0] == "join"


@pytest.mark.xfail(
    strict=True, reason="edge request_bridge persists NULL source_island_id/request_id from unvalidated RPC reply #1382"
)
@pytest.mark.asyncio
async def test_request_bridge_records_bridge_request(monkeypatch, engine):
    """#1382: request_bridge never populates source_island_id and takes
    request_id unvalidated from the RPC reply, so bridge_requests rows are
    persisted with NULL columns that cannot be reconciled."""
    _patch_sessions(monkeypatch, engine, island_svc_mod)
    _patch_island_rpc(monkeypatch, {"success": True, "request_id": "brq-1", "status": "pending"})

    result = await IslandService().request_bridge("isl-target")
    assert result["success"] is True

    async with AsyncSession(engine) as session:
        rows = (await session.execute(select(BridgeRequest))).scalars().all()
    assert len(rows) == 1
    assert rows[0].request_id == "brq-1"
    assert rows[0].target_island_id == "isl-target"
    # #1382: source_island_id is never populated — the row is written with NULL.
    assert rows[0].source_island_id


@pytest.mark.asyncio
async def test_request_bridge_failed_reply_writes_nothing(monkeypatch, engine):
    _patch_sessions(monkeypatch, engine, island_svc_mod)
    _patch_island_rpc(monkeypatch, {"success": False, "message": "denied"})
    result = await IslandService().request_bridge("isl-target")
    assert result["success"] is False
    async with AsyncSession(engine) as session:
        assert (await session.execute(select(BridgeRequest))).scalars().all() == []


# ---------------------------------------------------------------------------
# DatabaseService
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def _seed_database(engine, database_id="db-1", island_id="isl-1", capacity_gb=100):
    async with AsyncSession(engine) as session:
        session.add(
            EdgeDatabase(
                database_id=database_id,
                island_id=island_id,
                capacity_gb=capacity_gb,
                used_gb=0,
                status="initialized",
                sync_status="idle",
                records_synced=0,
            )
        )
        await session.commit()


@pytest.mark.xfail(
    strict=True, reason="edge DatabaseService.init_database reads db.id after commit -> MissingGreenlet/500 on success #1390"
)
@pytest.mark.asyncio
async def test_init_database_success_does_not_500(monkeypatch, engine):
    """#1390: init_database commits the row then reads ``db.id`` — expired by
    commit — which raises MissingGreenlet under the async engine. The row is
    written but POST /v1/database/init returns 500."""
    _patch_sessions(monkeypatch, engine, db_svc_mod)
    result = await DatabaseService().init_database("db-new", "isl-1", 100)
    assert result["success"] is True
    assert result["id"]


@pytest.mark.asyncio
async def test_database_lifecycle(monkeypatch, engine):
    _patch_sessions(monkeypatch, engine, db_svc_mod)
    svc = DatabaseService()
    await _seed_database(engine)

    dup = await svc.init_database("db-1", "isl-1", 100)
    assert dup["success"] is False
    assert "already exists" in dup["message"]

    fetched = await svc.get_database("db-1")
    assert fetched is not None
    assert fetched["capacity_gb"] == 100
    assert fetched["status"] == "initialized"
    assert fetched["sync_status"] == "idle"

    listing = await svc.list_databases(island_id="isl-1")
    assert [d["database_id"] for d in listing] == ["db-1"]
    assert await svc.list_databases(island_id="other") == []

    assert await svc.delete_database("db-1") is True
    assert await svc.delete_database("db-1") is False
    assert await svc.get_database("db-1") is None


@pytest.mark.asyncio
async def test_sync_database_raises_not_implemented(monkeypatch, engine):
    """Default mode must refuse rather than fabricate sync state (#V23-17)."""
    _patch_sessions(monkeypatch, engine, db_svc_mod)
    monkeypatch.setattr(db_svc_mod, "ALLOW_SIMULATED_SYNC", False)
    svc = DatabaseService()
    await _seed_database(engine, database_id="db-2", capacity_gb=50)

    with pytest.raises(SyncNotImplementedError):
        await svc.sync_database("db-2")

    # Nothing was written: last_sync_at stays NULL, records_synced stays 0.
    fetched = await svc.get_database("db-2")
    assert fetched["last_sync_at"] is None
    assert fetched["records_synced"] == 0


@pytest.mark.asyncio
async def test_sync_database_missing_returns_not_found(monkeypatch, engine):
    _patch_sessions(monkeypatch, engine, db_svc_mod)
    svc = DatabaseService()
    result = await svc.sync_database("nope")
    assert result["success"] is False


@pytest.mark.asyncio
async def test_sync_database_simulated_mode_writes_nothing(monkeypatch, engine):
    _patch_sessions(monkeypatch, engine, db_svc_mod)
    monkeypatch.setattr(db_svc_mod, "ALLOW_SIMULATED_SYNC", True)
    svc = DatabaseService()
    await _seed_database(engine, database_id="db-3", capacity_gb=10)

    result = await svc.sync_database("db-3")
    assert result["success"] is True
    assert result["simulated"] is True
    assert "not implemented" in result["notice"].lower() or "not implemented" in result["notice"]

    fetched = await svc.get_database("db-3")
    assert fetched["last_sync_at"] is None
    assert fetched["records_synced"] == 0


# ---------------------------------------------------------------------------
# MetricsService
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_metrics_crud(monkeypatch, engine):
    _patch_sessions(monkeypatch, engine, metrics_svc_mod)
    svc = MetricsService()

    rec = await svc.record_metrics("gpu-1", {"util": 0.5})
    assert rec["success"] is True
    metric_id = rec["metric_id"]

    got = await svc.get_metrics(metric_id)
    assert got is not None
    assert got["gpu_id"] == "gpu-1"
    assert got["metrics_data"] == {"util": 0.5}

    listed = await svc.list_metrics(gpu_id="gpu-1")
    assert [m["metric_id"] for m in listed] == [metric_id]
    assert await svc.list_metrics(gpu_id="other") == []

    assert await svc.delete_metrics(metric_id) is True
    assert await svc.delete_metrics(metric_id) is False
    assert await svc.get_metrics(metric_id) is None


@pytest.mark.xfail(strict=True, reason="edge MetricsService.list_metrics ignores limit parameter -> unbounded query #1384")
@pytest.mark.asyncio
async def test_list_metrics_respects_limit(monkeypatch, engine):
    """#1384: list_metrics accepted ``limit`` but never applied it to the query."""
    _patch_sessions(monkeypatch, engine, metrics_svc_mod)
    svc = MetricsService()
    for i in range(3):
        await svc.record_metrics("gpu-lim", {"i": i})

    limited = await svc.list_metrics(gpu_id="gpu-lim", limit=1)
    assert len(limited) == 1


# ---------------------------------------------------------------------------
# GPUService (edge-side listing mirror)
# ---------------------------------------------------------------------------


class _StubGPUClient:
    """Stands in for GPUServiceClient; returns a fixed profile list."""

    profiles: list[dict[str, Any]] = []

    def __init__(self, *a, **kw):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get_gpu_profiles(self, *a, **kw):
        return list(self.profiles)


@pytest.mark.xfail(strict=True, reason="edge GPUService.list_gpus appends duplicate gpu_listings rows on every call #1385")
@pytest.mark.asyncio
async def test_list_gpus_does_not_duplicate_listing_rows(monkeypatch, engine):
    """#1385: every list_gpus call appended a fresh gpu_listings row per
    profile with no dedup — the table grew on every read."""
    _patch_sessions(monkeypatch, engine, gpu_svc_mod)
    _StubGPUClient.profiles = [
        {"id": "gpu-a", "model": "RTX 4090", "memory_gb": 24, "region": "eu", "capabilities": ["inference"]},
        {"id": "gpu-b", "model": "RTX 3060", "memory_gb": 12, "region": "us", "capabilities": []},
    ]
    monkeypatch.setattr(gpu_svc_mod, "GPUServiceClient", _StubGPUClient)

    svc = GPUService()
    first = await svc.list_gpus()
    second = await svc.list_gpus()
    assert first == second  # remote profiles are returned verbatim

    async with AsyncSession(engine) as session:
        rows = (await session.execute(select(GPUListing))).scalars().all()
    # Two upstream profiles must produce two rows total — not four.
    assert len(rows) == 2
    assert {r.gpu_id for r in rows} == {"gpu-a", "gpu-b"}


@pytest.mark.asyncio
async def test_get_gpu_listing_falls_back_to_db(monkeypatch, engine):
    _patch_sessions(monkeypatch, engine, gpu_svc_mod)

    class _FailingClient(_StubGPUClient):
        async def get_gpu_profiles(self, *a, **kw):
            raise httpx.ConnectError("gpu service down")

    monkeypatch.setattr(gpu_svc_mod, "GPUServiceClient", _FailingClient)

    async with AsyncSession(engine) as session:
        session.add(
            GPUListing(
                gpu_id="gpu-db",
                model="Stored Card",
                memory_gb=16,
                cuda_version="12.1",
                region="ap",
                capabilities=["edge"],
            )
        )
        await session.commit()

    got = await GPUService().get_gpu_listing("gpu-db")
    assert got is not None
    assert got["id"] == "gpu-db"
    assert got["model"] == "Stored Card"

    assert await GPUService().get_gpu_listing("missing") is None


@pytest.mark.asyncio
async def test_advertise_to_market_reports_failure_without_raising(monkeypatch):
    """Market advertise must degrade to a labelled failure, not an exception."""
    import httpx as _httpx

    class _FailingProfiles(_StubGPUClient):
        profiles = [{"model": "RTX", "memory_gb": 8}]

    async def _boom(*a, **kw):
        raise _httpx.ConnectError("market down")

    monkeypatch.setattr(gpu_svc_mod, "GPUServiceClient", _FailingProfiles)
    monkeypatch.setattr(_httpx.AsyncClient, "post", _boom)

    result = await GPUService().advertise_to_market()
    assert result["status"] == "failed"
    assert result["gpu_count"] == 1
    assert "error" in result


# ---------------------------------------------------------------------------
# ServeService — owner scoping and lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_serve_request_lifecycle_and_owner_scope(monkeypatch, engine):
    _patch_sessions(monkeypatch, engine, serve_svc_mod)
    svc = ServeService()

    submitted = await svc.submit_compute_request("gpu-1", "llama", {"prompt": "hi"}, owner_id="user-a")
    request_id = submitted["request_id"]
    assert submitted["status"] == "queued"

    # Owner sees their own request.
    own = await svc.get_compute_request(request_id, owner_id="user-a")
    assert own is not None and own["gpu_id"] == "gpu-1"

    # Other users and missing owners do not.
    assert await svc.get_compute_request(request_id, owner_id="user-b") is None
    assert await svc.get_compute_request(request_id, owner_id="") is None
    # Admin (owner_id=None) sees everything.
    assert await svc.get_compute_request(request_id) is not None

    listing = await svc.list_compute_requests(owner_id="user-a")
    assert [r["request_id"] for r in listing] == [request_id]
    assert await svc.list_compute_requests(owner_id="user-b") == []

    # Cannot cancel someone else's request.
    assert await svc.cancel_compute_request(request_id, owner_id="user-b") is False
    assert await svc.cancel_compute_request(request_id, owner_id="user-a") is True

    async with AsyncSession(engine) as session:
        row = (await session.execute(select(ComputeRequest).where(ComputeRequest.request_id == request_id))).scalar_one()
        assert row.status == "cancelled"
        assert row.completed_at is not None


@pytest.mark.asyncio
async def test_cancel_only_queued_or_running(monkeypatch, engine):
    _patch_sessions(monkeypatch, engine, serve_svc_mod)
    svc = ServeService()
    submitted = await svc.submit_compute_request("gpu-1", "m", {}, owner_id=None)
    rid = submitted["request_id"]

    async with AsyncSession(engine) as session:
        req = (await session.execute(select(ComputeRequest).where(ComputeRequest.request_id == rid))).scalar_one()
        req.status = "completed"
        await session.commit()

    # Completed requests cannot be cancelled.
    assert await svc.cancel_compute_request(rid) is False


@pytest.mark.asyncio
async def test_get_compute_result_requires_owner_match(monkeypatch, engine):
    _patch_sessions(monkeypatch, engine, serve_svc_mod)
    svc = ServeService()
    submitted = await svc.submit_compute_request("gpu-1", "m", {}, owner_id="owner-1")
    rid = submitted["request_id"]

    async with AsyncSession(engine) as session:
        session.add(
            ComputeResult(
                result_id="res_x",
                request_id=rid,
                island_id="default",
                gpu_id="gpu-1",
                output_data={"ok": True},
            )
        )
        await session.commit()

    assert await svc.get_compute_result(rid, owner_id="owner-1") is not None
    assert await svc.get_compute_result(rid, owner_id="intruder") is None
    assert await svc.get_compute_result(rid) is not None  # admin path


@pytest.mark.xfail(strict=True, reason="edge ComputeResult expires_at never enforced -> stale results served forever #1386")
@pytest.mark.asyncio
async def test_expired_compute_result_is_not_served(monkeypatch, engine):
    """#1386: ComputeResult.expires_at/cache_ttl are written by the worker but
    never enforced — get_compute_result serves stale results forever."""
    _patch_sessions(monkeypatch, engine, serve_svc_mod)
    svc = ServeService()
    submitted = await svc.submit_compute_request("gpu-1", "m", {}, owner_id=None)
    rid = submitted["request_id"]

    past = datetime.now(UTC) - timedelta(hours=2)
    async with AsyncSession(engine) as session:
        session.add(
            ComputeResult(
                result_id="res_old",
                request_id=rid,
                island_id="default",
                gpu_id="gpu-1",
                output_data={"stale": True},
                expires_at=past,
            )
        )
        await session.commit()

    result = await svc.get_compute_result(rid)
    assert result is None


# ---------------------------------------------------------------------------
# compute_worker helpers and queue processing
# ---------------------------------------------------------------------------


def test_extract_prompt_prefers_text_keys():
    assert _extract_prompt({"prompt": "p"}) == "p"
    assert _extract_prompt({"text": "t"}) == "t"
    assert _extract_prompt({"input": 42, "query": "q"}) == "q"
    assert _extract_prompt({}) == ""
    assert json.loads(_extract_prompt({"a": 1})) == {"a": 1}


def test_execute_stub_returns_deterministic_output():
    req = ComputeRequest(request_id="r1", gpu_id="gpu-1", model_name="llama", input_data={"prompt": "x"})
    output, metrics = _execute_stub(req)
    assert output["result"] == "ok"
    assert output["model"] == "llama"
    assert metrics["simulated"] is True


@pytest.mark.asyncio
async def test_execute_request_unknown_executor_falls_back_to_stub(monkeypatch):
    monkeypatch.setattr(worker_mod.settings, "edge_worker_executor", "bogus-executor")
    req = ComputeRequest(request_id="r2", gpu_id="gpu-1", model_name="m", input_data={})
    output, metrics, elapsed, success, error = await _execute_request(req)
    assert success is True
    assert error is None
    assert output["result"] == "ok"
    assert elapsed >= 0
    assert metrics["execution_time_seconds"] >= 0


@pytest.mark.asyncio
async def test_process_queued_requests_executes_and_stores(monkeypatch, engine):
    """End-to-end: queued row -> running -> completed + ComputeResult row."""
    _patch_sessions(monkeypatch, engine, worker_mod)
    monkeypatch.setattr(worker_mod.settings, "edge_worker_executor", "stub")

    async with AsyncSession(engine) as session:
        session.add(
            ComputeRequest(
                request_id="req-w1",
                gpu_id="gpu-w",
                model_name="stub-model",
                input_data={"prompt": "hello"},
                status="queued",
                owner_id="u1",
            )
        )
        await session.commit()

    processed = await process_queued_requests()
    assert processed == 1

    async with AsyncSession(engine) as session:
        req = (await session.execute(select(ComputeRequest).where(ComputeRequest.request_id == "req-w1"))).scalar_one()
        assert req.status == "completed"
        assert req.started_at is not None
        assert req.completed_at is not None

        result = (await session.execute(select(ComputeResult).where(ComputeResult.request_id == "req-w1"))).scalar_one()
        assert result.status == "completed"
        assert result.output_data["result"] == "ok"
        assert result.island_id == "default"
        # expires_at must be set in the future relative to creation.
        assert result.expires_at is not None


@pytest.mark.asyncio
async def test_process_queued_requests_skips_non_queued(monkeypatch, engine):
    _patch_sessions(monkeypatch, engine, worker_mod)
    async with AsyncSession(engine) as session:
        session.add(
            ComputeRequest(
                request_id="req-done",
                gpu_id="gpu-w",
                model_name="m",
                input_data={},
                status="completed",
            )
        )
        await session.commit()
    # Nothing queued -> nothing processed.
    assert await process_queued_requests() == 0


# ---------------------------------------------------------------------------
# edge_app: compliance subnets and TEE proxy
# ---------------------------------------------------------------------------


def test_compliance_subnet_assign_release():
    from aitbc.compliance.policies import ComplianceFramework, DataClassification
    from edge_app.compliance_subnets import ComplianceSubnet, SubnetRegistry, WorkloadStatus

    subnet = ComplianceSubnet(
        subnet_id="s1",
        allowed_frameworks={ComplianceFramework.HIPAA},
        allowed_classifications={DataClassification.CONFIDENTIAL},
    )
    rec = subnet.assign("w1", ComplianceFramework.HIPAA, DataClassification.CONFIDENTIAL)
    assert rec["status"] == WorkloadStatus.ISOLATED.value
    assert subnet.is_isolated("w1")

    subnet.release("w1")
    assert not subnet.is_isolated("w1")

    registry = SubnetRegistry()
    registry.register(subnet)
    assert registry.is_isolated("s1", "w1") is False
    registry.assign("w2", ComplianceFramework.HIPAA, "confidential", "s1")
    assert registry.is_isolated("s1", "w2") is True

    from aitbc.compliance.errors import PolicyViolationError

    with pytest.raises(PolicyViolationError):
        subnet.assign("w3", ComplianceFramework.SOC2, DataClassification.CONFIDENTIAL)
    with pytest.raises(ValueError):
        registry.assign("w4", ComplianceFramework.HIPAA, DataClassification.CONFIDENTIAL, "missing")


def test_tee_proxy_channel_roundtrip():
    """register -> open -> route -> receive must round-trip a payload."""
    import os

    from edge_app.tee_proxy import TEEProxy, _generate_x25519_keypair

    _, peer_pub = _generate_x25519_keypair()

    proxy = TEEProxy(edge_id="edge-1")
    reg = proxy.register_channel("ch-1", peer_id="peer-1", peer_public_key=peer_pub)
    assert reg["peer_id"] == "peer-1"
    assert len(reg["edge_public_key"]) == 32

    opened = proxy.open_channel("ch-1")
    assert opened["state"] == "open"

    routed = proxy.route_to_channel("ch-1", {"hello": "world"})
    assert routed["delivered"] is True
    assert routed["sequence"] == 0

    decoded = proxy.receive_from_channel("ch-1", routed["payload"], routed["nonce"])
    assert decoded == {"hello": "world"}

    # Unknown channel and unopened channel are refused.
    with pytest.raises(KeyError):
        proxy.route_to_channel("nope", {})

    proxy2 = TEEProxy(edge_id="edge-2")
    proxy2.register_channel("ch-2", peer_id="peer-2")
    with pytest.raises(ValueError):
        proxy2.open_channel("ch-2")  # no peer key yet
    proxy2.open_channel("ch-2", peer_public_key=os.urandom(32))

    # A registered-but-never-opened channel refuses routing.
    proxy3 = TEEProxy(edge_id="edge-3")
    _, pk3 = _generate_x25519_keypair()
    proxy3.register_channel("ch-3", peer_id="peer-3", peer_public_key=pk3)
    with pytest.raises(RuntimeError):
        proxy3.route_to_channel("ch-3", {"x": 1})
