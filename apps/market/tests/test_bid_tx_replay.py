"""Phase-0 pin for MARKET-BID-TX-REPLAY-1 (#817).

complete_bid verifies that the payment tx exists, is confirmed, and pays
offer.provider >= bid.price — but it never binds the tx to the bid or
records it as spent, so the same tx_hash completes unlimited bids and
delists N offers for one on-chain payment.

Desired: a tx_hash already spent on a completed bid is rejected for the
next one. FAILS on current main: bid A and bid B both complete with the
same hash.
"""

import sys
from collections.abc import AsyncIterator
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock

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


class TestBidTxReplay:
    @pytest.mark.asyncio
    async def test_same_tx_hash_cannot_complete_two_bids(self, session):
        svc = MarketService(session)
        tx = {
            "hash": "0xPAYMENT",
            "status": "confirmed",
            "sender": "0xBuyer",
            "recipient": "0xProvider",
            "value": 36_000_000,
        }
        svc._rpc_client.get_transaction = AsyncMock(return_value=tx)

        bids = []
        for _i in range(2):
            offer = await svc.create_offer(
                {
                    "provider": "0xProvider",
                    "price": "1",
                    "capacity": 1,
                    "gpu_model": "RTX4090",
                    "chain_id": "ait-testchain",
                }
            )
            offer_id = offer.id
            bid = Bid(
                offer_id=offer_id, provider="0xProvider", buyer="0xBuyer", capacity=1.0, price=Decimal("1"), status="pending"
            )
            session.add(bid)
            offer.status = "booked"
            session.add(offer)
            await session.commit()
            await session.refresh(bid)
            bids.append(bid.id)

        try:
            await svc.complete_bid(bids[0], "0xPAYMENT")
        except Exception:
            pass  # the service commits then trips on an expired attr — state persists
        try:
            await svc.complete_bid(bids[1], "0xPAYMENT")
        except Exception:
            pass
        rows = (await session.execute(select(Bid).where(Bid.id.in_(bids)))).scalars().all()
        completed = [b.id for b in rows if b.status == "completed"]
        # desired: only the first bid may complete on this tx — the replay is refused
        assert bids[1] not in completed, "same tx_hash completed a second bid — replay not bound"
