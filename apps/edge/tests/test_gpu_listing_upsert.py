"""#1385: GPUService.list_gpus must upsert gpu_listings, not append duplicates.

Every ``GET /v1/gpu/`` call used to ``session.add(GPUListing(...))`` for each
remote profile unconditionally — the mirror table grew by one full copy of
the catalog per read. The remote profile list is the source of truth, so the
mirror now upserts by gpu_id.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlmodel import SQLModel, select

import aitbc_edge.services.gpu_service as svc_mod
from aitbc_edge.schemas.gpu import GPUListing
from aitbc_edge.services.gpu_service import GPUService


class _FakeGPUServiceClient:
    """Stand-in for GPUServiceClient returning canned profiles."""

    profiles: list[dict[str, Any]] = []

    def __init__(self) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get_gpu_profiles(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        return list(self.profiles)


@pytest.fixture
async def seeded_session(monkeypatch, tmp_path):
    """In-memory sqlite session factory patched into the service."""
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/edge.db")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    @asynccontextmanager
    async def fake_get_session():
        async with AsyncSession(engine) as session:
            yield session

    monkeypatch.setattr(svc_mod, "get_session", fake_get_session)

    def set_profiles(profiles: list[dict[str, Any]]) -> None:
        _FakeGPUServiceClient.profiles = profiles

    monkeypatch.setattr(svc_mod, "GPUServiceClient", _FakeGPUServiceClient)
    set_profiles([])

    yield engine, set_profiles
    await engine.dispose()


async def _listings(engine) -> list[GPUListing]:
    async with AsyncSession(engine) as session:
        result = await session.execute(select(GPUListing))
        return list(result.scalars().all())


PROFILES = [
    {
        "id": "gpu-1",
        "model": "RTX 4090",
        "memory_gb": 24,
        "cuda_version": "12.4",
        "region": "us-east",
        "capabilities": ["inference"],
        "price_per_hour": "0.50",
    },
    {
        "id": "gpu-2",
        "model": "A100",
        "memory_gb": None,
        "cuda_version": "12.1",
        "region": "eu-west",
        "capabilities": [],
    },
]


@pytest.mark.asyncio
async def test_repeated_calls_do_not_duplicate_rows(seeded_session):
    engine, set_profiles = seeded_session
    set_profiles(PROFILES)
    service = GPUService()

    await service.list_gpus()
    await service.list_gpus()
    await service.list_gpus()

    listings = await _listings(engine)
    assert len(listings) == 2
    assert {g.gpu_id for g in listings} == {"gpu-1", "gpu-2"}


@pytest.mark.asyncio
async def test_second_call_updates_existing_row(seeded_session):
    engine, set_profiles = seeded_session
    service = GPUService()

    set_profiles(PROFILES)
    await service.list_gpus()

    updated = [dict(PROFILES[0], model="RTX 4090 Ti", memory_gb=48), PROFILES[1]]
    set_profiles(updated)
    await service.list_gpus()

    listings = {g.gpu_id: g for g in await _listings(engine)}
    assert len(listings) == 2
    assert listings["gpu-1"].model == "RTX 4090 Ti"
    assert listings["gpu-1"].memory_gb == 48
    # gpu-2 untouched by the update path beyond a refresh
    assert listings["gpu-2"].model == "A100"


@pytest.mark.asyncio
async def test_null_memory_gb_stays_null(seeded_session):
    """A profile with memory_gb: null must not be coerced to 0."""
    engine, set_profiles = seeded_session
    set_profiles(PROFILES)
    await GPUService().list_gpus()

    listings = {g.gpu_id: g for g in await _listings(engine)}
    assert listings["gpu-2"].memory_gb is None
    assert listings["gpu-1"].memory_gb == 24


@pytest.mark.asyncio
async def test_price_is_mirrored_from_profile(seeded_session):
    engine, set_profiles = seeded_session
    set_profiles(PROFILES)
    await GPUService().list_gpus()

    listings = {g.gpu_id: g for g in await _listings(engine)}
    assert listings["gpu-1"].price_per_hour == Decimal("0.50")
    assert listings["gpu-2"].price_per_hour == 0


@pytest.mark.asyncio
async def test_profile_without_id_is_not_mirrored(seeded_session):
    """No stable key -> no row; it could never be upserted or found anyway."""
    engine, set_profiles = seeded_session
    set_profiles([{"model": "Mystery GPU"}, PROFILES[0]])
    result = await GPUService().list_gpus()

    assert len(result) == 2  # remote list is returned verbatim
    listings = await _listings(engine)
    assert [g.gpu_id for g in listings] == ["gpu-1"]


@pytest.mark.asyncio
async def test_hardware_uuid_falls_back_as_key(seeded_session):
    engine, set_profiles = seeded_session
    set_profiles([{"hardware_uuid": "hw-9", "model": "Jetson"}])
    await GPUService().list_gpus()
    await GPUService().list_gpus()

    listings = await _listings(engine)
    assert len(listings) == 1
    assert listings[0].gpu_id == "hw-9"
