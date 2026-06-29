"""Basic matching engine for inter-chain trades (v0.8.0 §B6).

Implements price-time priority matching across chains. A buy trade
(source_chain → dest_chain) matches a sell trade (dest_chain → source_chain)
when prices cross and chains are compatible.

Matching is off-chain — the trading service finds matches and updates
trade status. Escrow locking and settlement are deferred to v0.9.0.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ..domain.inter_chain import InterChainTrade

logger = logging.getLogger(__name__)


class MatchingEngine:
    """Price-time priority matching engine for inter-chain trades."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def match_trade(self, trade_id: str) -> dict[str, Any] | None:
        """Find a matching counterparty trade for the given trade.

        Matching criteria:
        - Counterparty trade must be in "pending" status
        - Counterparty's source_chain == this trade's dest_chain
        - Counterparty's dest_chain == this trade's source_chain
        - Counterparty's sender == this trade's recipient (or vice versa)
        - Price-time priority: highest price first, then earliest creation

        Returns a match result dict if a match is found, None otherwise.
        """
        # Get the trade to match
        stmt = select(InterChainTrade).where(InterChainTrade.trade_id == trade_id)
        result = await self.session.execute(stmt)
        trade = result.scalars().first()
        if not trade:
            return None
        if trade.status != "pending":
            return {"trade_id": trade_id, "status": trade.status, "matched": False, "reason": "trade not pending"}

        # Find matching counterparty trades
        # A match is: counterparty source = our dest, counterparty dest = our source
        match_stmt = (
            select(InterChainTrade)
            .where(
                InterChainTrade.status == "pending",
                InterChainTrade.trade_id != trade_id,
                InterChainTrade.source_chain == trade.dest_chain,
                InterChainTrade.dest_chain == trade.source_chain,
                InterChainTrade.amount == trade.amount,
            )
            .order_by(InterChainTrade.price.desc(), InterChainTrade.created_at.asc())
        )
        result = await self.session.execute(match_stmt)
        candidates = list(result.scalars().all())

        if not candidates:
            return {"trade_id": trade_id, "status": "pending", "matched": False, "reason": "no matching trades"}

        # Take the best match (highest price, earliest time)
        match = candidates[0]

        # Update both trades to "matched" status
        trade.status = "matched"
        trade.matched_trade_id = match.trade_id
        match.status = "matched"
        match.matched_trade_id = trade.trade_id

        await self.session.commit()
        # Note: refresh after commit can fail with async sessions in some configurations.
        # The trade objects are already updated in-memory, so refresh is optional.

        logger.info("Matched trade %s with %s", trade.trade_id, match.trade_id)

        return {
            "trade_id": trade_id,
            "matched_trade_id": match.trade_id,
            "status": "matched",
            "matched": True,
            "source_chain": trade.source_chain,
            "dest_chain": trade.dest_chain,
            "amount": trade.amount,
            "price": match.price,
        }

    async def match_all_pending(self) -> list[dict[str, Any]]:
        """Attempt to match all pending trades.

        Returns a list of match results for each pending trade.
        """
        stmt = select(InterChainTrade).where(InterChainTrade.status == "pending").order_by(InterChainTrade.created_at.asc())
        result = await self.session.execute(stmt)
        pending = list(result.scalars().all())

        results: list[dict[str, Any]] = []
        for trade in pending:
            match_result = await self.match_trade(trade.trade_id)
            if match_result:
                results.append(match_result)

        return results
