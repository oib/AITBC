"""Coverage for ``TradingService`` — the legacy P2P trade-request CRUD layer.

Exercises create/list/analytics against an in-memory SQLite session,
including the server-field stripping that keeps clients from forging
status/id columns, and the Decimal analytics math.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine


@pytest.fixture
async def db_session():
    from trading_service.domain.base import trading_metadata
    from trading_service.domain.trading import (  # noqa: F401 — register tables
        TradeAgreement,
        TradeFeedback,
        TradeMatch,
        TradeNegotiation,
        TradeRequest,
        TradeSettlement,
        TradingAnalytics,
    )

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        # Trading tables live on trading_metadata, not SQLModel.metadata
        # (see domain/base.py — coordinator-api defines the same table names).
        await conn.run_sync(trading_metadata.create_all)

    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session

    await engine.dispose()


def _svc(session):
    from trading_service.services.trading_service import TradingService

    return TradingService(session)


def _request_data(**overrides):
    data = {
        "buyer_agent_id": "buyer-1",
        "trade_type": "ai_power",
        "title": "need inference",
    }
    data.update(overrides)
    return data


class TestCreateRequest:
    async def test_create_request_strips_server_fields(self, db_session):
        svc = _svc(db_session)
        request = await svc.create_request(
            _request_data(
                # Client tries to forge server-managed fields — all must be ignored
                request_id="req_forged",
                status="completed",
                match_count=99,
                created_at="2020-01-01T00:00:00",
            )
        )
        assert request.request_id != "req_forged"
        assert request.request_id.startswith("req_")
        assert request.status == "open"
        assert request.match_count == 0

    async def test_create_request_generates_id_when_absent(self, db_session):
        svc = _svc(db_session)
        request = await svc.create_request(_request_data())
        assert request.request_id
        assert request.status == "open"

    async def test_create_request_persists_and_reloads(self, db_session):
        svc = _svc(db_session)
        request = await svc.create_request(_request_data(buyer_agent_id="buyer-z"))
        fetched = await svc.get_request(request.request_id)
        assert fetched is not None
        assert fetched.buyer_agent_id == "buyer-z"


class TestListAndFilter:
    async def test_list_requests_filters(self, db_session):
        svc = _svc(db_session)
        await svc.create_request(_request_data(buyer_agent_id="b1", trade_type="ai_power"))
        await svc.create_request(_request_data(buyer_agent_id="b2", trade_type="compute_resources"))
        # Manually flip one to completed for status filtering
        requests = await svc.list_requests()
        requests[0].status = "completed"
        await db_session.commit()

        by_buyer = await svc.list_requests(buyer_agent_id="b1")
        assert len(by_buyer) == 1
        assert by_buyer[0].buyer_agent_id == "b1"

        by_status = await svc.list_requests(status="completed")
        assert len(by_status) == 1

        by_type = await svc.list_requests(trade_type="compute_resources")
        assert len(by_type) == 1


class TestAnalytics:
    async def test_analytics_empty_db(self, db_session):
        svc = _svc(db_session)
        stats = await svc.get_analytics()
        assert stats["total_requests"] == 0
        assert stats["total_trade_volume"] == 0.0
        assert stats["average_trade_value"] == 0.0

    async def test_analytics_completed_volume_and_average(self, db_session):
        """Volume sums only COMPLETED agreements; average divides by count."""
        from trading_service.domain.trading import (
            TradeAgreement,
            TradeRequest,
            TradeStatus,
            TradeType,
            SettlementType,
        )

        svc = _svc(db_session)
        db_session.add(
            TradeAgreement(
                agreement_id="agree_1",
                negotiation_id="neg_1",
                buyer_agent_id="b",
                seller_agent_id="s",
                trade_type=TradeType.AI_POWER,
                title="t",
                settlement_type=SettlementType.IMMEDIATE,
                total_price=Decimal("100.5"),
                status=TradeStatus.COMPLETED,
            )
        )
        db_session.add(
            TradeAgreement(
                agreement_id="agree_2",
                negotiation_id="neg_2",
                buyer_agent_id="b",
                seller_agent_id="s",
                trade_type=TradeType.AI_POWER,
                title="t",
                settlement_type=SettlementType.IMMEDIATE,
                total_price=Decimal("200.5"),
                status=TradeStatus.COMPLETED,
            )
        )
        # Non-completed agreement must not count toward volume
        db_session.add(
            TradeAgreement(
                agreement_id="agree_3",
                negotiation_id="neg_3",
                buyer_agent_id="b",
                seller_agent_id="s",
                trade_type=TradeType.AI_POWER,
                title="t",
                settlement_type=SettlementType.IMMEDIATE,
                total_price=Decimal("999"),
                status=TradeStatus.AGREED,
            )
        )
        db_session.add(
            TradeRequest(
                request_id="req_1",
                buyer_agent_id="b",
                trade_type=TradeType.AI_POWER,
                title="t",
            )
        )
        await db_session.commit()

        stats = await svc.get_analytics()
        assert stats["total_requests"] == 1
        assert stats["total_agreements"] == 3
        assert stats["completed_trades"] == 2
        # 100.5 + 200.5 = 301.0 — the AGREED agreement's 999 is excluded
        assert stats["total_trade_volume"] == pytest.approx(301.0)
        assert stats["average_trade_value"] == pytest.approx(150.5)


class TestCreateMatchAgreementSettlement:
    async def test_create_match_strips_server_fields(self, db_session):
        svc = _svc(db_session)
        await svc.create_request(_request_data())
        match = await svc.create_match(
            {
                "request_id": "req_x",
                "buyer_agent_id": "b",
                "seller_agent_id": "s",
                "match_score": 90.0,
                "confidence_level": 0.9,
                "price_compatibility": 80.0,
                "timing_compatibility": 80.0,
                "specification_compatibility": 80.0,
                "reputation_compatibility": 80.0,
                "geographic_compatibility": 80.0,
                "match_id": "match_forged",
                "status": "completed",
            }
        )
        assert match.match_id != "match_forged"
        assert match.status == "matching"

    async def test_create_agreement_and_settlement_defaults(self, db_session):
        from trading_service.domain.trading import SettlementType, TradeType

        svc = _svc(db_session)
        agreement = await svc.create_agreement(
            {
                "negotiation_id": "neg_1",
                "buyer_agent_id": "b",
                "seller_agent_id": "s",
                "trade_type": TradeType.AI_POWER,
                "title": "t",
                "settlement_type": SettlementType.IMMEDIATE,
                "total_price": "12.34",
                "status": "completed",  # forged — must be stripped
            }
        )
        assert agreement.status == "agreed"
        assert agreement.agreement_id.startswith("agree_")
        assert agreement.total_price == Decimal("12.34")

        settlement = await svc.create_settlement(
            {
                "agreement_id": agreement.agreement_id,
                "buyer_agent_id": "b",
                "seller_agent_id": "s",
                "settlement_type": SettlementType.IMMEDIATE,
                "total_amount": "12.34",
                "payment_status": "paid",  # forged — payment_status is a server field
            }
        )
        assert settlement.settlement_id.startswith("settle_")
        assert settlement.status == "settling"
        assert settlement.payment_status == "pending"


class TestUnboundedLists:
    @pytest.mark.xfail(
        strict=True,
        reason="TRADING-QUERY-1 (#1412): list_requests/list_matches/list_agreements "
        "have no LIMIT — the legacy GET /v1/trading/* endpoints return every "
        "row in the table; sibling services all take limit/offset",
    )
    async def test_list_requests_supports_limit(self, db_session):
        import inspect

        from trading_service.services.trading_service import TradingService

        sig = inspect.signature(TradingService.list_requests)
        assert "limit" in sig.parameters
