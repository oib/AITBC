"""
Trading service for managing trading operations
"""

from typing import Any
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from domain.trading import TradeAgreement, TradeMatch, TradeRequest


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

    async def create_request(self, request_data: dict) -> TradeRequest:
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

    async def create_match(self, match_data: dict) -> TradeMatch:
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

    async def create_agreement(self, agreement_data: dict) -> TradeAgreement:
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
        from sqlalchemy import func, select

        # Count requests
        req_count_stmt = select(func.count()).select_from(TradeRequest)
        req_count_result = await self.session.execute(req_count_stmt)
        total_requests = req_count_result.scalar() or 0

        # Count matches
        match_count_stmt = select(func.count()).select_from(TradeMatch)
        match_count_result = await self.session.execute(match_count_stmt)
        total_matches = match_count_result.scalar() or 0

        # Count agreements
        agree_count_stmt = select(func.count()).select_from(TradeAgreement)
        agree_count_result = await self.session.execute(agree_count_stmt)
        total_agreements = agree_count_result.scalar() or 0

        return {
            "period_type": period_type,
            "total_requests": total_requests,
            "total_matches": total_matches,
            "total_agreements": total_agreements,
            "total_trades": total_requests,
            "completed_trades": total_agreements,
            "total_trade_volume": 0.0,
            "average_trade_value": 0.0,
        }
