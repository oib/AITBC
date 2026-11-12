"""Phase-0 pin for MARKET-BID-TX-REPLAY-1 (#817).

complete_bid verifies that the payment tx exists, is confirmed, and pays
offer.provider >= bid.price — but it never binds the tx to the bid or
records it as spent, so the same tx_hash completes unlimited bids and
delists N offers for one on-chain payment.

Desired: a tx_hash already spent on a completed bid is rejected for the
next one. FAILS on current main: bid A and bid B both complete with the
same hash.
"""

import contextlib
import sys
from collections.abc import AsyncIterator
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import SQLAlchemyError
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

        # #1914: the payment tx must reference the bid/offer it settles.
        tx["payload"] = {"bid_id": bids[0]}
        try:
            await svc.complete_bid(bids[0], "0xPAYMENT")
        except (SQLAlchemyError, ValueError, TypeError, KeyError, AttributeError, RuntimeError):
            pass  # the service commits then trips on an expired attr — state persists
        try:
            await svc.complete_bid(bids[1], "0xPAYMENT")
        except (SQLAlchemyError, ValueError, TypeError, KeyError, AttributeError, RuntimeError):
            pass
        rows = (await session.execute(select(Bid).where(Bid.id.in_(bids)))).scalars().all()
        completed = [b.id for b in rows if b.status == "completed"]
        # desired: only the first bid may complete on this tx — the replay is refused
        assert bids[1] not in completed, "same tx_hash completed a second bid — replay not bound"

    @pytest.mark.asyncio
    async def test_zero_price_bid_cannot_complete(self, session):
        """#1914: a legacy/corrupt bid row with price <= 0 must fail closed —
        complete_bid may not skip the on-chain minimum for it."""
        svc = MarketService(session)
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
            price=Decimal("0"),
            status="pending",
        )
        session.add(bid)
        await session.commit()
        await session.refresh(bid)

        tx = {
            "hash": "0xDUST",
            "status": "confirmed",
            "sender": "0xBuyer",
            "recipient": "0xProvider",
            "value": 0,
        }
        svc._rpc_client.get_transaction = AsyncMock(return_value=tx)

        with pytest.raises(ValueError, match="no positive price"):
            await svc.complete_bid(bid.id, "0xDUST")
        await session.refresh(bid)
        assert bid.status == "pending"

    @pytest.mark.asyncio
    async def test_unbound_tx_cannot_complete_bid(self, session):
        """#1914: a confirmed buyer→provider tx with sufficient value but no
        payload reference to this bid/offer must not settle it."""
        svc = MarketService(session)
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

        for payload in ({}, {"offer_id": "0xUnrelatedOffer"}, {"order_id": "0xUnrelatedOrder"}):
            tx = {
                "hash": f"0xUNBOUND-{len(payload)}",
                "status": "confirmed",
                "sender": "0xBuyer",
                "recipient": "0xProvider",
                "value": 36_000_000,
                "payload": payload,
            }
            svc._rpc_client.get_transaction = AsyncMock(return_value=tx)
            with pytest.raises(ValueError, match="not bound"):
                await svc.complete_bid(bid.id, tx["hash"])
        await session.refresh(bid)
        assert bid.status == "pending"

    @pytest.mark.asyncio
    async def test_offer_bound_tx_completes_bid(self, session):
        """#1914: an offer-level reference (payload.offer_id) binds the tx just
        as well as a bid-level one — the chain's order_id index treats them
        equivalently."""
        svc = MarketService(session)
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

        tx = {
            "hash": "0xOFFERBOUND",
            "status": "confirmed",
            "sender": "0xBuyer",
            "recipient": "0xProvider",
            "value": 36_000_000,
            "payload": {"offer_id": offer.id},
        }
        svc._rpc_client.get_transaction = AsyncMock(return_value=tx)
        # the service commits then trips on an expired attr — state persists
        with contextlib.suppress(Exception):
            await svc.complete_bid(bid.id, "0xOFFERBOUND")
        await session.refresh(bid)
        assert bid.status == "completed"

    @pytest.mark.asyncio
    async def test_job_id_bound_tx_completes_bid(self, session):
        """#1914 respin: the chain's escrow convention keys payload.job_id to
        the same id the market registers escrows under — a tx carrying only
        job_id must bind, or every existing escrow-flow completion wedges."""
        svc = MarketService(session)
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

        tx = {
            "hash": "0xJOBBOUND",
            "status": "confirmed",
            "sender": "0xBuyer",
            "recipient": "0xProvider",
            "value": 36_000_000,
            "payload": {"job_id": bid.id},
        }
        svc._rpc_client.get_transaction = AsyncMock(return_value=tx)
        with contextlib.suppress(Exception):
            await svc.complete_bid(bid.id, "0xJOBBOUND")
        await session.refresh(bid)
        assert bid.status == "completed"

    @pytest.mark.asyncio
    async def test_non_dict_payload_fails_closed_not_500(self, session):
        """#1914 respin: a tx whose payload is not a dict must fail closed
        with ValueError (400), not AttributeError (500)."""
        svc = MarketService(session)
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

        for bad_payload in ("not-a-dict", ["bid_id"], 42):
            tx = {
                "hash": f"0xBADPAYLOAD-{type(bad_payload).__name__}",
                "status": "confirmed",
                "sender": "0xBuyer",
                "recipient": "0xProvider",
                "value": 36_000_000,
                "payload": bad_payload,
            }
            svc._rpc_client.get_transaction = AsyncMock(return_value=tx)
            with pytest.raises(ValueError, match="not bound"):
                await svc.complete_bid(bid.id, tx["hash"])
        await session.refresh(bid)
        assert bid.status == "pending"
