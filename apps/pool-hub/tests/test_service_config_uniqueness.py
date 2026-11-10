"""ServiceConfig uniqueness pin — #1397 (POOLHUB-DB-1).

models.py:151 comments "Add unique constraint for miner_id + service_type" but
``__table_args__`` is a no-op ``({"schema": None},)``. The create route does
select-then-insert, so a concurrent pair of POSTs can both insert; afterwards
every ``scalar_one_or_none`` lookup for that miner+service_type raises
MultipleResultsFound and the config endpoints 500 permanently.
"""

from __future__ import annotations

import pytest
from decimal import Decimal
from sqlalchemy import UniqueConstraint
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from poolhub.models import Base, Miner, ServiceConfig


def test_service_config_enforces_unique_miner_service_type():
    """(miner_id, service_type) must be unique — one config row per miner per service."""
    uniques = [constraint for constraint in ServiceConfig.__table__.constraints if isinstance(constraint, UniqueConstraint)]
    covered = {tuple(sorted(col.name for col in constraint.columns)) for constraint in uniques}
    assert ("miner_id", "service_type") in covered, (
        "ServiceConfig has no UniqueConstraint(miner_id, service_type) — "
        "duplicate rows make every scalar_one_or_none lookup raise; see #1397"
    )


@pytest.mark.asyncio
async def test_duplicate_miner_service_type_insert_is_rejected():
    """The constraint is enforced by the database, not just declared on the model."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[Miner.__table__, ServiceConfig.__table__])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as s:
            s.add(
                Miner(
                    miner_id="m-1",
                    api_key_hash="h",
                    addr="a",
                    proto="http",
                    gpu_vram_gb=1.0,
                    cpu_cores=1,
                    ram_gb=1.0,
                    max_parallel=1,
                    base_price=Decimal("0.01"),
                )
            )
            s.add(ServiceConfig(miner_id="m-1", service_type="whisper"))
            await s.commit()
        async with factory() as s:
            s.add(ServiceConfig(miner_id="m-1", service_type="whisper"))
            with pytest.raises(IntegrityError):
                await s.commit()
    finally:
        await engine.dispose()
