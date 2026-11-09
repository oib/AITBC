"""#1388: miner heartbeat/register must not overwrite committed GPU status.

Before the fix, POST /v1/miners/heartbeat and POST /v1/miners/register set
every GPURegistry row for the miner to status="online" — an off-vocabulary
spelling that also flipped booked/in_use GPUs back to bookable, enabling
double-booking. Liveness may now only mark uncommitted GPUs (available,
offline, legacy "online") as the canonical "available"; committed states
(booked, in_use) and unknown values are left untouched.

The same clobber existed on the two remaining liveness paths —
POST /v1/gpu/register re-registration and EdgeGPUService
.discover_and_register_edge_gpus (POST /v1/market/edge-gpu/scan/{miner})
unconditionally reset status to "available". Both now apply the same
BOOKABLE_GPU_STATUSES filter.
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import gpu_service.main as main  # noqa: E402
from gpu_service.domain.gpu_market import GPURegistry  # noqa: E402
from gpu_service.main import app  # noqa: E402
from gpu_service.storage import get_session  # noqa: E402

_STATUSES = ("available", "offline", "online", "booked", "in_use", "bogus")


async def _seed_miner_gpus(miner_id: str) -> dict[str, str]:
    """Insert one GPU per status for the miner; return {gpu_id: status}."""
    rows: dict[str, str] = {}
    async with get_session() as session:
        for status in _STATUSES:
            gpu_id = f"gpu_{miner_id}_{status}_{uuid.uuid4().hex[:6]}"
            session.add(GPURegistry(id=gpu_id, miner_id=miner_id, model="TestGPU", status=status))
            rows[gpu_id] = status
        await session.commit()
    return rows


async def _statuses(gpu_ids: list[str]) -> dict[str, str]:
    async with get_session() as session:
        result = await session.execute(select(GPURegistry).where(GPURegistry.id.in_(gpu_ids)))
        return {gpu.id: gpu.status for gpu in result.scalars().all()}


@pytest.fixture
def client():
    app.dependency_overrides[main.require_gpu_api_key] = lambda: {"role": "gpu_admin"}
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _assert_liveness_semantics(before: dict[str, str], after: dict[str, str]) -> None:
    """Uncommitted GPUs become canonical 'available'; committed/unknown survive."""
    for gpu_id, old in before.items():
        if old in ("available", "offline", "online"):
            assert after[gpu_id] == "available", f"{gpu_id}: {old} -> {after[gpu_id]}"
        else:
            assert after[gpu_id] == old, f"{gpu_id}: committed status {old} was overwritten to {after[gpu_id]}"


def test_heartbeat_preserves_committed_status(client) -> None:
    miner_id = f"miner_hb_{uuid.uuid4().hex[:8]}"
    rows = asyncio.run(_seed_miner_gpus(miner_id))
    resp = client.post("/v1/miners/heartbeat", json={"miner_id": miner_id})
    assert resp.status_code == 200, resp.text
    after = asyncio.run(_statuses(list(rows)))
    _assert_liveness_semantics(rows, after)


async def _seed_uuid_gpus(miner_id: str) -> dict[str, str]:
    """Insert one GPU per status, each with a distinct hardware_uuid."""
    rows: dict[str, str] = {}
    async with get_session() as session:
        for status in _STATUSES:
            gpu_id = f"gpu_{miner_id}_{status}_{uuid.uuid4().hex[:6]}"
            hw_uuid = f"GPU-UUID-{miner_id}-{status}"
            session.add(
                GPURegistry(
                    id=gpu_id,
                    miner_id=miner_id,
                    model="TestGPU",
                    status=status,
                    hardware_uuid=hw_uuid,
                )
            )
            rows[hw_uuid] = status
        await session.commit()
    return rows


async def _status_by_uuid(hw_uuid: str) -> str | None:
    async with get_session() as session:
        result = await session.execute(select(GPURegistry).where(GPURegistry.hardware_uuid == hw_uuid))
        gpu = result.scalar_one_or_none()
        return None if gpu is None else gpu.status


def test_gpu_register_preserves_committed_status(client) -> None:
    """POST /v1/gpu/register re-registration must not un-commit booked/in_use."""
    miner_id = f"miner_gpreg_{uuid.uuid4().hex[:8]}"
    rows = asyncio.run(_seed_uuid_gpus(miner_id))
    for hw_uuid, old in rows.items():
        resp = client.post(
            "/v1/gpu/register",
            json={
                "miner_id": miner_id,
                "specs": {"uuid": hw_uuid, "model": "TestGPU", "memory_gb": 8},
            },
        )
        assert resp.status_code == 200, resp.text
        after = asyncio.run(_status_by_uuid(hw_uuid))
        if old in ("available", "offline", "online"):
            assert after == "available", f"{hw_uuid}: {old} -> {after}"
        else:
            assert after == old, f"{hw_uuid}: committed status {old} was overwritten to {after}"


def test_edge_scan_preserves_committed_status(client, monkeypatch) -> None:
    """EdgeGPUService rediscovery must not un-commit booked/in_use GPUs."""
    from gpu_service.services.edge_gpu_service import EdgeGPUService

    miner_id = f"miner_edge_{uuid.uuid4().hex[:8]}"
    rows = asyncio.run(_seed_uuid_gpus(miner_id))
    discovered = [
        {
            "index": i,
            "name": "TestGPU",
            "memory_mb": 8192,
            "driver_version": "550.1",
            "uuid": hw_uuid,
        }
        for i, hw_uuid in enumerate(rows)
    ]
    monkeypatch.setattr(
        EdgeGPUService,
        "_discover_gpus_via_nvidia_smi",
        lambda self: discovered,
    )
    resp = client.post(f"/v1/market/edge-gpu/scan/{miner_id}")
    assert resp.status_code == 200, resp.text
    for hw_uuid, old in rows.items():
        after = asyncio.run(_status_by_uuid(hw_uuid))
        if old in ("available", "offline", "online"):
            assert after == "available", f"{hw_uuid}: {old} -> {after}"
        else:
            assert after == old, f"{hw_uuid}: committed status {old} was overwritten to {after}"


def test_miner_register_preserves_committed_status(client) -> None:
    miner_id = f"miner_reg_{uuid.uuid4().hex[:8]}"
    rows = asyncio.run(_seed_miner_gpus(miner_id))
    resp = client.post("/v1/miners/register", json={"miner_id": miner_id})
    assert resp.status_code == 200, resp.text
    assert resp.json()["gpu_count"] == len(_STATUSES)
    after = asyncio.run(_statuses(list(rows)))
    _assert_liveness_semantics(rows, after)
