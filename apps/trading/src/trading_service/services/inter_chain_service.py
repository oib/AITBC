"""Inter-chain trade lifecycle service (v0.8.0 §B5).

Manages the creation, querying, and status tracking of inter-chain trades.
Escrow locking and atomic settlement are deferred to v0.9.0 — v0.8.0
only handles the create → match → agree lifecycle.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, or_, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from aitbc.trading.types import InterChainTradeStatus

from ..domain.inter_chain import InterChainTrade

logger = logging.getLogger(__name__)

_TERMINAL_TRADE_STATUSES = {
    InterChainTradeStatus.COMPLETED,
    InterChainTradeStatus.CANCELLED,
    InterChainTradeStatus.FAILED,
}

# #1562: pending trades get a finite lifetime — INTER_CHAIN_TRADE_TTL_SECONDS
# (default 7d). Naive UTC datetimes match how the column is written below and
# keep sqlite comparisons lexicographic-correct.
_DEFAULT_TRADE_TTL_SECONDS = 7 * 24 * 3600


def _trade_ttl() -> timedelta:
    try:
        seconds = int(os.environ.get("INTER_CHAIN_TRADE_TTL_SECONDS", str(_DEFAULT_TRADE_TTL_SECONDS)))
    except (TypeError, ValueError):
        seconds = _DEFAULT_TRADE_TTL_SECONDS
    return timedelta(seconds=max(60, seconds))


def _utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


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
        price: Decimal = Decimal("0"),
        quantity: int = 0,
    ) -> InterChainTrade:
        """Create a new inter-chain trade.

        #1553: a retried create with identical terms replays the existing
        pending trade instead of stacking a duplicate that could reach
        escrow/settlement twice. The natural key is the full term set —
        two genuinely different trades differ in at least one field.
        """
        now = _utcnow_naive()
        existing_stmt = select(InterChainTrade).where(
            InterChainTrade.status == "pending",  # type: ignore[arg-type]
            InterChainTrade.source_chain == source_chain,
            InterChainTrade.dest_chain == dest_chain,
            InterChainTrade.sender == sender,
            InterChainTrade.recipient == recipient,
            InterChainTrade.amount == amount,
            InterChainTrade.offer_id == offer_id,
            InterChainTrade.price == price,
            InterChainTrade.quantity == quantity,
            or_(  # type: ignore[operator]
                InterChainTrade.expires_at.is_(None),  # type: ignore[union-attr]
                InterChainTrade.expires_at > now,  # type: ignore[operator]
            ),
        )
        existing = (await self.session.execute(existing_stmt)).scalars().first()
        if existing is not None:
            logger.info("Replaying existing inter-chain trade %s for identical create", existing.trade_id)
            return existing

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
            expires_at=_utcnow_naive() + _trade_ttl(),
        )
        self.session.add(trade)
        await self.session.commit()
        await self.session.refresh(trade)
        logger.info("Created inter-chain trade %s: %s → %s", trade.trade_id, source_chain, dest_chain)
        return trade

    async def _expire_stale_pending(self) -> int:
        """#1562 lazy expiry: pending trades past expires_at become 'cancelled'.

        Runs on the read paths (list/get/history) — there is no background
        sweeper in this service. Rows predating the column (NULL expires_at)
        fall back to created_at + TTL. Returns the number of rows expired.
        """
        now = _utcnow_naive()
        # Rows predating the expires_at column (NULL) fall back to
        # created_at + TTL so legacy pending trades still expire.
        cutoff = now - _trade_ttl()
        result = await self.session.execute(
            update(InterChainTrade)
            .where(
                InterChainTrade.status == "pending",  # type: ignore[arg-type]
                or_(  # type: ignore[operator]
                    InterChainTrade.expires_at < now,  # type: ignore[operator]
                    and_(  # type: ignore[operator]
                        InterChainTrade.expires_at.is_(None),  # type: ignore[union-attr]
                        InterChainTrade.created_at < cutoff,  # type: ignore[operator]
                    ),
                ),
            )
            .values(status="cancelled", updated_at=now)
        )
        expired = result.rowcount or 0
        if expired:
            await self.session.commit()
            logger.info("Expired %d stale pending inter-chain trade(s)", expired)
        return expired

    async def get_trade(self, trade_id: str) -> InterChainTrade | None:
        """Get a trade by ID."""
        await self._expire_stale_pending()
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
        """List trades with optional filters.

        ``limit``/``offset`` are clamped — a negative limit would otherwise
        reach ``.limit()`` as SQLite "unlimited" (#1543).
        """
        await self._expire_stale_pending()
        limit = min(max(int(limit), 1), 500)
        offset = max(int(offset), 0)
        stmt = select(InterChainTrade)
        if status:
            stmt = stmt.where(InterChainTrade.status == status)
        if source_chain:
            stmt = stmt.where(InterChainTrade.source_chain == source_chain)
        if dest_chain:
            stmt = stmt.where(InterChainTrade.dest_chain == dest_chain)
        stmt = stmt.order_by(InterChainTrade.created_at.desc())  # type: ignore[attr-defined]
        stmt = stmt.limit(limit).offset(offset)
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
        # #1416: validate against InterChainTradeStatus and refuse writes out
        # of terminal states (completed/cancelled/failed) — any string used to
        # be persisted verbatim.
        try:
            new_status = InterChainTradeStatus(status)
        except ValueError:
            logger.warning("update_trade_status: invalid status %r for trade %s", status, trade_id)
            return None
        try:
            current_status = InterChainTradeStatus(trade.status)
        except ValueError:
            current_status = None
        if current_status in _TERMINAL_TRADE_STATUSES and new_status != current_status:
            logger.warning(
                "update_trade_status: refusing %s -> %s on terminal trade %s",
                current_status.value,
                new_status.value,
                trade_id,
            )
            return None
        trade.status = new_status.value
        trade.updated_at = datetime.now(UTC)
        if matched_trade_id:
            trade.matched_trade_id = matched_trade_id
        await self.session.commit()
        await self.session.refresh(trade)
        return trade

    async def cancel_trade(self, trade_id: str) -> InterChainTrade | None:
        """Cancel a pending inter-chain trade (#1562).

        Only ``pending`` trades may be cancelled here: a ``matched`` trade may
        already have an escrow/settlement in flight on the counterparty side,
        so cancelling it locally would strand the pair — that path needs the
        settlement lifecycle's own cancel/refund transitions (residual).
        """
        trade = await self.get_trade(trade_id)
        if not trade:
            return None
        if trade.status != InterChainTradeStatus.PENDING.value:
            logger.warning("cancel_trade: refusing to cancel trade %s in status %r", trade_id, trade.status)
            return trade
        trade.status = InterChainTradeStatus.CANCELLED.value
        trade.updated_at = datetime.now(UTC)
        await self.session.commit()
        await self.session.refresh(trade)
        logger.info("Cancelled inter-chain trade %s", trade_id)
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
        await self._expire_stale_pending()
        limit = min(max(int(limit), 1), 500)
        stmt = select(InterChainTrade).where(InterChainTrade.status.in_(["completed", "cancelled", "failed"]))  # type: ignore[attr-defined]
        if source_chain:
            stmt = stmt.where(InterChainTrade.source_chain == source_chain)
        if dest_chain:
            stmt = stmt.where(InterChainTrade.dest_chain == dest_chain)
        stmt = stmt.order_by(InterChainTrade.updated_at.desc()).limit(limit)  # type: ignore[attr-defined]
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
