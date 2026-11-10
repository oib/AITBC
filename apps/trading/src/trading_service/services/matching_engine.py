"""Basic matching engine for inter-chain trades (v0.8.0 §B6).

Implements price-time priority matching across chains. A buy trade
(source_chain → dest_chain) matches a sell trade (dest_chain → source_chain)
when prices cross and chains are compatible.

Matching is off-chain — the trading service finds matches and updates
trade status. Escrow locking and settlement are deferred to v0.9.0.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, or_, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ..domain.inter_chain import InterChainTrade

logger = logging.getLogger(__name__)

_DEFAULT_TRADE_TTL_SECONDS = 7 * 24 * 3600


def _utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def _expire_stale_pending(session: AsyncSession) -> None:
    """#1562: pending trades past expires_at must not match — flip them to
    'cancelled' before candidate selection. Mirrors the lazy expiry in
    InterChainTradeService; the engine gets its own session dependency."""
    try:
        ttl = int(os.environ.get("INTER_CHAIN_TRADE_TTL_SECONDS", str(_DEFAULT_TRADE_TTL_SECONDS)))
    except (TypeError, ValueError):
        ttl = _DEFAULT_TRADE_TTL_SECONDS
    # expires_at is stamped at create time; trades older than the TTL that
    # somehow lack the column value fall back to created_at + TTL.
    cutoff = _utcnow_naive() - timedelta(seconds=max(60, ttl))
    result = await session.execute(
        update(InterChainTrade)
        .where(
            InterChainTrade.status == "pending",  # type: ignore[arg-type]
            or_(  # type: ignore[operator]
                InterChainTrade.expires_at < _utcnow_naive(),  # type: ignore[operator]
                and_(  # type: ignore[operator]
                    InterChainTrade.expires_at.is_(None),  # type: ignore[union-attr]
                    InterChainTrade.created_at < cutoff,  # type: ignore[operator]
                ),
            ),
        )
        .values(status="cancelled", updated_at=_utcnow_naive())
    )
    if result.rowcount:
        await session.commit()
        logger.info("Expired %d stale pending trade(s) before matching", result.rowcount)


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
        await _expire_stale_pending(self.session)
        # Get the trade to match (lock for update to prevent concurrent matching)
        stmt = select(InterChainTrade).where(InterChainTrade.trade_id == trade_id)
        result = await self.session.execute(stmt.with_for_update())
        trade = result.scalars().first()
        if not trade:
            return None
        if trade.status != "pending":
            return {"trade_id": trade_id, "status": trade.status, "matched": False, "reason": "trade not pending"}

        # Find matching counterparty trades (lock for update to prevent double-matching)
        # A match is: counterparty source = our dest, counterparty dest = our source
        # Documented party criterion (#1413): the counterparty must involve
        # the same two parties — either mirrored (its sender is our recipient
        # and vice versa) or identical ordering. Without this, unrelated
        # trades between the same chains with equal amount get matched.
        party_match = or_(
            and_(
                InterChainTrade.sender == trade.recipient,
                InterChainTrade.recipient == trade.sender,
            ),
            and_(
                InterChainTrade.sender == trade.sender,
                InterChainTrade.recipient == trade.recipient,
            ),
        )
        match_stmt = (
            select(InterChainTrade)
            .where(
                InterChainTrade.status == "pending",
                InterChainTrade.trade_id != trade_id,
                InterChainTrade.source_chain == trade.dest_chain,
                InterChainTrade.dest_chain == trade.source_chain,
                InterChainTrade.amount == trade.amount,
                party_match,
            )
            .order_by(InterChainTrade.price.desc(), InterChainTrade.created_at.asc())  # type: ignore[attr-defined]
            .with_for_update()
        )
        result = await self.session.execute(match_stmt)
        candidates = list(result.scalars().all())

        if not candidates:
            return {"trade_id": trade_id, "status": "pending", "matched": False, "reason": "no matching trades"}

        # Take the best match (highest price, earliest time)
        match = candidates[0]

        # Capture response fields before commit — expire_on_commit=True
        # expires ORM attrs, and post-commit reads raise MissingGreenlet.
        resp = {
            "trade_id": trade_id,
            "matched_trade_id": match.trade_id,
            "status": "matched",
            "matched": True,
            "source_chain": trade.source_chain,
            "dest_chain": trade.dest_chain,
            "amount": trade.amount,
            "price": match.price,
        }

        # #1562: claim BOTH trades with guarded UPDATEs — SELECT ... FOR
        # UPDATE is a no-op on sqlite, the default backend, so two concurrent
        # match_trade calls could both read the same counterparty as 'pending'
        # and match it twice. The WHERE status='pending' recheck makes the
        # claim atomic: whichever transaction commits first wins, the loser
        # sees rowcount 0 and rolls back both sides of the pair.
        now = _utcnow_naive()
        claim_self = await self.session.execute(
            update(InterChainTrade)
            .where(
                InterChainTrade.trade_id == trade_id,  # type: ignore[arg-type]
                InterChainTrade.status == "pending",  # type: ignore[arg-type]
            )
            .values(status="matched", matched_trade_id=match.trade_id, updated_at=now)
        )
        claim_match = await self.session.execute(
            update(InterChainTrade)
            .where(
                InterChainTrade.trade_id == match.trade_id,  # type: ignore[arg-type]
                InterChainTrade.status == "pending",  # type: ignore[arg-type]
            )
            .values(status="matched", matched_trade_id=trade_id, updated_at=now)
        )
        if (claim_self.rowcount or 0) != 1 or (claim_match.rowcount or 0) != 1:
            await self.session.rollback()
            logger.info("Match for trade %s lost a concurrent claim race", trade_id)
            return {
                "trade_id": trade_id,
                "status": "pending",
                "matched": False,
                "reason": "counterparty already matched concurrently",
            }
        await self.session.commit()

        logger.info("Matched trade %s with %s", trade_id, resp["matched_trade_id"])

        return resp

    async def match_all_pending(self) -> list[dict[str, Any]]:
        """Attempt to match all pending trades.

        Returns a list of match results for each pending trade.
        """
        stmt = select(InterChainTrade).where(InterChainTrade.status == "pending").order_by(InterChainTrade.created_at.asc())  # type: ignore[attr-defined]
        result = await self.session.execute(stmt)
        pending = list(result.scalars().all())

        results: list[dict[str, Any]] = []
        for trade in pending:
            match_result = await self.match_trade(trade.trade_id)
            if match_result:
                results.append(match_result)

        return results
