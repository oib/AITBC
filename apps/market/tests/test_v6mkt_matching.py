"""Regression tests — alias-aware, bounded market matching (#1442, #1445).

* #1442 — ``find_best_match``/``match_and_assign`` filtered on the canonical
  ``available`` spelling only, hiding ``open``-spelled offers and crashing
  ``OfferFSM.from_string`` on alias words.
* #1445 — the two matcher candidate sets were the last unbounded reads.
"""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from aitbc_shared import MarketOffer
from market_service.services.matching_service import MatchingService
from market_service.storage import engine

pytestmark = pytest.mark.asyncio


@asynccontextmanager
async def _prod_session():
    """Mirror storage.get_session: expire_on_commit=False, as production uses."""
    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session


def _uid() -> str:
    return uuid4().hex[:8]


async def _seed_offers(session, statuses, region: str | None = None) -> str:
    u = _uid()
    region = region or f"v6_{u}"
    for i, status in enumerate(statuses):
        session.add(
            MarketOffer(
                id=f"offer_v6_{u}_{i}",
                provider="0x4A5b3bf95aa06072c568Cfcb7392b4e86608B5D2",
                status=status,
                capacity=4,
                price_per_hour=Decimal("1.5"),
                region=region,
            )
        )
    await session.commit()
    return region


async def test_find_best_match_sees_open_spelled_offer():
    """An offer stored as 'open' (a deployed spelling) must be matchable."""
    async with _prod_session() as session:
        region = await _seed_offers(session, ["open"])
        svc = MatchingService(session)
        match = await svc.find_best_match({}, preferred_region=region)
        assert match is not None
        assert match["id"].startswith("offer_v6_")


async def test_match_and_assign_reserves_open_spelled_offer():
    """match_and_assign must not crash OfferFSM on the 'open' spelling and
    must reserve the offer when the coordinator accepts the task."""
    async with _prod_session() as session:
        region = await _seed_offers(session, ["open"])
        svc = MatchingService(session)

        resp = Mock()
        resp.raise_for_status = Mock()
        resp.json.return_value = {"task_id": "t1", "escrow_id": "e1", "job_id": "j1"}
        client = Mock()
        client.is_closed = False
        client.post = AsyncMock(return_value=resp)
        svc._http_client = client

        out = await svc.match_and_assign({}, preferred_region=region)
        assert out["status"] == "matched"
        assert out["task_id"] == "t1"
        offer = await session.get(MarketOffer, out["offer_id"])
        assert offer is not None
        assert offer.status == "reserved"


async def test_matcher_statements_are_bounded():
    """The matcher candidate query must carry LIMIT (#1445)."""
    async with _prod_session() as session:
        region = await _seed_offers(session, ["available"] * 3)
        svc = MatchingService(session)
        statements: list[str] = []

        def _count(conn, cursor, statement, parameters, context, executemany):
            if "marketplaceoffer" in statement.lower():
                statements.append(statement)

        event.listen(engine.sync_engine, "before_cursor_execute", _count)
        try:
            await svc.find_best_match({}, preferred_region=region)
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", _count)
        assert statements, "expected a marketplaceoffer select"
        assert all("limit" in s.lower() for s in statements), f"unbounded matcher query: {statements}"
