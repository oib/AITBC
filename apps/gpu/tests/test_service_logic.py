"""Branch coverage for gpu service logic: job queue, profiles, endpoints,
TEE runner/enclaves and the capacity publisher.

Deterministic only: Redis is faked at ``_redis``, HTTP boundaries are faked
with ``urllib.request.urlopen``/``httpx`` monkeypatches, and endpoint tests
override the API-key dependency. The DB is the throwaway sqlite file the
repo-root conftest points ``AITBC_DATA_DIR`` at (see tests/conftest.py).
"""

from __future__ import annotations

import io
import json
import urllib.error
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from gpu_service.domain.gpu_market import (
    CONSUMER_GPU_PROFILES,
    GPUArchitecture,
    GPUJobStatus,
    GPURegistry,
)
from gpu_service.services import edge_gpu_service as egs_mod
from gpu_service.services.edge_gpu_service import EdgeGPUService
from gpu_service.storage import DATABASE_URL, engine


def _db_path() -> str:
    assert DATABASE_URL.startswith("sqlite+aiosqlite:///")
    return DATABASE_URL.replace("sqlite+aiosqlite:///", "", 1)


class _FakeRedis:
    """In-memory stand-in for the Redis sorted-set queue."""

    def __init__(self) -> None:
        self.sets: dict[str, dict[str, float]] = {}

    async def zadd(self, key, mapping):
        self.sets.setdefault(key, {}).update(mapping)

    async def zpopmin(self, key, count=1):
        members = self.sets.get(key, {})
        if not members:
            return []
        # Lowest score first; ties broken lexicographically like Redis.
        ordered = sorted(members.items(), key=lambda kv: (kv[1], kv[0]))[:count]
        for member, _score in ordered:
            del members[member]
        return [(m, s) for m, s in ordered]

    async def delete(self, key):
        self.sets.pop(key, None)

    async def aclose(self):
        return None


@pytest.fixture
def fake_redis(monkeypatch) -> _FakeRedis:
    fake = _FakeRedis()
    monkeypatch.setattr(egs_mod, "_redis", lambda: fake)
    return fake


# ---------------------------------------------------------------------------
# Consumer GPU profiles
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_seed_and_list_profiles_with_filters():
    async with AsyncSession(engine, expire_on_commit=False) as session:
        svc = EdgeGPUService(session)
        profiles = await svc.list_profiles()
        assert len(profiles) >= len(CONSUMER_GPU_PROFILES)
        # Idempotent: a second call must not duplicate rows.
        again = await svc.list_profiles()
        assert len(again) == len(profiles)

        ampere = await svc.list_profiles(architecture=GPUArchitecture.AMPERE)
        assert ampere
        assert all(p.architecture == GPUArchitecture.AMPERE for p in ampere)

        big = await svc.list_profiles(min_memory_gb=10)
        assert all((p.memory_gb or 0) >= 10 for p in big)

        none = await svc.list_profiles(architecture=GPUArchitecture.VOLTA)
        assert none == []


def test_consumer_profiles_have_decimal_prices():
    for key, profile in CONSUMER_GPU_PROFILES.items():
        assert isinstance(profile["market_price_usd"], Decimal), key
        assert profile["market_price_usd"] > 0


# ---------------------------------------------------------------------------
# GPU job queue
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_queue_list_and_pop_priority_order(fake_redis):
    gpu_id = "gpu-q-priority"
    async with AsyncSession(engine, expire_on_commit=False) as session:
        svc = EdgeGPUService(session)

        low = await svc.queue_job(gpu_id, "client", 1, {"n": "low"})
        high = await svc.queue_job(gpu_id, "client", 10, {"n": "high"})

        queued = await svc.list_queued_jobs(gpu_id, status="queued")
        assert {j.id for j in queued} == {low.id, high.id}

        first = await svc.get_next_queued_job(gpu_id)
        assert first is not None and first.id == high.id
        assert first.status == GPUJobStatus.RUNNING

        second = await svc.get_next_queued_job(gpu_id)
        assert second is not None and second.id == low.id

        empty = await svc.get_next_queued_job(gpu_id)
        assert empty is None

        # Redis mirror was populated and drained.
        assert fake_redis.sets.get(f"aitbc:gpu:queue:{gpu_id}", {}) == {}


