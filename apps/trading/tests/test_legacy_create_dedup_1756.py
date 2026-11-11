"""Pins for #1756: legacy trading creates replay on caller-supplied ids.

``create_request``/``create_match``/``create_agreement``/``create_settlement``
accept a caller-supplied business id (``request_id``/``match_id``/
``agreement_id``/``settlement_id``). An identical retry must return the
existing row (idempotent replay); the same id with different terms must
raise ``LegacyCreateConflictError`` (HTTP 409) instead of a 500.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select
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


def _svc(session: AsyncSession):
    from trading_service.services.trading_service import TradingService

    return TradingService(session)


_REQUEST = {
    "buyer_agent_id": "buyer-1",
    "trade_type": "ai_power",
    "title": "need inference",
    "request_id": "req_client_1",
}

_MATCH = {
    "request_id": "req_parent",
    "buyer_agent_id": "b",
    "seller_agent_id": "s",
    "match_score": 90.0,
    "confidence_level": 0.9,
    "price_compatibility": 80.0,
    "timing_compatibility": 80.0,
    "specification_compatibility": 80.0,
    "reputation_compatibility": 80.0,
    "geographic_compatibility": 80.0,
    "match_id": "match_client_1",
}

_AGREEMENT = {
    "negotiation_id": "neg_1",
    "buyer_agent_id": "b",
    "seller_agent_id": "s",
    "trade_type": "ai_power",
    "title": "t",
    "settlement_type": "immediate",
    "agreement_id": "agree_client_1",
}

_SETTLEMENT = {
    "agreement_id": "agree_x",
    "buyer_agent_id": "b",
    "seller_agent_id": "s",
    "settlement_type": "immediate",
    "settlement_id": "settle_client_1",
}


class TestRequestReplay:
    @pytest.mark.asyncio
    async def test_identical_retry_replays_same_row(self, db_session: AsyncSession):
        from trading_service.domain.trading import TradeRequest

        svc = _svc(db_session)
        first = await svc.create_request(dict(_REQUEST))
        second = await svc.create_request(dict(_REQUEST))
        assert second.request_id == first.request_id == "req_client_1"
        count = await db_session.execute(select(func.count()).select_from(TradeRequest))
        assert count.scalar() == 1

    @pytest.mark.asyncio
    async def test_same_id_different_payload_conflicts(self, db_session: AsyncSession):
        from trading_service.services.trading_service import LegacyCreateConflictError

        svc = _svc(db_session)
        await svc.create_request(dict(_REQUEST))
        with pytest.raises(LegacyCreateConflictError):
            await svc.create_request({**_REQUEST, "title": "different terms"})

    @pytest.mark.asyncio
    async def test_replay_survives_server_field_drift(self, db_session: AsyncSession):
        """A row that has since transitioned still replays — only caller
        fields are compared, never status/counters/timestamps."""
        from trading_service.domain.trading import TradeStatus

        svc = _svc(db_session)
        first = await svc.create_request(dict(_REQUEST))
        first.status = TradeStatus.CANCELLED
        first.match_count = 7
        await db_session.commit()

        second = await svc.create_request(dict(_REQUEST))
        assert second.request_id == "req_client_1"
        assert second.status == TradeStatus.CANCELLED  # the stored row, drift included
        assert second.match_count == 7

    @pytest.mark.asyncio
    async def test_invalid_caller_id_rejected(self, db_session: AsyncSession):
        svc = _svc(db_session)
        with pytest.raises(ValueError):
            await svc.create_request({**_REQUEST, "request_id": "x" * 200})
        with pytest.raises(ValueError):
            await svc.create_request({**_REQUEST, "request_id": "   "})

    @pytest.mark.asyncio
    async def test_no_caller_id_still_mints_unique_ids(self, db_session: AsyncSession):
        svc = _svc(db_session)
        payload = {k: v for k, v in _REQUEST.items() if k != "request_id"}
        a = await svc.create_request(dict(payload))
        b = await svc.create_request(dict(payload))
        assert a.request_id != b.request_id
        assert a.request_id.startswith("req_")


class TestMatchAgreementSettlementReplay:
    @pytest.mark.asyncio
    async def test_match_replay_and_conflict(self, db_session: AsyncSession):
        from trading_service.domain.trading import TradeMatch
        from trading_service.services.trading_service import LegacyCreateConflictError

        svc = _svc(db_session)
        first = await svc.create_match(dict(_MATCH))
        second = await svc.create_match(dict(_MATCH))
        assert second.match_id == first.match_id == "match_client_1"
        count = await db_session.execute(select(func.count()).select_from(TradeMatch))
        assert count.scalar() == 1
        with pytest.raises(LegacyCreateConflictError):
            await svc.create_match({**_MATCH, "match_score": 10.0})

    @pytest.mark.asyncio
    async def test_agreement_replay_and_conflict(self, db_session: AsyncSession):
        from trading_service.domain.trading import TradeAgreement
        from trading_service.services.trading_service import LegacyCreateConflictError

        svc = _svc(db_session)
        first = await svc.create_agreement(dict(_AGREEMENT))
        second = await svc.create_agreement(dict(_AGREEMENT))
        assert second.agreement_id == first.agreement_id == "agree_client_1"
        count = await db_session.execute(select(func.count()).select_from(TradeAgreement))
        assert count.scalar() == 1
        with pytest.raises(LegacyCreateConflictError):
            await svc.create_agreement({**_AGREEMENT, "title": "renegotiated"})

    @pytest.mark.asyncio
    async def test_settlement_replay_and_conflict(self, db_session: AsyncSession):
        from trading_service.domain.trading import TradeSettlement
        from trading_service.services.trading_service import LegacyCreateConflictError

        svc = _svc(db_session)
        first = await svc.create_settlement(dict(_SETTLEMENT))
        second = await svc.create_settlement(dict(_SETTLEMENT))
        assert second.settlement_id == first.settlement_id == "settle_client_1"
        count = await db_session.execute(select(func.count()).select_from(TradeSettlement))
        assert count.scalar() == 1
        with pytest.raises(LegacyCreateConflictError):
            await svc.create_settlement({**_SETTLEMENT, "buyer_agent_id": "someone-else"})
