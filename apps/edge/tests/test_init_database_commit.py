"""#1390: init_database must not 500 after a successful commit.

``AsyncSession(engine)`` defaults to ``expire_on_commit=True``, so reading
``db.id`` after ``session.commit()`` triggered a lazy refresh and raised
``MissingGreenlet`` under aiosqlite — the row committed but the endpoint
returned 500. The fix captures ``db.id`` before the commit.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlmodel import SQLModel

import aitbc_edge.services.database_service as svc_mod
from aitbc_edge.services.database_service import DatabaseService


@pytest.fixture
async def seeded_session(monkeypatch, tmp_path):
    """Real aiosqlite session factory patched into the service (default
    expire_on_commit=True — the condition that triggered the bug)."""
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


@pytest.mark.asyncio
async def test_init_database_returns_id_after_commit(seeded_session) -> None:
    svc = DatabaseService()
    result = await svc.init_database("db_audit", "isl-1", 10)
    assert result["success"] is True
    assert result["id"].startswith("edge_db_")

    # Second call hits the already-exists branch and must not error either.
    again = await svc.init_database("db_audit", "isl-1", 10)
    assert again["success"] is False
    assert "already exists" in again["message"]