@pytest.mark.asyncio
async def test_get_next_queued_job_falls_back_to_db(fake_redis):
    """With an empty Redis queue the DB SELECT ... FOR UPDATE path serves."""
    gpu_id = "gpu-q-fallback"
    async with AsyncSession(engine, expire_on_commit=False) as session:
        svc = EdgeGPUService(session)
        # queue_job mirrors to Redis; pop it so only the DB row remains queued.
        job = await svc.queue_job(gpu_id, "client", 5, {})
        fake_redis.sets.clear()

        popped = await svc.get_next_queued_job(gpu_id)
        assert popped is not None and popped.id == job.id
        assert popped.status == GPUJobStatus.RUNNING


@pytest.mark.asyncio
async def test_list_queued_jobs_filters_by_status(fake_redis):
    gpu_id = "gpu-q-filter"
    async with AsyncSession(engine, expire_on_commit=False) as session:
        svc = EdgeGPUService(session)
        await svc.queue_job(gpu_id, "c", 1, {})
        await svc.get_next_queued_job(gpu_id)  # -> RUNNING
        await svc.queue_job(gpu_id, "c", 2, {})

        running = await svc.list_queued_jobs(gpu_id, status="running")
        assert len(running) == 1
        queued = await svc.list_queued_jobs(gpu_id, status="queued")
        assert len(queued) == 1
        all_jobs = await svc.list_queued_jobs(gpu_id)
        assert len(all_jobs) == 2


@pytest.mark.asyncio
async def test_complete_job_marks_running_job_completed(fake_redis):
    gpu_id = "gpu-q-complete"
    async with AsyncSession(engine, expire_on_commit=False) as session:
        svc = EdgeGPUService(session)
        await svc.queue_job(gpu_id, "c", 1, {})
        running = await svc.get_next_queued_job(gpu_id)
        assert running is not None

        done = await svc.complete_job(running.id)
        assert done is not None
        assert done.status == GPUJobStatus.COMPLETED
        assert done.completed_at is not None

        missing = await svc.complete_job("jobq_nonexistent")
        assert missing is None


@pytest.mark.xfail(
    strict=True,
    reason="gpu complete_job completes QUEUED jobs without running them — no status guard #1387",
)
@pytest.mark.asyncio
async def test_complete_job_refuses_queued_job(fake_redis):
    """#1387: complete_job must only transition RUNNING -> COMPLETED; today it
    marks a still-QUEUED job COMPLETED, skipping execution entirely."""
    gpu_id = "gpu-q-guard"
    async with AsyncSession(engine, expire_on_commit=False) as session:
        svc = EdgeGPUService(session)
        job = await svc.queue_job(gpu_id, "c", 1, {})
        assert job.status == GPUJobStatus.QUEUED

        result = await svc.complete_job(job.id)
        assert result is None  # must refuse: the job never ran


# ---------------------------------------------------------------------------
# nvidia-smi discovery parsing (subprocess faked)
# ---------------------------------------------------------------------------


def test_discover_gpus_parses_nvidia_smi(monkeypatch):
    class _Result:
        returncode = 0
        stdout = "0, NVIDIA RTX 4090, 24564, 550.54.15, GPU-aaa\n1, NVIDIA RTX 3060, 12288, 550.54.15, GPU-bbb\n"
        stderr = ""

    monkeypatch.setattr(egs_mod.subprocess, "run", lambda *a, **kw: _Result())
    svc = EdgeGPUService(session=None)  # type: ignore[arg-type]
    gpus = svc._discover_gpus_via_nvidia_smi()
    assert len(gpus) == 2
    assert gpus[0]["name"] == "NVIDIA RTX 4090"
    assert gpus[0]["memory_mb"] == 24564
    assert gpus[0]["uuid"] == "GPU-aaa"
    assert gpus[1]["index"] == 1


