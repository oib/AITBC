"""#2848 pin: one payment settles one bid — DB-level uniqueness backstop.

complete_bid's spent-hash check is select-then-write: two concurrent
completes carrying the same tx_hash both pass the SELECT before either
commits, settling two bids (and delisting two offers) on one payment.
The ux_bids_tx_hash partial unique index makes the loser's commit fail;
complete_bid translates the IntegrityError into the same "already
settled" refusal the pre-check raises.
"""

import sys
from collections.abc import AsyncIterator
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import IntegrityError
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


async def _seed_booked_bid(svc: MarketService, session: AsyncSession) -> tuple[str, str]:
    """Create an offer + pending bid; returns (offer_id, bid_id)."""
    offer = await svc.create_offer(
        {
            "provider": "0xProvider",
            "price": "1",
            "capacity": 1,
            "gpu_model": "RTX4090",
            "chain_id": "ait-testchain",
        }
    )
    offer.status = "booked"
    session.add(offer)
    bid = Bid(
        offer_id=offer.id,
        provider="0xProvider",
        buyer="0xBuyer",
        capacity=1.0,
        price=Decimal("1"),
        status="pending",
    )
    session.add(bid)
    await session.commit()
    await session.refresh(bid)
    return offer.id, bid.id


def _payment_tx(bid_id: str) -> dict:
    return {
        "hash": "0xRACE",
        "status": "confirmed",
        "sender": "0xBuyer",
        "recipient": "0xProvider",
        "value": 36_000_000,
        "payload": {"bid_id": bid_id},
    }


class TestBidTxUniqueness:
    @pytest.mark.asyncio
    async def test_tx_hash_unique_index_rejects_duplicate(self, session):
        """The schema backstop itself: two bids may not carry one tx_hash."""
        for _ in range(2):
            session.add(
                Bid(
                    offer_id="offer-x",
                    provider="0xP",
                    buyer="0xB",
                    capacity=1.0,
                    price=Decimal("1"),
                    status="completed",
                    tx_hash="0xSAME",
                )
            )
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()

    @pytest.mark.asyncio
    async def test_concurrent_complete_settles_one_bid(self, session):
        """Loser-of-the-race simulation: the winner commits while the
        loser's verify hook is in flight — exactly the interleaving the
        select-then-write check cannot see."""
        svc_seed = MarketService(session)
        offer1, bid1 = await _seed_booked_bid(svc_seed, session)
        offer2, bid2 = await _seed_booked_bid(svc_seed, session)

        async with get_session_context() as s2:
            svc_win = MarketService(session)
            svc_lose = MarketService(s2)
            svc_win._rpc_client.get_transaction = AsyncMock(return_value=_payment_tx(bid1))

            # The winner's whole complete_bid runs inside the loser's
            # get_transaction await — after the loser's spent SELECT
            # already missed, before its commit.
            async def losing_get_tx(tx_hash, chain_id=None):
                await svc_win.complete_bid(bid1, "0xRACE")
                return _payment_tx(bid2)

            svc_lose._rpc_client.get_transaction = losing_get_tx

            with pytest.raises(ValueError, match="already settled"):
                await svc_lose.complete_bid(bid2, "0xRACE")

        # bid1 settled; bid2 must not be completed on the same payment.
        rows = (await session.execute(select(Bid).where(Bid.id.in_([bid1, bid2])))).scalars().all()
        by_id = {b.id: b for b in rows}
        assert by_id[bid1].status == "completed"
        assert by_id[bid2].status != "completed"
