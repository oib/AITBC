"""#1566: matching must exclude offers with NULL price_per_hour even when no
max_price is supplied — SQLite sorts NULLs first under ORDER BY price ASC, so
a priceless offer would otherwise win "best match".
"""

from __future__ import annotations

import sys
from collections.abc import AsyncIterator
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from aitbc_shared.models.market import MarketOffer

from market_service.services.matching_service import MatchingService
from market_service.storage import get_session_context


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    async with get_session_context() as session:
        yield session


def _model() -> str:
    """Unique gpu_model per test — the session DB is shared across tests."""
    return f"gpu-1566-{uuid4().hex[:8]}"


async def _add_offer(
    session: AsyncSession,
    offer_id: str,
    price_per_hour: Decimal | None,
    *,
    gpu_model: str,
    chain_id: str = "ait-testchain",
) -> None:
    session.add(
        MarketOffer(
            id=offer_id,
            provider="provider-x",
            capacity=1,
            price=Decimal("0"),
            status="available",
            price_per_hour=price_per_hour,
            gpu_model=gpu_model,
            chain_id=chain_id,
        )
    )
    await session.commit()


async def test_find_best_match_skips_null_price_without_max_price(session: AsyncSession) -> None:
    """Regression: with no max_price the old code never applied the NULL filter,
    and the priceless offer sorted first and won."""
    model = _model()
    await _add_offer(session, "offer-null-1566", None, gpu_model=model)
    await _add_offer(session, "offer-priced-1566", Decimal("0.5"), gpu_model=model)

    match = await MatchingService(session).find_best_match({"capacity": 1}, required_gpu_model=model)
    assert match is not None
    assert match["id"] == "offer-priced-1566"


async def test_find_best_match_returns_none_when_all_prices_null(session: AsyncSession) -> None:
    model = _model()
    await _add_offer(session, "offer-null-only-1566", None, gpu_model=model)

    match = await MatchingService(session).find_best_match({"capacity": 1}, required_gpu_model=model)
    assert match is None


async def test_match_and_assign_no_match_when_only_null_prices(session: AsyncSession) -> None:
    """match_and_assign must report no_match rather than reserving a priceless offer.
    Isolated by a unique chain_id since this path has no model filter."""
    chain = f"ait-chain-1566-{uuid4().hex[:8]}"
    await _add_offer(session, "offer-null-assign-1566", None, gpu_model=_model(), chain_id=chain)

    result = await MatchingService(session).match_and_assign({"capacity": 1}, chain_id=chain)
    assert result["status"] == "no_match"
