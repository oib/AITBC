"""Pins for #1553: inter-chain create dedup.

``InterChainTradeService.create_trade`` replays an identical pending trade
instead of stacking a duplicate that could reach escrow/settlement twice.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine


@pytest.fixture
async def db_session():
    """In-memory SQLite async session with all trading tables."""
    from trading_service.domain.base import trading_metadata
    from trading_service.domain.inter_chain import (  # noqa: F401 — register tables
        InterChainTrade,
        IslandRegistryEntry,
    )
    from trading_service.domain.trading import (  # noqa: F401 — register tables
        TradeAgreement,
        TradeMatch,
        TradeNegotiation,
        TradeRequest,
        TradeSettlement,
    )

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(trading_metadata.create_all)

    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session

    await engine.dispose()


_CREATE_KWARGS = {
    "source_chain": "chain-a",
    "dest_chain": "chain-b",
    "sender": "0xSender",
    "recipient": "0xRecipient",
    "amount": 100,
    "offer_id": "offer-1",
    "price": Decimal("1.5"),
    "quantity": 2,
}


class TestInterChainCreateDedup:
    @pytest.mark.asyncio
    async def test_identical_create_replays_pending_trade(self, db_session: AsyncSession):
        from trading_service.services.inter_chain_service import InterChainTradeService

        svc = InterChainTradeService(db_session)
        first = await svc.create_trade(**_CREATE_KWARGS)
        second = await svc.create_trade(**_CREATE_KWARGS)
        assert second.trade_id == first.trade_id

    @pytest.mark.asyncio
    async def test_different_terms_create_new_trade(self, db_session: AsyncSession):
        from trading_service.services.inter_chain_service import InterChainTradeService

        svc = InterChainTradeService(db_session)
        await svc.create_trade(**_CREATE_KWARGS)
        other = await svc.create_trade(**{**_CREATE_KWARGS, "amount": 200})
        assert other.amount == 200

    @pytest.mark.asyncio
    async def test_expired_pending_trade_does_not_replay(self, db_session: AsyncSession):
        from trading_service.services.inter_chain_service import InterChainTradeService

        svc = InterChainTradeService(db_session)
        stale = await svc.create_trade(**_CREATE_KWARGS)
        stale.expires_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1)
        db_session.add(stale)
        await db_session.commit()

        fresh = await svc.create_trade(**_CREATE_KWARGS)
        assert fresh.trade_id != stale.trade_id
