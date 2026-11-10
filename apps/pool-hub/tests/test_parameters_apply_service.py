"""apply_parameter_change tests — governance parameter application.

#1396 (POOLHUB-GOV-1): the ServiceConfig lookup filters by service_type only
across ALL miners' rows (scalar_one_or_none → 500 once two miners configure the
same service); attributes are mutated BEFORE the old_value check; and
isinstance(True, int) lets a bool through for max_concurrent.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from poolhub.app.routers.parameters import ParameterChangeRequest, apply_parameter_change
from poolhub.models import Base, Miner, ServiceConfig


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


def _miner(miner_id: str) -> Miner:
    return Miner(
        miner_id=miner_id,
        api_key_hash="x" * 64,
        addr="/ip4/127.0.0.1/tcp/9000",
        proto="tcp",
        gpu_vram_gb=24.0,
        gpu_name="RTX 4090",
        cpu_cores=16,
        ram_gb=64.0,
        max_parallel=4,
        base_price=Decimal("0.01"),
    )


def _config(miner_id: str, service_type: str = "whisper", max_concurrent: int = 1) -> ServiceConfig:
    return ServiceConfig(
        miner_id=miner_id,
        service_type=service_type,
        enabled=True,
        config={},
        pricing={},
        capabilities=[],
        max_concurrent=max_concurrent,
    )


def _change(**overrides) -> ParameterChangeRequest:
    kwargs = {
        "proposal_id": "prop-1",
        "target_service": "whisper",
        "parameter_name": "max_concurrent",
        "new_value": 3,
        "old_value": 1,
    }
    kwargs.update(overrides)
    return ParameterChangeRequest(**kwargs)


class TestHappyPath:
    async def test_valid_change_applies_and_commits(self, db_session):
        async with db_session() as s:
            s.add(_miner("m-1"))
            s.add(_config("m-1"))
            await s.commit()

        async with db_session() as s:
            response = await apply_parameter_change(_change(), db=s, _={})

        assert response.applied is True
        assert response.old_value == 1
        assert response.new_value == 3

        async with db_session() as s:
            row = (await s.execute(select(ServiceConfig))).scalar_one()
            assert row.max_concurrent == 3


class TestLookupScope:
    async def test_two_miners_same_service_type_does_not_500(self, db_session):
        async with db_session() as s:
            s.add(_miner("m-1"))
            s.add(_miner("m-2"))
            s.add(_config("m-1"))
            s.add(_config("m-2"))
            await s.commit()

        async with db_session() as s:
            response = await apply_parameter_change(_change(), db=s, _={})

        assert response.applied is True

    async def test_missing_service_config_is_404(self, db_session):
        async with db_session() as s:
            with pytest.raises(HTTPException) as exc:
                await apply_parameter_change(_change(target_service="blender"), db=s, _={})
        assert exc.value.status_code == 404


class TestValidation:
    async def test_disallowed_parameter_is_400(self, db_session):
        async with db_session() as s:
            s.add(_miner("m-1"))
            s.add(_config("m-1"))
            await s.commit()
        async with db_session() as s:
            with pytest.raises(HTTPException) as exc:
                await apply_parameter_change(_change(parameter_name="admin_override"), db=s, _={})
        assert exc.value.status_code == 400

    async def test_wrong_type_is_400(self, db_session):
        async with db_session() as s:
            s.add(_miner("m-1"))
            s.add(_config("m-1"))
            await s.commit()
        async with db_session() as s:
            with pytest.raises(HTTPException) as exc:
                await apply_parameter_change(_change(new_value="three"), db=s, _={})
        assert exc.value.status_code == 400

    async def test_bool_is_not_accepted_for_int_parameter(self, db_session):
        async with db_session() as s:
            s.add(_miner("m-1"))
            s.add(_config("m-1"))
            await s.commit()
        async with db_session() as s:
            with pytest.raises(HTTPException) as exc:
                await apply_parameter_change(_change(new_value=True), db=s, _={})
        assert exc.value.status_code == 400

    async def test_negative_max_concurrent_is_rejected(self, db_session):
        async with db_session() as s:
            s.add(_miner("m-1"))
            s.add(_config("m-1"))
            await s.commit()
        async with db_session() as s:
            with pytest.raises(HTTPException) as exc:
                await apply_parameter_change(_change(new_value=-5), db=s, _={})
        assert exc.value.status_code == 400


class TestOldValueCheck:
    async def test_rejected_change_leaves_config_unmodified(self, db_session):
        async with db_session() as s:
            s.add(_miner("m-1"))
            s.add(_config("m-1", max_concurrent=1))
            await s.commit()

        async with db_session() as s:
            with pytest.raises(HTTPException) as exc:
                await apply_parameter_change(_change(old_value=999), db=s, _={})
            assert exc.value.status_code == 409
            row = (await s.execute(select(ServiceConfig))).scalar_one()
            assert row.max_concurrent == 1, "rejected change must not mutate the row"

    async def test_matching_old_value_applies(self, db_session):
        async with db_session() as s:
            s.add(_miner("m-1"))
            s.add(_config("m-1", max_concurrent=2))
            await s.commit()
        async with db_session() as s:
            response = await apply_parameter_change(_change(old_value=2, new_value=4), db=s, _={})
        assert response.applied is True
        assert response.old_value == 2
