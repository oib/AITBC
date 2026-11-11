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
        TradeMatch,
        TradeNegotiation,
        TradeRequest,
        TradeSettlement,
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
                # Server-managed fields must be ignored; the business id is
                # caller-controlled since #1756 (it is the dedup key).
                request_id="req_caller",
                status="completed",
                match_count=99,
                created_at="2020-01-01T00:00:00",
            )
        )
        assert request.request_id == "req_caller"
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
        # Monetary aggregates serialize as str(Decimal) — exact, not float (#1635)
        assert stats["total_trade_volume"] == "0"
        assert stats["average_trade_value"] == "0"

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
        # 100.5 + 200.5 = 301.0 — the AGREED agreement's 999 is excluded.
        # Serialized as str(Decimal) — exact, not float (#1635).
        assert Decimal(stats["total_trade_volume"]) == Decimal("301.0")
        assert Decimal(stats["average_trade_value"]) == Decimal("150.5")


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
                "match_id": "match_caller",
                "status": "completed",
            }
        )
        # match_id is the caller-controlled dedup key since #1756; status stays server-owned.
        assert match.match_id == "match_caller"
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
    async def test_list_requests_supports_limit(self, db_session):
        import inspect

        from trading_service.services.trading_service import TradingService

        sig = inspect.signature(TradingService.list_requests)
        assert "limit" in sig.parameters


class TestLegacyExpiry:
    """#1562: TradeRequest/TradeMatch/TradeNegotiation expires_at is write-only
    unless a lazy sweep flips stale non-terminal rows on read paths."""

    async def test_expired_rows_lazily_cancel_or_expire(self, db_session):
        from datetime import UTC, datetime, timedelta

        from trading_service.domain.trading import (
            NegotiationStatus,
            TradeMatch,
            TradeNegotiation,
            TradeRequest,
            TradeStatus,
            TradeType,
        )

        past = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1)
        db_session.add(
            TradeRequest(
                request_id="req_exp",
                buyer_agent_id="b",
                trade_type=TradeType.AI_POWER,
                title="expired",
                status=TradeStatus.OPEN,
                expires_at=past,
            )
        )
        db_session.add(
            TradeMatch(
                match_id="match_exp",
                request_id="req_exp",
                buyer_agent_id="b",
                seller_agent_id="s",
                match_score=1.0,
                confidence_level=0.5,
                price_compatibility=1.0,
                timing_compatibility=1.0,
                specification_compatibility=1.0,
                reputation_compatibility=1.0,
                geographic_compatibility=1.0,
                status=TradeStatus.MATCHING,
                expires_at=past,
            )
        )
        db_session.add(
            TradeNegotiation(
                negotiation_id="neg_exp",
                match_id="match_exp",
                buyer_agent_id="b",
                seller_agent_id="s",
                status=NegotiationStatus.PENDING,
                expires_at=past,
            )
        )
        await db_session.commit()

        svc = _svc(db_session)
        # Any legacy read path runs the sweep for all three tables.
        await svc.list_requests()

        request = await svc.get_request("req_exp")
        assert request is not None
        assert request.status == TradeStatus.CANCELLED

        matches = await svc.list_matches()
        match = next(m for m in matches if m.match_id == "match_exp")
        assert match.status == TradeStatus.CANCELLED

        from sqlalchemy import select

        result = await db_session.execute(select(TradeNegotiation).where(TradeNegotiation.negotiation_id == "neg_exp"))
        negotiation = result.scalars().first()
        assert negotiation is not None
        assert negotiation.status == NegotiationStatus.EXPIRED

    async def test_null_expires_at_falls_back_to_created_at_ttl(self, db_session, monkeypatch):
        from datetime import UTC, datetime, timedelta

        from trading_service.domain.trading import TradeRequest, TradeStatus, TradeType

        monkeypatch.setenv("TRADING_LEGACY_TTL_SECONDS", "60")
        old = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=120)
        db_session.add(
            TradeRequest(
                request_id="req_legacy_null",
                buyer_agent_id="b",
                trade_type=TradeType.AI_POWER,
                title="legacy",
                status=TradeStatus.OPEN,
                created_at=old,
                updated_at=old,
                last_activity=old,
                expires_at=None,
            )
        )
        await db_session.commit()

        svc = _svc(db_session)
        await svc.list_requests()
        request = await svc.get_request("req_legacy_null")
        assert request is not None
        assert request.status == TradeStatus.CANCELLED


