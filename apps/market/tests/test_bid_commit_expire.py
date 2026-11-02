"""Phase-0 pin for MARKET-BID-COMMIT-EXPIRE-1 (#820).

book_offer/_create_bid and complete_bid call ``session.commit()`` and then
touch expired ORM attributes (``bid.id`` / ``offer.id``), which raises
``MissingGreenlet`` — AFTER the row already landed. The caller sees an
exception while the bid / delisted state persists: the write is committed
but reported as failed, so retries double-write and callers cannot tell
the operation succeeded.

Desired: the route either fails before the write or returns cleanly after
it — an exception must imply nothing persisted. FAILS on current main:
the route raises MissingGreenlet AND the bid row lands.
"""

import sys
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from market_service.domain.market import Bid
from market_service.services.market_service import MarketService
from market_service.storage import get_session_context


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    async with get_session_context() as s:
        yield s


class TestErrorImpliesNoRow:
    @pytest.mark.asyncio
    async def test_book_offer_error_does_not_leave_a_bid(self, session):
        svc = MarketService(session)
        offer = await svc.create_offer(
            {
                "provider": "0xProviderAddr",
                "price": "5",
                "capacity": 1,
                "gpu_model": "RTX4090",
                "chain_id": "ait-testchain",
            }
        )
        offer_id = offer.id
        raised = False
        try:
            await svc.book_offer(offer_id, {"wallet": "0xBuyer"})
        except Exception:
            raised = True
        bids = list((await session.execute(select(Bid).where(Bid.offer_id == offer_id))).scalars())
        # atomicity: a raised route must not leave committed state behind
        assert not (raised and bids), (
            "route raised (MissingGreenlet after commit) AND the bid persisted — caller sees failure but the write landed"
        )
