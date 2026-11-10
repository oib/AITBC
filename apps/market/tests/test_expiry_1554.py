"""Pins for #1554 market expiry: pending-bid TTL and offer reservation TTL.

- ``book_offer`` stamps ``Bid.expires_at``; ``complete_bid`` refuses an
  expired pending bid.
- The sweeper expires pending bids and releases offers whose
  ``attributes['_reserved_until']`` lapsed back to ``available``.
"""

import sys
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from market_service.domain.market import Bid, MarketOffer
from market_service.services.market_job_sweeper import MarketJobSweeper
from market_service.services.market_service import MarketService
from market_service.storage import get_session_context


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    async with get_session_context() as s:
        yield s


async def _bookable_offer(svc: MarketService) -> MarketOffer:
    return await svc.create_offer(
        {
            "provider": "0xProviderAddr",
            "price": "5",
            "capacity": 1,
            "gpu_model": "RTX4090",
            "chain_id": "ait-testchain",
        }
    )


class TestBidExpiry:
    @pytest.mark.asyncio
    async def test_pending_bid_carries_expires_at(self, session):
        svc = MarketService(session)
        offer = await _bookable_offer(svc)
        result = await svc.book_offer(offer.id, {"wallet": "0xBuyer"})
        bid = await session.get(Bid, result["bid_id"])
        assert bid is not None and bid.expires_at is not None
        assert bid.expires_at > datetime.now(UTC).replace(tzinfo=None)


class TestReservationExpiry:
    @pytest.mark.asyncio
    async def test_sweeper_expires_pending_bid_and_releases_offer(self, session):
        svc = MarketService(session)
        offer = await _bookable_offer(svc)
        result = await svc.book_offer(offer.id, {"wallet": "0xBuyer"})
        bid = await session.get(Bid, result["bid_id"])
        assert bid is not None
        bid.expires_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1)
        session.add(bid)

        # Force the offer's reservation deadline into the past.
        await session.refresh(offer)
        attrs = dict(offer.attributes or {})
        attrs["_reserved_until"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
        offer.attributes = attrs
        session.add(offer)
        await session.commit()

        sweeper = MarketJobSweeper()
        await sweeper._expire_stale_reservations(session, datetime.now(UTC).replace(tzinfo=None))
        await session.commit()

        await session.refresh(bid)
        await session.refresh(offer)
        assert bid.status == "expired"
        assert offer.status == "available"
        assert "_reserved_until" not in (offer.attributes or {})
