"""CAS reservation pins for STATE-MACHINE-AUDIT-1 item 6 (#1424).

book_offer and match_and_assign used to check ``status == available`` and
write the reservation in separate steps — two concurrent callers could both
pass the check and both persist a bid / reserve the same offer. The fix is a
conditional ``UPDATE ... WHERE status IN (available spellings)`` whose
rowcount is the compare-and-swap verdict.
"""

from __future__ import annotations

import sys
from collections.abc import AsyncIterator
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from aitbc_shared import MarketOffer
from market_service.domain.market import Bid
from market_service.services.market_service import MarketService
from market_service.services.matching_service import MatchingService
from market_service.storage import get_session_context

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    async with get_session_context() as s:
        yield s


def _uid() -> str:
    return uuid4().hex[:8]


async def _seed_offer(session: AsyncSession, status: str = "available") -> MarketOffer:
    offer = MarketOffer(
        id=f"offer_cas_{_uid()}",
        provider="0xProviderAddr",
        status=status,
        capacity=4,
        price=Decimal("5"),
        price_per_hour=Decimal("1.5"),
        region=f"cas_{_uid()}",
        chain_id="ait-testchain",
    )
    session.add(offer)
    await session.commit()
    return offer


class TestBookOfferCAS:
    async def test_second_booking_on_same_session_loses_the_cas(self, session):
        """A second booking on the same offer must not double-write a bid —
        refused by the status check or the CAS, never both bids land."""
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
        first = await svc.book_offer(offer.id, {"wallet": "0xBuyerOne"})
        assert first["status"] == "pending"

        with pytest.raises(ValueError, match="not available"):
            await svc.book_offer(offer.id, {"wallet": "0xBuyerTwo"})

        bids = list((await session.execute(select(Bid).where(Bid.offer_id == offer.id))).scalars())
        assert len(bids) == 1

    async def test_cas_refuses_when_status_moved_between_read_and_write(self, session):
        """A stale 'available' read must not book an offer another writer
        already reserved — exercises the rowcount==0 path directly."""
        svc = MarketService(session)
        offer = await _seed_offer(session, status="booked")

        # Stand-in for the identity-mapped object a racing request would hold:
        # reads AVAILABLE, but the row is already RESERVED.
        stale = MarketOffer(
            id=offer.id,
            provider=offer.provider,
            status="available",
            capacity=offer.capacity,
            price=offer.price,
        )
        original = svc.get_offer
        svc.get_offer = AsyncMock(return_value=stale)  # type: ignore[method-assign]
        try:
            with pytest.raises(ValueError, match="not available"):
                await svc.book_offer(offer.id, {"wallet": "0xLateBuyer"})
        finally:
            svc.get_offer = original  # type: ignore[method-assign]

        bids = list((await session.execute(select(Bid).where(Bid.offer_id == offer.id))).scalars())
        assert not bids


class TestBidPriceBounds:
    """#1634 second pass: booking_data.price feeds bid.price, and complete_bid
    only enforces tx_value >= price when that value is positive — a negative
    or NaN price would settle a 'completed' bid for dust."""

    async def _book_with_price(self, session: AsyncSession, price: object) -> None:
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
        await svc.book_offer(offer.id, {"wallet": "0xBuyerOne", "price": price})

    async def test_negative_price_is_rejected(self, session):
        with pytest.raises(ValueError, match="non-negative"):
            await self._book_with_price(session, "-100")

    async def test_nan_price_is_rejected(self, session):
        with pytest.raises(ValueError, match="finite"):
            await self._book_with_price(session, "nan")

    async def test_over_cap_price_is_rejected(self, session):
        with pytest.raises(ValueError, match="must not exceed"):
            await self._book_with_price(session, "1000000000000001")

    async def test_unparseable_price_is_rejected(self, session):
        with pytest.raises(ValueError, match="valid number"):
            await self._book_with_price(session, "not-a-number")

    async def test_valid_price_still_books(self, session):
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
        result = await svc.book_offer(offer.id, {"wallet": "0xBuyerOne", "price": "7.5"})
        assert result["status"] == "pending"
        bid = (await session.execute(select(Bid).where(Bid.id == result["bid_id"]))).scalar_one()
        assert bid.price == Decimal("7.5")

    async def test_zero_price_is_rejected(self, session):
        """#1914: price=0 survives _money_decimal (non-negative) but makes
        required_value <= 0 in complete_bid — any dust tx then settles the bid."""
        with pytest.raises(ValueError, match="positive"):
            await self._book_with_price(session, "0")

    async def test_under_ask_price_is_rejected(self, session):
        """#1914: a bid below the offer's advertised price must not book."""
        with pytest.raises(ValueError, match="below the offer price"):
            await self._book_with_price(session, "4.99")

    async def test_rejected_price_leaves_offer_bookable(self, session):
        """The rejection runs before the CAS claim — no 'booked' stranding,
        no orphan bid row."""
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
        with pytest.raises(ValueError):
            await svc.book_offer(offer.id, {"wallet": "0xBuyerOne", "price": "0"})
        await session.refresh(offer)
        assert offer.status == "available"
        bids = (await session.execute(select(Bid).where(Bid.offer_id == offer.id))).scalars().all()
        assert bids == []

    async def test_price_equal_to_ask_still_books(self, session):
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
        result = await svc.book_offer(offer.id, {"wallet": "0xBuyerOne"})
        assert result["status"] == "pending"


class TestMatchAndAssignCAS:
    async def _mock_coordinator(self, svc: MatchingService) -> None:
        resp = Mock()
        resp.raise_for_status = Mock()
        resp.json.return_value = {"task_id": "t1", "escrow_id": "e1", "job_id": "j1"}
        client = Mock()
        client.is_closed = False
        client.post = AsyncMock(return_value=resp)
        svc._http_client = client

    async def test_reserved_offer_is_not_rematched(self, session):
        """After a successful match reserves the offer, a second match finds
        nothing — the CAS wrote 'reserved' and it stays excluded."""
        offer = await _seed_offer(session, status="available")
        region = offer.region

        svc = MatchingService(session)
        await self._mock_coordinator(svc)

        first = await svc.match_and_assign({}, preferred_region=region)
        assert first["status"] == "matched"
        assert first["offer_id"] == offer.id

        second = await svc.match_and_assign({}, preferred_region=region)
        assert second["status"] == "no_match"
