"""EDGE-JOIN-CHAINID-1 (#1383): IslandService.join_island accepts
chain_id as str | list[str] (the chain RPC supports both), but the local
island_memberships.chain_id column is a plain str. A list must be
normalized before the row is written — previously the on-chain join
succeeded and the local write then raised ValidationError, 500ing the
caller.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlmodel import SQLModel, select

import aitbc_edge.services.island_service as svc_mod
from aitbc_edge.schemas.island import IslandMembership


class _StubRPC:
    """async context manager replacing BlockchainRPCClient."""

    def __init__(self, reply: dict[str, Any]):
        self._reply = reply

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def join_island(
        self,
        island_id: str,
        island_name: str,
        chain_id: str | list[str],
        role: str = "compute-provider",
        is_hub: bool = False,
    ) -> dict[str, Any]:
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


async def _memberships(engine) -> list[IslandMembership]:
    async with AsyncSession(engine) as session:
        result = await session.execute(select(IslandMembership))
        return list(result.scalars().all())


def _patch_rpc(monkeypatch, reply: dict[str, Any]):
    monkeypatch.setattr(svc_mod, "BlockchainRPCClient", lambda **kw: _StubRPC(reply))


_JOIN_OK = {"success": True, "island_id": "isl-1", "status": "joined", "message": "ok"}


@pytest.mark.asyncio
async def test_list_chain_id_is_normalized_before_storage(monkeypatch, session_factory):
    _patch_rpc(monkeypatch, dict(_JOIN_OK))

    svc = svc_mod.IslandService()
    result = await svc.join_island(
        island_id="isl-1",
        island_name="Test Island",
        chain_id=["chain-a", "chain-b"],
    )

    assert result["success"] is True
    rows = await _memberships(session_factory)
    assert len(rows) == 1
    row = rows[0]
    assert row.chain_id == "chain-a,chain-b"
    assert row.extra_data["chain_ids"] == ["chain-a", "chain-b"]


@pytest.mark.asyncio
async def test_str_chain_id_still_stored_verbatim(monkeypatch, session_factory):
    _patch_rpc(monkeypatch, dict(_JOIN_OK))

    svc = svc_mod.IslandService()
    result = await svc.join_island(
        island_id="isl-1",
        island_name="Test Island",
        chain_id="ait-mainnet",
    )

    assert result["success"] is True
    rows = await _memberships(session_factory)
    assert len(rows) == 1
    assert rows[0].chain_id == "ait-mainnet"
    assert "chain_ids" not in rows[0].extra_data