class TestLegacyCreateValidation:
    async def test_invalid_request_payload_raises_value_error(self, db_session):
        svc = _svc(db_session)
        with pytest.raises(ValueError):
            await svc.create_request(_request_data(trade_type="not_a_trade_type"))

    async def test_negative_settlement_fee_raises_value_error(self, db_session):
        from trading_service.domain.trading import SettlementType

        svc = _svc(db_session)
        with pytest.raises(ValueError):
            await svc.create_settlement(
                {
                    "agreement_id": "agree_x",
                    "buyer_agent_id": "b",
                    "seller_agent_id": "s",
                    "settlement_type": SettlementType.IMMEDIATE,
                    "total_amount": "10",
                    "platform_fee": "-1",
                }
            )

    def test_legacy_create_endpoint_returns_422(self, client):
        resp = client.post(
            "/v1/trading/requests",
            json={
                "buyer_agent_id": "b",
                "trade_type": "not_a_trade_type",
                "title": "bad",
            },
        )
        assert resp.status_code == 422


class TestMoneyCeiling:
    """#1727: legacy agreement/settlement money fields share the 1e15 ceiling
    (market MAX_PAYMENT_AMOUNT / exchange _MARKET_MAX_PRICE) — 1e30 must not
    reach a 200."""

    _CEILING = "1000000000000000"

    def _agreement(self, **overrides):
        from trading_service.domain.trading import SettlementType, TradeType

        data = {
            "negotiation_id": "neg_1",
            "buyer_agent_id": "b",
            "seller_agent_id": "s",
            "trade_type": TradeType.AI_POWER,
            "settlement_type": SettlementType.IMMEDIATE,
            "title": "t",
        }
        data.update(overrides)
        return data

    def _settlement(self, **overrides):
        from trading_service.domain.trading import SettlementType

        data = {
            "agreement_id": "agree_x",
            "buyer_agent_id": "b",
            "seller_agent_id": "s",
            "settlement_type": SettlementType.IMMEDIATE,
        }
        data.update(overrides)
        return data

    async def test_agreement_total_price_at_ceiling_accepted(self, db_session):
        svc = _svc(db_session)
        agreement = await svc.create_agreement(self._agreement(total_price=self._CEILING))
        assert agreement.total_price == Decimal(self._CEILING)

    @pytest.mark.parametrize("bad", ["1000000000000000.00000001", "1e30"])
    async def test_agreement_total_price_over_ceiling_rejected(self, db_session, bad):
        svc = _svc(db_session)
        with pytest.raises(ValueError, match="must not exceed"):
            await svc.create_agreement(self._agreement(total_price=bad))

    async def test_settlement_money_fields_at_ceiling_accepted(self, db_session):
        svc = _svc(db_session)
        settlement = await svc.create_settlement(
            self._settlement(
                total_amount=self._CEILING,
                platform_fee=self._CEILING,
                processing_fee=self._CEILING,
                gas_fee=self._CEILING,
                net_amount_seller=self._CEILING,
            )
        )
        assert settlement.total_amount == Decimal(self._CEILING)

    @pytest.mark.parametrize("field", ["total_amount", "platform_fee", "processing_fee", "gas_fee", "net_amount_seller"])
    @pytest.mark.parametrize("bad", ["1000000000000000.00000001", "1e30"])
    async def test_settlement_money_fields_over_ceiling_rejected(self, db_session, field, bad):
        svc = _svc(db_session)
        with pytest.raises(ValueError, match="must not exceed"):
            await svc.create_settlement(self._settlement(**{field: bad}))

    def test_legacy_agreement_endpoint_returns_422_over_ceiling(self, client):
        resp = client.post(
            "/v1/trading/agreements",
            json={
                "negotiation_id": "neg_1",
                "buyer_agent_id": "b",
                "seller_agent_id": "s",
                "trade_type": "ai_power",
                "settlement_type": "immediate",
                "title": "t",
                "total_price": "1e30",
            },
        )
        assert resp.status_code == 422
