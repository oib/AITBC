"""EDGE-ISLAND-STALE-ROW-1 (#578): leave_island must drop the edge-DB
membership row also on the #573 "not_member" refusal — the chain already
considers us gone. forbidden_default and legacy code-less failures keep it.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlmodel import SQLModel, select

import aitbc_edge.services.island_service as svc_mod
from aitbc_edge.schemas.island import IslandMembership, IslandStatus


class _StubRPC:
    """async context manager replacing BlockchainRPCClient."""

    def __init__(self, reply: dict[str, Any]):
        self._reply = reply

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def leave_island(self, island_id: str) -> dict[str, Any]:
        return self._reply


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

    async with AsyncSession(engine) as session:
        session.add(
            IslandMembership(
                island_id="isl-1",
                island_name="Test Island",
                chain_id="ait-mainnet",
                role="compute-provider",
                status=IslandStatus.ACTIVE,
            )
        )
        await session.commit()

    yield engine

    await engine.dispose()


async def _row_count(engine) -> int:
    async with AsyncSession(engine) as session:
        result = await session.execute(select(IslandMembership))
        return len(result.scalars().all())


def _patch_rpc(monkeypatch, reply: dict[str, Any]):
    monkeypatch.setattr(svc_mod, "BlockchainRPCClient", lambda **kw: _StubRPC(reply))


async def test_left_deletes_row(monkeypatch, seeded_session):
    _patch_rpc(
        monkeypatch,
        {"success": True, "island_id": "isl-1", "status": "left", "code": "left", "message": "Successfully left"},
    )
    result = await svc_mod.IslandService().leave_island("isl-1")
    assert result["success"] is True
    assert await _row_count(seeded_session) == 0


async def test_not_member_deletes_row(monkeypatch, seeded_session):
    """Chain says we are already gone — the edge row is stale and must go."""
    _patch_rpc(
        monkeypatch,
        {
            "success": False,
            "island_id": "isl-1",
            "status": "not_member",
            "code": "not_member",
            "message": "Not a member of island isl-1",
        },
    )
    result = await svc_mod.IslandService().leave_island("isl-1")
    assert result["success"] is False  # RPC doc returned unchanged
    assert result["code"] == "not_member"
    assert await _row_count(seeded_session) == 0


async def test_not_member_via_status_only_deletes_row(monkeypatch, seeded_session):
    """A reply carrying the code only in `status` is also recognised."""
    _patch_rpc(
        monkeypatch,
        {"success": False, "island_id": "isl-1", "status": "not_member", "message": "Not a member"},
    )
    await svc_mod.IslandService().leave_island("isl-1")
    assert await _row_count(seeded_session) == 0


async def test_forbidden_default_keeps_row(monkeypatch, seeded_session):
    _patch_rpc(
        monkeypatch,
        {
            "success": False,
            "island_id": "isl-1",
            "status": "forbidden_default",
            "code": "forbidden_default",
            "message": "Cannot leave the default island isl-1",
        },
    )
    result = await svc_mod.IslandService().leave_island("isl-1")
    assert result["code"] == "forbidden_default"
    assert await _row_count(seeded_session) == 1


async def test_legacy_codeless_failure_keeps_row(monkeypatch, seeded_session):
    """Pre-#573 shape: success:false with no code/status — must not delete."""
    _patch_rpc(
        monkeypatch,
        {
            "success": False,
            "island_id": "isl-1",
            "status": "failed",
            "message": "Failed to leave island isl-1 (may not be a member)",
        },
    )
    await svc_mod.IslandService().leave_island("isl-1")
    assert await _row_count(seeded_session) == 1
