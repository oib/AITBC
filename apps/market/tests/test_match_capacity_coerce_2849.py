"""#2849 pin: requirements.capacity must be coerced, not just validated.

A string capacity ('4') passed _validate_match_requirements (which parsed
a copy) then TypeError'd in _calculate_match_score — AFTER the offer CAS
commit and the coordinator task submit, leaving the offer reserved until
TTL and the idempotency ledger marking the op failed→uncertain.
"""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from aitbc_shared import MarketOffer
from market_service.services.matching_service import MatchingService
from market_service.storage import engine

pytestmark = pytest.mark.asyncio


@asynccontextmanager
async def _prod_session():
    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session


async def _seed_offer(session) -> str:
    u = uuid4().hex[:8]
    region = f"capcoerce_{u}"
    session.add(
        MarketOffer(
            id=f"offer_cap_{u}",
            provider="0x4A5b3bf95aa06072c568Cfcb7392b4e86608B5D2",
            status="available",
            capacity=4,
            price_per_hour=Decimal("1.5"),
            region=region,
        )
    )
    await session.commit()
    return region


def _coordinator_client() -> Mock:
    resp = Mock()
    resp.raise_for_status = Mock()
    resp.json.return_value = {"task_id": "t1", "escrow_id": "e1", "job_id": "j1"}
    client = Mock()
    client.is_closed = False
    client.post = AsyncMock(return_value=resp)
    return client


async def test_string_capacity_completes_match() -> None:
    """The reported crash: capacity='4' validates, reserves, submits —
    then must still produce a match, not a post-commit TypeError."""
    async with _prod_session() as session:
        region = await _seed_offer(session)
        svc = MatchingService(session)
        svc._http_client = _coordinator_client()

        requirements = {"capacity": "4"}
        out = await svc.match_and_assign(requirements, preferred_region=region)

        assert out["status"] == "matched"
        assert out["task_id"] == "t1"
        # The dict was coerced in place — the coordinator payload carried
        # a JSON-safe number, and the score computation saw a number.
        assert requirements["capacity"] == 4.0
        assert isinstance(out["match_score"], float)


async def test_numeric_capacity_still_works() -> None:
    async with _prod_session() as session:
        region = await _seed_offer(session)
        svc = MatchingService(session)
        svc._http_client = _coordinator_client()

        out = await svc.match_and_assign({"capacity": 2}, preferred_region=region)
        assert out["status"] == "matched"


async def test_huge_capacity_rejected_not_inf() -> None:
    """Decimal('1e999') is finite but overflows float — it must not reach
    the coordinator payload as Infinity."""
    async with _prod_session() as session:
        region = await _seed_offer(session)
        svc = MatchingService(session)
        svc._http_client = _coordinator_client()

        with pytest.raises(ValueError, match="capacity"):
            await svc.match_and_assign({"capacity": "1e999"}, preferred_region=region)
