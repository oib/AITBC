"""#1450: naive ORM datetimes must not TypeError against aware UTC now."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from coordinator_api.contexts.trading.domain.trading import TradeRequest, TradeType
from coordinator_api.contexts.trading.services.trading_market.trading import P2PTradingProtocol
from sqlmodel import Session


def _minimal_request(agent_id: str, created_at: datetime) -> TradeRequest:
    return TradeRequest(
        request_id=f"req_{created_at.timestamp():.0f}",
        buyer_agent_id=agent_id,
        trade_type=TradeType.COMPUTE_RESOURCES,
        title="t",
        requirements={},
        budget_range={"min": "1", "max": "2"},
        created_at=created_at,
    )


class TestTradingSummaryNaiveCreatedAt:
    def test_summary_recent_activity_tolerates_naive_db_timestamp(self, db_session: Session) -> None:
        agent_id = "agent-tz-1450"
        recent_naive = (datetime.now(UTC) - timedelta(days=1)).replace(tzinfo=None)
        old_naive = (datetime.now(UTC) - timedelta(days=60)).replace(tzinfo=None)
        db_session.add(_minimal_request(agent_id, recent_naive))
        db_session.add(_minimal_request(agent_id, old_naive))
        db_session.commit()
        db_session.expunge_all()

        summary = P2PTradingProtocol(db_session).get_trading_summary(agent_id)

        assert summary["trade_requests"] == 2
        assert summary["recent_activity"]["requests_last_30d"] == 1
