"""Concurrency pin for POST /v1/parameters/apply (#1421 follow-on).

``apply_parameter_change`` is a check-then-act: it SELECTs every
ServiceConfig row for the service type, validates ``old_value`` against
each, then writes ``new_value`` and commits — with no row lock, version
column, or serializable transaction. Two governance-approved proposals that
both expect the same ``old_value`` can therefore both pass the check and
both commit; the second write lands on a baseline the first already moved,
so its approval precondition no longer holds.

These tests drive the endpoint function against a real async SQLite
database with two independent sessions (the same shape two concurrent HTTP
requests produce). A barrier inside ``execute`` holds both sessions until
each has read the pre-change rows, making the check-then-act window
deterministic instead of timing-dependent.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from poolhub.app.routers.parameters import ParameterChangeRequest, apply_parameter_change
from poolhub.models import Base, Miner, ServiceConfig


class _BarrierSession:
    """AsyncSession proxy that parks ``execute`` until every peer arrives.

    The endpoint issues exactly one ``execute`` (the ServiceConfig SELECT)
    before mutating and committing, so gating there forces both sessions to
    read the same pre-change snapshot — the exact interleaving a real
    concurrent request pair can hit.
    """

    def __init__(self, inner: AsyncSession, barrier: asyncio.Barrier) -> None:
        self._inner = inner
        self._barrier = barrier

    async def execute(self, stmt: Any, *args: Any, **kwargs: Any) -> Any:
        result = await self._inner.execute(stmt, *args, **kwargs)
        await self._barrier.wait()
        return result

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


@pytest.fixture
async def session_factory(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'poolhub_conc.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        s.add(
            Miner(
                miner_id="miner-1",
                api_key_hash="hash",
                addr="0xabc",
                proto="http",
                gpu_vram_gb=24.0,
                cpu_cores=8,
                ram_gb=32.0,
                max_parallel=4,
                base_price=Decimal("0.01"),
            )
        )
        s.add(
            ServiceConfig(
                miner_id="miner-1",
                service_type="whisper",
                enabled=True,
                max_concurrent=1,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )
        await s.commit()
    yield factory
    await engine.dispose()


def _change(proposal_id: str, new_value: int) -> ParameterChangeRequest:
    return ParameterChangeRequest(
        proposal_id=proposal_id,
        target_service="whisper",
        parameter_name="max_concurrent",
        old_value=1,
        new_value=new_value,
    )


async def _race(factory, change_a: ParameterChangeRequest, change_b: ParameterChangeRequest) -> list[Any]:
    barrier = asyncio.Barrier(2)
    async with factory() as s1, factory() as s2:
        return list(
            await asyncio.gather(
                apply_parameter_change(change_a, _BarrierSession(s1, barrier), {}),  # type: ignore[arg-type]
                apply_parameter_change(change_b, _BarrierSession(s2, barrier), {}),  # type: ignore[arg-type]
                return_exceptions=True,
            )
        )


@pytest.mark.xfail(
    strict=True,
    reason="check-then-act old_value guard lets conflicting changes both commit — fix tracked in #1600",
)
@pytest.mark.asyncio
async def test_concurrent_conflicting_applies_at_most_one_succeeds(session_factory) -> None:
    """Two proposals racing on old_value=1 must not both apply.

    Exactly one transition from the approved baseline is legitimate; the
    loser must see a 409 (its old_value no longer holds) — not silently
    overwrite the winner's committed value.
    """
    results = await _race(session_factory, _change("prop-a", 4), _change("prop-b", 7))

    applied = [r for r in results if getattr(r, "applied", False)]
    conflicts = [r for r in results if getattr(r, "status_code", None) == 409]
    assert len(applied) + len(conflicts) == 2, f"unexpected outcomes: {results!r}"
    assert len(applied) <= 1, f"both conflicting changes applied — last writer won on a stale baseline: {results!r}"


@pytest.mark.asyncio
async def test_concurrent_identical_applies_are_idempotent(session_factory) -> None:
    """A replayed identical proposal may apply twice harmlessly — same
    new_value, so the end state is correct either way. This pins that the
    guard does not need to distinguish replay from conflict for safety."""
    results = await _race(session_factory, _change("prop-a", 4), _change("prop-a", 4))

    assert all(getattr(r, "applied", False) for r in results), f"unexpected outcomes: {results!r}"

    async with session_factory() as s:
        row = (await s.execute(select(ServiceConfig).where(ServiceConfig.service_type == "whisper"))).scalars().one()
        assert row.max_concurrent == 4