def test_discover_gpus_handles_missing_binary(monkeypatch):
    def _raise(*a, **kw):
        raise FileNotFoundError("nvidia-smi")

    monkeypatch.setattr(egs_mod.subprocess, "run", _raise)
    svc = EdgeGPUService(session=None)  # type: ignore[arg-type]
    assert svc._discover_gpus_via_nvidia_smi() == []


@pytest.mark.asyncio
async def test_discover_and_register_uses_db_fallback(monkeypatch):
    """No nvidia-smi -> returns the miner's existing registry rows."""
    monkeypatch.setattr(EdgeGPUService, "_discover_gpus_via_nvidia_smi", lambda self: [])
    gpu_id = "gpu-fb-1"
    async with AsyncSession(engine, expire_on_commit=False) as session:
        session.add(
            GPURegistry(
                id=gpu_id,
                miner_id="miner-fb",
                model="Fallback Card",
                memory_gb=8,
                status="available",
            )
        )
        await session.commit()

        svc = EdgeGPUService(session)
        result = await svc.discover_and_register_edge_gpus("miner-fb")
        assert result["discovery_method"] == "database_fallback"
        assert result["gpus"][0]["id"] == gpu_id
        assert result["registered"] == 1


@pytest.mark.asyncio
async def test_discover_and_register_dedups_by_hardware_uuid(monkeypatch):
    """Same physical uuid scanned twice must update, not duplicate."""
    fake_smi = [
        {"index": 0, "name": "Card A", "memory_mb": 8192, "driver_version": "1.0", "uuid": "GPU-dup"},
    ]
    monkeypatch.setattr(EdgeGPUService, "_discover_gpus_via_nvidia_smi", lambda self: fake_smi)
    async with AsyncSession(engine, expire_on_commit=False) as session:
        svc = EdgeGPUService(session)
        first = await svc.discover_and_register_edge_gpus("miner-dup")
        second = await svc.discover_and_register_edge_gpus("miner-dup")
        assert first["registered"] == 1
        assert second["registered"] == 0  # updated in place

        from sqlmodel import select

        rows = (await session.execute(select(GPURegistry).where(GPURegistry.hardware_uuid == "GPU-dup"))).scalars().all()
        assert len(rows) == 1


# ---------------------------------------------------------------------------
# HTTP endpoints (TestClient + API-key dependency override)
# ---------------------------------------------------------------------------


@pytest.fixture
def api_client(monkeypatch):
    from gpu_service import main as main_mod

    app = main_mod.app
    app.dependency_overrides[main_mod.require_gpu_api_key] = lambda: {
        "sub": "test-key",
        "role": "gpu_admin",
        "auth_type": "api_key",
    }
    yield TestClient(app)
    app.dependency_overrides.clear()


def _insert_gpu(status: str, miner_id: str, gpu_id: str) -> None:
    """Insert a GPURegistry row via a sync session on the same sqlite file."""
    from datetime import UTC, datetime

    from sqlalchemy import create_engine
    from sqlmodel import Session

    sync_engine = create_engine(f"sqlite:///{_db_path()}")
    with Session(sync_engine) as session:
        session.add(
            GPURegistry(
                id=gpu_id,
                miner_id=miner_id,
                model="HB Card",
                memory_gb=8,
                cuda_version="12.0",
                region="test",
                price_per_hour=Decimal("1.00000000"),
                status=status,
                chain_id="ait-hub",
                capabilities=["inference"],
                created_at=datetime.now(UTC),
            )
        )
        session.commit()
    sync_engine.dispose()


@pytest.mark.xfail(
    strict=True,
    reason="gpu miner heartbeat/register overwrite booked/in_use status with off-vocabulary 'online' #1388",
)
def test_heartbeat_preserves_booked_status(api_client):
    """#1388: a routine heartbeat must not flip a BOOKED gpu back to bookable."""
    _insert_gpu(status="booked", miner_id="miner-hb", gpu_id="gpu-hb-1")
    resp = api_client.post("/v1/miners/heartbeat", json={"miner_id": "miner-hb"})
    assert resp.status_code == 200

    got = api_client.get("/v1/gpu/gpu-hb-1")
    assert got.status_code == 200
    assert got.json()["status"] == "booked"


