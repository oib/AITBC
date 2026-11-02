"""Phase-0 pin for MARKET-BOOKING-UNKNOWN-BUYER-1 (#816).

book_offer requires no wallet/buyer: a booking with no buyer stores
buyer="unknown". complete_bid then enforces tx_sender ==
canonical("unknown"), which no on-chain transaction can ever satisfy, and
cancel_offer rejects RESERVED -> DELISTED — so an anonymous caller can book
every offer in the market and strand all inventory forever.

Desired: booking without a buyer identity is refused and no bid persists.
FAILS on current main: the anonymous booking commits a bid with
buyer="unknown" and the offer goes to "booked".
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
    async def test_anonymous_booking_leaves_no_bid(self, session):
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
        try:
            await svc.book_offer(offer_id, {})
        except Exception:
            pass  # refusal shape unpinned; what matters is nothing persisted
        bids = list((await session.execute(select(Bid).where(Bid.offer_id == offer_id))).scalars())
        assert not any(b.buyer == "unknown" for b in bids), (
            "anonymous booking persisted a bid with buyer='unknown' — it can never complete or cancel"
        )
