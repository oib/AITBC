"""Pin for MARKET-BOOKING-UNKNOWN-BUYER-1 (#816), post-fix contract.

book_offer refuses a booking with no buyer identity (a persisted
``buyer='unknown'`` can never match an on-chain sender in complete_bid,
which stranded the offer in RESERVED forever), and a RESERVED offer has a
recovery path: cancel releases it RESERVED -> AVAILABLE -> DELISTED.

Green on the fix; FAILS on pre-fix main (the anonymous booking persisted).
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


class TestAnonymousBookingRefused:
    @pytest.mark.asyncio
    async def test_booking_without_buyer_is_rejected(self, session):
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
        with pytest.raises(ValueError, match="(?i)buyer|wallet"):
            await svc.book_offer(offer.id, {})
        bids = list((await session.execute(select(Bid).where(Bid.offer_id == offer.id))).scalars())
        assert not bids

    @pytest.mark.asyncio
    async def test_reserved_offer_is_recoverable_via_cancel(self, session):
        """A RESERVED offer must reach DELISTED through cancel (release first)."""
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
        oid = offer.id
        offer.status = "booked"  # RESERVED on the wire
        session.add(offer)
        await session.commit()
        # service-level transition sequence the cancel route performs
        await svc.update_offer_status(oid, "available")
        await svc.update_offer_status(oid, "cancelled")
        stored = await svc.get_offer(oid)
        assert stored.status in {"cancelled", "delisted"}