def test_heartbeat_marks_offline_available(api_client):
    """Heartbeat on an offline gpu is allowed to bring it back."""
    _insert_gpu(status="offline", miner_id="miner-hb2", gpu_id="gpu-hb-2")
    resp = api_client.post("/v1/miners/heartbeat", json={"miner_id": "miner-hb2"})
    assert resp.status_code == 200
    got = api_client.get("/v1/gpu/gpu-hb-2")
    # Current behaviour writes 'online'; canonical vocabulary is 'available'.
    # This test pins the *reachable* state, not the preferred spelling.
    assert got.json()["status"] in {"online", "available"}


@pytest.mark.xfail(
    strict=True,
    reason="gpu offer path persists caller-controlled status/price bypassing OfferFSM validation #1389",
)
def test_offer_rejects_invalid_status(api_client, monkeypatch):
    """#1389: PUT /v1/gpu/{id} validates status via OfferFSM; the offer path
    writes transaction_data['status'] verbatim, so 'bogus_status' is stored."""
    from gpu_service import main as main_mod

    async def _transport_fail(self, *a, **kw):
        import httpx

        raise httpx.ConnectError("no chain")

    monkeypatch.setattr(main_mod._rpc_client, "submit_transaction", _transport_fail)

    resp = api_client.post(
        "/v1/transactions",
        json={
            "type": "gpu_market",
            "action": "offer",
            "offer_id": "gpu-bogus-1",
            "status": "bogus_status",
            "tx": {
                "from": "0xabc",
                "chain_id": "ait-hub",
                "payload": {"gpu_id": "gpu-bogus-1", "miner_id": "miner-bogus", "model": "M", "price_per_hour": "1.0"},
            },
        },
    )
    assert resp.status_code == 400


