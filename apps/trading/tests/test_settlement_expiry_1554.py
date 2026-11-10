"""Pins for #1554 trading settlement expiry.

- ``TradeSettlement`` rows carry ``expires_at`` (TRADE_SETTLEMENT_TTL_SECONDS,
  default 7d); stale SETTLING rows are failed lazily on the next create.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

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


class TestSettlementExpiry:
    @pytest.mark.asyncio
    async def test_settlement_gets_expires_at(self, db_session: AsyncSession):
        from trading_service.services.trading_service import TradingService

        svc = TradingService(db_session)
        settlement = await svc.create_settlement(
            {
                "agreement_id": "agree-1",
                "buyer_agent_id": "buyer",
                "seller_agent_id": "seller",
                "settlement_type": "immediate",
                "total_amount": "10",
            }
        )
        assert settlement.expires_at is not None
        assert settlement.expires_at > datetime.now(UTC).replace(tzinfo=None)

    @pytest.mark.asyncio
    async def test_stale_settling_row_fails_on_next_create(self, db_session: AsyncSession):
        from trading_service.domain.trading import TradeStatus
        from trading_service.services.trading_service import TradingService

        svc = TradingService(db_session)
        stale = await svc.create_settlement(
            {
                "agreement_id": "agree-old",
                "buyer_agent_id": "buyer",
                "seller_agent_id": "seller",
                "settlement_type": "immediate",
                "total_amount": "10",
            }
        )
        stale.expires_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1)
        db_session.add(stale)
        await db_session.commit()

        await svc.create_settlement(
            {
                "agreement_id": "agree-new",
                "buyer_agent_id": "buyer",
                "seller_agent_id": "seller",
                "settlement_type": "immediate",
                "total_amount": "10",
            }
        )
        await db_session.refresh(stale)
        assert stale.status == TradeStatus.FAILED
