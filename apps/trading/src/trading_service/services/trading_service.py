"""
Trading service for managing trading operations
"""

from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ..domain.trading import TradeAgreement, TradeMatch, TradeRequest, TradeStatus


class TradingService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_requests(
        self,
        status: str | None = None,
        buyer_agent_id: str | None = None,
        trade_type: str | None = None,
    ) -> list[TradeRequest]:
        """List trade requests"""
        stmt = select(TradeRequest)
        if status:
            stmt = stmt.where(TradeRequest.status == status)
        if buyer_agent_id:
            stmt = stmt.where(TradeRequest.buyer_agent_id == buyer_agent_id)
        if trade_type:
            stmt = stmt.where(TradeRequest.trade_type == trade_type)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_request(self, request_id: str) -> TradeRequest | None:
        """Get a specific trade request"""
        stmt = select(TradeRequest).where(TradeRequest.request_id == request_id)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def create_request(self, request_data: dict[str, Any]) -> TradeRequest:
        """Create a new trade request"""
        if "request_id" not in request_data:
            request_data["request_id"] = f"req_{uuid4().hex[:8]}"
        request = TradeRequest(**request_data)
        self.session.add(request)
        await self.session.commit()
        await self.session.refresh(request)
        return request

    async def list_matches(
        self,
        status: str | None = None,
        buyer_agent_id: str | None = None,
        seller_agent_id: str | None = None,
    ) -> list[TradeMatch]:
        """List trade matches"""
        stmt = select(TradeMatch)
        if status:
            stmt = stmt.where(TradeMatch.status == status)
        if buyer_agent_id:
            stmt = stmt.where(TradeMatch.buyer_agent_id == buyer_agent_id)
        if seller_agent_id:
            stmt = stmt.where(TradeMatch.seller_agent_id == seller_agent_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create_match(self, match_data: dict[str, Any]) -> TradeMatch:
        """Create a new trade match"""
        if "match_id" not in match_data:
            match_data["match_id"] = f"match_{uuid4().hex[:8]}"
        match = TradeMatch(**match_data)
        self.session.add(match)
        await self.session.commit()
        await self.session.refresh(match)
        return match

    async def list_agreements(
        self,
        status: str | None = None,
        buyer_agent_id: str | None = None,
        seller_agent_id: str | None = None,
    ) -> list[TradeAgreement]:
        """List trade agreements"""
        stmt = select(TradeAgreement)
        if status:
            stmt = stmt.where(TradeAgreement.status == status)
        if buyer_agent_id:
            stmt = stmt.where(TradeAgreement.buyer_agent_id == buyer_agent_id)
        if seller_agent_id:
            stmt = stmt.where(TradeAgreement.seller_agent_id == seller_agent_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create_agreement(self, agreement_data: dict[str, Any]) -> TradeAgreement:
        """Create a new trade agreement"""
        if "agreement_id" not in agreement_data:
            agreement_data["agreement_id"] = f"agree_{uuid4().hex[:8]}"
        agreement = TradeAgreement(**agreement_data)
        self.session.add(agreement)
        await self.session.commit()
        await self.session.refresh(agreement)
        return agreement

    async def get_analytics(self, period_type: str = "daily") -> dict[str, Any]:
        """Get trading analytics"""
        # Counts
        req_count_stmt = select(func.count()).select_from(TradeRequest)
        req_count_result = await self.session.execute(req_count_stmt)
        total_requests = req_count_result.scalar() or 0

        match_count_stmt = select(func.count()).select_from(TradeMatch)
        match_count_result = await self.session.execute(match_count_stmt)
        total_matches = match_count_result.scalar() or 0

        agree_count_stmt = select(func.count()).select_from(TradeAgreement)
        agree_count_result = await self.session.execute(agree_count_stmt)
        total_agreements = agree_count_result.scalar() or 0

        # Real trade volume from completed agreements
        completed_volume_stmt = (
            select(func.coalesce(func.sum(TradeAgreement.total_price), Decimal("0")))
            .select_from(TradeAgreement)
            .where(TradeAgreement.status == TradeStatus.COMPLETED)
        )
        completed_volume_result = await self.session.execute(completed_volume_stmt)
        completed_volume = completed_volume_result.scalar() or Decimal("0")

        completed_count_stmt = (
            select(func.count()).select_from(TradeAgreement).where(TradeAgreement.status == TradeStatus.COMPLETED)
        )
        completed_count_result = await self.session.execute(completed_count_stmt)
        completed_count = completed_count_result.scalar() or 0

        average_trade_value = Decimal("0")
        if completed_count:
            average_trade_value = completed_volume / completed_count

        return {
            "period_type": period_type,
            "total_requests": total_requests,
            "total_matches": total_matches,
            "total_agreements": total_agreements,
            "total_trades": total_matches,
            "completed_trades": completed_count,
            "total_trade_volume": float(completed_volume),
            "average_trade_value": float(average_trade_value),
        }
