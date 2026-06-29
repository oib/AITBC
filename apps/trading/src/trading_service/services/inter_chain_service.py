"""Inter-chain trade lifecycle service (v0.8.0 §B5).

Manages the creation, querying, and status tracking of inter-chain trades.
Escrow locking and atomic settlement are deferred to v0.9.0 — v0.8.0
only handles the create → match → agree lifecycle.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ..domain.inter_chain import InterChainTrade

logger = logging.getLogger(__name__)


class InterChainTradeService:
    """Service for managing inter-chain trade lifecycle."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_trade(
        self,
        source_chain: str,
        dest_chain: str,
        sender: str,
        recipient: str,
        amount: int,
        offer_id: str | None = None,
        price: float = 0.0,
        quantity: int = 0,
    ) -> InterChainTrade:
        """Create a new inter-chain trade."""
        trade = InterChainTrade(
            source_chain=source_chain,
            dest_chain=dest_chain,
            sender=sender,
            recipient=recipient,
            amount=amount,
            offer_id=offer_id,
            price=price,
            quantity=quantity,
            status="pending",
        )
        self.session.add(trade)
        await self.session.commit()
        await self.session.refresh(trade)
        logger.info("Created inter-chain trade %s: %s → %s", trade.trade_id, source_chain, dest_chain)
        return trade

    async def get_trade(self, trade_id: str) -> InterChainTrade | None:
        """Get a trade by ID."""
        stmt = select(InterChainTrade).where(InterChainTrade.trade_id == trade_id)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def list_trades(
        self,
        status: str | None = None,
        source_chain: str | None = None,
        dest_chain: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[InterChainTrade]:
        """List trades with optional filters."""
        stmt = select(InterChainTrade)
        if status:
            stmt = stmt.where(InterChainTrade.status == status)
        if source_chain:
            stmt = stmt.where(InterChainTrade.source_chain == source_chain)
        if dest_chain:
            stmt = stmt.where(InterChainTrade.dest_chain == dest_chain)
        stmt = stmt.order_by(InterChainTrade.created_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_trade_status(self, trade_id: str) -> dict[str, Any] | None:
        """Get the status of a trade."""
        trade = await self.get_trade(trade_id)
        if not trade:
            return None
        return {
            "trade_id": trade.trade_id,
            "status": trade.status,
            "source_chain": trade.source_chain,
            "dest_chain": trade.dest_chain,
            "matched_trade_id": trade.matched_trade_id,
            "source_tx_hash": trade.source_tx_hash,
            "dest_tx_hash": trade.dest_tx_hash,
            "updated_at": trade.updated_at.isoformat() if trade.updated_at else None,
        }

    async def update_trade_status(
        self, trade_id: str, status: str, matched_trade_id: str | None = None
    ) -> InterChainTrade | None:
        """Update the status of a trade."""
        trade = await self.get_trade(trade_id)
        if not trade:
            return None
        trade.status = status
        trade.updated_at = datetime.now(UTC)
        if matched_trade_id:
            trade.matched_trade_id = matched_trade_id
        await self.session.commit()
        await self.session.refresh(trade)
        return trade

    async def get_trade_history(
        self,
        source_chain: str | None = None,
        dest_chain: str | None = None,
        limit: int = 50,
    ) -> list[InterChainTrade]:
        """Get trade history across chains.

        Returns completed/cancelled/failed trades, optionally filtered
        by source/dest chain.
        """
        stmt = select(InterChainTrade).where(InterChainTrade.status.in_(["completed", "cancelled", "failed"]))
        if source_chain:
            stmt = stmt.where(InterChainTrade.source_chain == source_chain)
        if dest_chain:
            stmt = stmt.where(InterChainTrade.dest_chain == dest_chain)
        stmt = stmt.order_by(InterChainTrade.updated_at.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
