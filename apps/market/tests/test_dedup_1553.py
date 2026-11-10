"""Pins for #1553 market dedup.

- ``book_offer`` must replay a pending bid the buyer already holds instead of
  stacking a second bid when the offer is still bookable (crash window between
  the bid commit and the offer-status commit).
- ``create_market_job`` replays an in-flight job on the same ``client_ref``.
"""

import sys
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from market_service.domain.market import Bid, MarketJob, MarketOffer
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


class TestBookOfferDedup:
    @pytest.mark.asyncio
    async def test_pending_bid_replays_instead_of_duplicating(self, session):
        svc = MarketService(session)
        offer = await _bookable_offer(svc)
        first = await svc.book_offer(offer.id, {"wallet": "0xBuyer"})
        assert first["bid_id"]

        # Simulate the crash window: bid committed, offer status rolled back
        # to bookable. A retry must return the same bid, not a second row.
        offer.status = "available"
        session.add(offer)
        await session.commit()

        second = await svc.book_offer(offer.id, {"wallet": "0xBuyer"})
        assert second["bid_id"] == first["bid_id"]
        bids = list((await session.execute(select(Bid).where(Bid.offer_id == offer.id))).scalars())
        assert len(bids) == 1

    @pytest.mark.asyncio
    async def test_different_buyer_gets_a_new_bid(self, session):
        svc = MarketService(session)
        offer = await _bookable_offer(svc)
        await svc.book_offer(offer.id, {"wallet": "0xBuyerA"})
        offer.status = "available"
        session.add(offer)
        await session.commit()
        second = await svc.book_offer(offer.id, {"wallet": "0xBuyerB"})
        bids = list((await session.execute(select(Bid).where(Bid.offer_id == offer.id))).scalars())
        assert len(bids) == 2
        assert second["bid_id"] in {b.id for b in bids}


class TestClientRefDedup:
    @pytest.mark.asyncio
    async def test_same_client_ref_replays_inflight_job(self, session):
        svc = MarketService(session)
        payload = {
            "client_ref": "order-123",
            "buyer_address": "0xBuyer",
            "service_type": "ipfs",
            "payment": {"amount": "1.5"},
        }
        first = await svc.create_market_job(dict(payload))
        second = await svc.create_market_job(dict(payload))
        assert second["job_id"] == first["job_id"]
        assert second.get("deduplicated") is True
        jobs = list((await session.execute(select(MarketJob).where(MarketJob.client_ref == "order-123"))).scalars())
        assert len(jobs) == 1

    @pytest.mark.asyncio
    async def test_client_ref_scoped_per_buyer(self, session):
        svc = MarketService(session)
        base = {"client_ref": "shared-ref", "service_type": "ipfs", "payment": {"amount": "1"}}
        await svc.create_market_job({**base, "buyer_address": "0xBuyerA"})
        other = await svc.create_market_job({**base, "buyer_address": "0xBuyerB"})
        assert other.get("deduplicated") is not True
        jobs = list((await session.execute(select(MarketJob).where(MarketJob.client_ref == "shared-ref"))).scalars())
        assert len(jobs) == 2


class TestCallerSuppliedIdDedup:
    """#1634: a caller-supplied job id is a natural key when client_ref is absent."""

    @pytest.mark.asyncio
    async def test_same_id_same_buyer_replays(self, session):
        svc = MarketService(session)
        payload = {
            "id": "job-fixed-1",
            "buyer_address": "0xBuyerA",
            "service_type": "ipfs",
            "payment": {"amount": "1"},
        }
        first = await svc.create_market_job(dict(payload))
        second = await svc.create_market_job(dict(payload))
        assert second["job_id"] == first["job_id"] == "job-fixed-1"
        assert second.get("deduplicated") is True
        jobs = list((await session.execute(select(MarketJob).where(MarketJob.id == "job-fixed-1"))).scalars())
        assert len(jobs) == 1

    @pytest.mark.asyncio
    async def test_same_id_different_buyer_conflicts(self, session):
        svc = MarketService(session)
        await svc.create_market_job(
            {
                "id": "job-fixed-2",
                "buyer_address": "0xBuyerA",
                "service_type": "ipfs",
                "payment": {"amount": "1"},
            }
        )
        with pytest.raises(ValueError, match="already exists"):
            await svc.create_market_job(
                {
                    "id": "job-fixed-2",
                    "buyer_address": "0xBuyerB",
                    "service_type": "ipfs",
                    "payment": {"amount": "1"},
                }
            )


class TestEscrowContractIdPersistence:
    """#1634: escrow_contract_id was write-never; creation now persists the
    chain escrow binding (the market job id is the /rpc/escrow path key)."""

    @pytest.mark.asyncio
    async def test_created_job_persists_escrow_binding(self, session):
        svc = MarketService(session)
        result = await svc.create_market_job(
            {
                "buyer_address": "0xBuyerA",
                "service_type": "ipfs",
                "payment": {"amount": "1"},
            }
        )
        job = await session.get(MarketJob, result["job_id"])
        assert job is not None
        assert job.escrow_contract_id == job.id