def test_offer_falls_back_to_local_on_transport_failure(api_client, monkeypatch):
    """Transport failure (not admission refusal) still writes the local row."""
    from gpu_service import main as main_mod

    async def _transport_fail(self, *a, **kw):
        import httpx

        raise httpx.ConnectError("no chain")

    monkeypatch.setattr(main_mod._rpc_client, "submit_transaction", _transport_fail)

    resp = api_client.post(
        "/v1/transactions",
        json={
            "type": "gpu_market",
            "action": "offer",
            "offer_id": "gpu-local-1",
            "status": "available",
            "tx": {
                "from": "0xabc",
                "chain_id": "ait-hub",
                "payload": {"gpu_id": "gpu-local-1", "miner_id": "miner-local", "model": "M"},
            },
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["blockchain_registered"] is False

    got = api_client.get("/v1/gpu/gpu-local-1")
    assert got.status_code == 200
    assert got.json()["miner_id"] == "miner-local"


def test_offer_rejects_wrong_transaction_type(api_client):
    resp = api_client.post("/v1/transactions", json={"type": "other", "action": "offer"})
    assert resp.status_code == 400


def test_offer_rejects_unsupported_action(api_client):
    resp = api_client.post("/v1/transactions", json={"type": "gpu_market", "action": "book"})
    assert resp.status_code == 400


def test_offer_requires_signed_tx(api_client):
    resp = api_client.post(
        "/v1/transactions",
        json={"type": "gpu_market", "action": "offer", "tx": "not-a-dict"},
    )
    assert resp.status_code == 400
    assert "signed transaction required" in resp.json()["error"]


# ---------------------------------------------------------------------------
# gpu_app: TEE runner, compliance enclaves, capacity publisher
# ---------------------------------------------------------------------------


def test_run_tee_task_completes_and_reports(monkeypatch):
    from gpu_app.tee_runner import TEEExecutionStatus, run_tee_task

    sent: list[dict[str, Any]] = []

    class _Resp:
        def read(self):
            return b"{}"

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def _fake_urlopen(request, timeout=0):
        sent.append(json.loads(request.data.decode()))
        return _Resp()

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)

    task = run_tee_task("t1", "agent-1", {"x": 1}, coordinator_url="http://coord:8000", api_key="k")
    assert task.status == TEEExecutionStatus.COMPLETED
    assert task.result["executed"] is True
    assert any("enclave initialized" in line for line in task.logs)
    assert sent and sent[0]["task_id"] == "t1"
    assert sent[0]["status"] == "completed"


def test_submit_tee_task_logs_url_error(monkeypatch):
    from gpu_app.tee_runner import TEETask, TEEExecutionStatus, submit_tee_task

    def _boom(request, timeout=0):
        raise urllib.error.URLError("refused")

    monkeypatch.setattr("urllib.request.urlopen", _boom)
    task = TEETask(task_id="t2", agent_id="a", payload={}, status=TEEExecutionStatus.RUNNING)
    submit_tee_task(task, coordinator_url="http://127.0.0.1:9")
    assert any("coordinator submission failed" in line for line in task.logs)


def test_compliance_gpu_enclave_lifecycle():
    from aitbc.compliance.errors import PolicyViolationError
    from aitbc.compliance.policies import ComplianceFramework, DataClassification
    from gpu_app.compliance_enclaves import ComplianceGPUEnclave, GPUEnclaveStatus

    enclave = ComplianceGPUEnclave(
        enclave_id="enc-1",
        policy_framework=ComplianceFramework.HIPAA,
        allowed_classifications={DataClassification.PHI},
    )
    assert enclave.status == GPUEnclaveStatus.PENDING

    # Cannot run before attestation.
    with pytest.raises(PolicyViolationError):
        enclave.run("w1", DataClassification.PHI, {})

    enclave.attest("measurement-1")
    assert enclave.attested is True
    assert enclave.status == GPUEnclaveStatus.ATTESTED

    out = enclave.run("w1", DataClassification.PHI, {"data": 1})
    assert out["workload_id"] == "w1"
    assert out["attested"] is True
    assert enclave.status == GPUEnclaveStatus.RUNNING

    # Wrong classification refused even when attested.
    with pytest.raises(PolicyViolationError):
        enclave.run("w2", DataClassification.PUBLIC, {})

    enclave.stop()
    assert enclave.status == GPUEnclaveStatus.STOPPED


def test_compliance_gpu_enclave_empty_allowlist_accepts_all():
    from gpu_app.compliance_enclaves import ComplianceGPUEnclave

    enclave = ComplianceGPUEnclave(enclave_id="enc-2")
    assert enclave.allows("public")
    with pytest.raises(ValueError):
        ComplianceGPUEnclave(enclave_id="")


def test_publish_capacity_success(monkeypatch):
    from gpu_app.capacity_publisher import publish_capacity

    seen: dict[str, Any] = {}

    class _Resp:
        def read(self):
            return b'{"ok": true}'

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def _fake_urlopen(request, timeout=0):
        seen["url"] = request.full_url
        seen["body"] = json.loads(request.data.decode())
        seen["api_key"] = request.headers.get("X-api-key")
        return _Resp()

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    result = publish_capacity(
        "prov-1",
        4,
        coordinator_url="http://coord:8203/",
        price_per_hour=Decimal("0.5"),
        api_key="secret",
    )
    assert result == {"ok": True}
    assert seen["url"] == "http://coord:8203/v1/market/providers/prov-1/capacity"
    assert seen["body"]["capacity"] == 4
    assert seen["body"]["price_per_hour"] == "0.5"
    assert seen["api_key"] == "secret"


def test_publish_capacity_http_error_returns_error_dict(monkeypatch):
    from gpu_app.capacity_publisher import publish_capacity

    def _boom(request, timeout=0):
        raise urllib.error.HTTPError(request.full_url, 500, "err", {}, io.BytesIO(b"server error"))

    monkeypatch.setattr("urllib.request.urlopen", _boom)
    result = publish_capacity("prov-1", 1, coordinator_url="http://coord:8203")
    assert result["status"] == 500
    assert "error" in result


def test_publish_capacity_url_error_returns_503(monkeypatch):
    from gpu_app.capacity_publisher import publish_capacity

    def _boom(request, timeout=0):
        raise urllib.error.URLError("no route")

    monkeypatch.setattr("urllib.request.urlopen", _boom)
    result = publish_capacity("prov-1", 1, coordinator_url="http://coord:8203")
    assert result["status"] == 503
