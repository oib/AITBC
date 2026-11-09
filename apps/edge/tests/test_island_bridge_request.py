"""EDGE-BRIDGE-REQ-1 (#1382): IslandService.request_bridge must not 500 on a
successful chain-side bridge request — populate source_island_id, require a
request_id from the RPC reply, and never let local bookkeeping mask the
chain success.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlmodel import SQLModel, select

import aitbc_edge.services.island_service as svc_mod
from aitbc_edge.schemas.island import BridgeRequest


class _StubRPC:
    """async context manager replacing BlockchainRPCClient."""

    def __init__(self, reply: dict[str, Any]):
        self._reply = reply

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def request_bridge(self, target_island_id: str) -> dict[str, Any]:
        return self._reply


@pytest.fixture
async def session_factory(monkeypatch, tmp_path):
    """In-memory sqlite session factory patched into the service."""
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/edge.db")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    @asynccontextmanager
    async def fake_get_session():
        async with AsyncSession(engine) as session:
            yield session

    monkeypatch.setattr(svc_mod, "get_session", fake_get_session)

    yield engine

    await engine.dispose()


async def _rows(engine) -> list[BridgeRequest]:
    async with AsyncSession(engine) as session:
        result = await session.execute(select(BridgeRequest))
        return list(result.scalars().all())


def _patch_rpc(monkeypatch, reply: dict[str, Any]):
    monkeypatch.setattr(svc_mod, "BlockchainRPCClient", lambda **kw: _StubRPC(reply))


@pytest.mark.asyncio
async def test_success_writes_row_with_source_island(monkeypatch, session_factory):
    monkeypatch.setattr(svc_mod.settings, "island_id", "isl-src")
    _patch_rpc(
        monkeypatch,
        {
            "success": True,
            "request_id": "req-123",
            "target_island_id": "isl-dst",
            "status": "pending",
            "message": "ok",
        },
    )

    svc = svc_mod.IslandService()
    result = await svc.request_bridge("isl-dst")

    assert result["success"] is True
    rows = await _rows(session_factory)
    assert len(rows) == 1
    row = rows[0]
    assert row.request_id == "req-123"
    assert row.source_island_id == "isl-src"
    assert row.target_island_id == "isl-dst"
    assert row.status == "pending"


@pytest.mark.asyncio
async def test_missing_request_id_skips_row_without_raising(monkeypatch, session_factory):
    _patch_rpc(monkeypatch, {"success": True, "status": "pending", "message": "ok"})

    svc = svc_mod.IslandService()
    result = await svc.request_bridge("isl-dst")

    # The chain-side request succeeded; the caller must see that, not a 500.
    assert result["success"] is True
    assert await _rows(session_factory) == []


@pytest.mark.asyncio
async def test_failed_rpc_writes_no_row(monkeypatch, session_factory):
    _patch_rpc(
        monkeypatch,
        {"success": False, "request_id": "", "status": "failed", "message": "nope"},
    )

    svc = svc_mod.IslandService()
    result = await svc.request_bridge("isl-dst")

    assert result["success"] is False
    assert await _rows(session_factory) == []
