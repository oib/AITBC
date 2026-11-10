"""
Trading service for managing trading operations
"""

import math
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import and_, func, or_, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from ..domain.trading import (
    NegotiationStatus,
    SettlementType,
    TradeAgreement,
    TradeMatch,
    TradeNegotiation,
    TradeRequest,
    TradeSettlement,
    TradeStatus,
    TradeType,
)

_DEFAULT_SETTLEMENT_TTL_SECONDS = 7 * 24 * 3600


def _settlement_ttl() -> timedelta:
    """Settlement lifetime before a stuck SETTLING row is failed (#1554)."""
    try:
        seconds = int(os.environ.get("TRADE_SETTLEMENT_TTL_SECONDS", str(_DEFAULT_SETTLEMENT_TTL_SECONDS)))
    except (TypeError, ValueError):
        seconds = _DEFAULT_SETTLEMENT_TTL_SECONDS
    return timedelta(seconds=max(60, seconds))


_REQUEST_SERVER_FIELDS = frozenset(
    {
        "id",
        "request_id",
        "status",
        "match_count",
        "negotiation_count",
        "best_match_score",
        "created_at",
        "updated_at",
        "last_activity",
    }
)

_MATCH_SERVER_FIELDS = frozenset(
    {
        "id",
        "match_id",
        "status",
        "created_at",
        "updated_at",
        "last_interaction",
    }
)

_AGREEMENT_SERVER_FIELDS = frozenset(
    {
        "id",
        "agreement_id",
        "status",
        "execution_status",
        "completion_percentage",
        "created_at",
        "updated_at",
        "signed_at",
        "starts_at",
        "ends_at",
        "completed_at",
    }
)

_SETTLEMENT_SERVER_FIELDS = frozenset(
    {
        "id",
        "settlement_id",
        "status",
        "initiated_at",
        "processed_at",
        "completed_at",
        "refunded_at",
        "payment_status",
        "transaction_id",
        "transaction_hash",
        "block_number",
        "dispute_raised",
        "expires_at",
    }
)

# #1562/#1608: legacy P2P rows carried expires_at columns with zero readers.
# The sweep runs lazily on every legacy read path (and once per /v1/transactions
# fetch) — there is no background sweeper in this service. Rows predating the
# TTL fallback (NULL expires_at) use created_at + TTL, matching the
# InterChainTrade lazy-expiry pattern.
_DEFAULT_LEGACY_TTL_SECONDS = 7 * 24 * 3600
_LEGACY_EXPIRABLE_REQUEST_STATUSES = {TradeStatus.OPEN, TradeStatus.MATCHING, TradeStatus.NEGOTIATING}
_LEGACY_EXPIRABLE_MATCH_STATUSES = {TradeStatus.OPEN, TradeStatus.MATCHING, TradeStatus.NEGOTIATING}
_LEGACY_EXPIRABLE_NEGOTIATION_STATUSES = {
    NegotiationStatus.PENDING,
    NegotiationStatus.ACTIVE,
    NegotiationStatus.COUNTERED,
}


def _legacy_ttl() -> timedelta:
    try:
        seconds = int(os.environ.get("TRADING_LEGACY_TTL_SECONDS", str(_DEFAULT_LEGACY_TTL_SECONDS)))
    except (TypeError, ValueError):
        seconds = _DEFAULT_LEGACY_TTL_SECONDS
    return timedelta(seconds=max(60, seconds))


def _utcnow() -> datetime:
    # The legacy DateTime columns are timezone-naive (same convention as
    # InterChainTrade); bind a naive UTC value so sqlite comparisons stay
    # lexicographic-correct.
    return datetime.now(UTC).replace(tzinfo=None)


def _model_or_value_error(model: type, data: dict[str, Any]):
    """Build a SQLModel row, mapping pydantic ValidationError to ValueError.

    The legacy routers accept arbitrary JSON dicts; without this the model's
    ValidationError escaped as an HTTP 500 instead of a client error (#1608).
    """
    try:
        return model(**data)
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc


def _require_str(data: dict[str, Any], key: str) -> None:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")


def _require_enum(data: dict[str, Any], key: str, enum: type) -> None:
    try:
        enum(data.get(key))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} must be one of {[member.value for member in enum]}") from exc


def _require_number(data: dict[str, Any], key: str, low: float, high: float) -> None:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{key} must be a finite number")
    if not low <= float(value) <= high:
        raise ValueError(f"{key} must be between {low} and {high}")


def _optional_decimal(data: dict[str, Any], key: str) -> None:
    if key not in data or data[key] is None:
        return
    try:
        value = Decimal(str(data[key]))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{key} must be a decimal") from exc
    if not value.is_finite() or value < 0:
        raise ValueError(f"{key} must be a finite non-negative decimal")


def _validate_request_data(data: dict[str, Any]) -> None:
    _require_str(data, "buyer_agent_id")
    _require_enum(data, "trade_type", TradeType)
    _require_str(data, "title")
    priority = data.get("priority", 5)
    if isinstance(priority, bool) or not isinstance(priority, int) or not 1 <= priority <= 10:
        raise ValueError("priority must be an integer between 1 and 10")


def _validate_match_data(data: dict[str, Any]) -> None:
    for key in ("request_id", "buyer_agent_id", "seller_agent_id"):
        _require_str(data, key)
    _require_number(data, "match_score", 0, 100)
    _require_number(data, "confidence_level", 0, 1)
    for key in (
        "price_compatibility",
        "timing_compatibility",
        "specification_compatibility",
        "reputation_compatibility",
        "geographic_compatibility",
    ):
        _require_number(data, key, 0, 100)


def _validate_agreement_data(data: dict[str, Any]) -> None:
    for key in ("negotiation_id", "buyer_agent_id", "seller_agent_id", "title"):
        _require_str(data, key)
    _require_enum(data, "trade_type", TradeType)
    _require_enum(data, "settlement_type", SettlementType)
    _optional_decimal(data, "total_price")


def _validate_settlement_data(data: dict[str, Any]) -> None:
    for key in ("agreement_id", "buyer_agent_id", "seller_agent_id"):
        _require_str(data, key)
    _require_enum(data, "settlement_type", SettlementType)
    for key in ("total_amount", "platform_fee", "processing_fee", "gas_fee", "net_amount_seller"):
        _optional_decimal(data, key)


class TradingService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def expire_stale_legacy(self) -> None:
        """#1562: flip expired non-terminal legacy P2P rows on read paths.

        Requests/matches have no ``expired`` TradeStatus, so they land on
        ``cancelled``; negotiations use ``NegotiationStatus.EXPIRED``. NULL
        ``expires_at`` rows fall back to ``created_at + TRADING_LEGACY_TTL_SECONDS``.
        """
        now = _utcnow()
        cutoff = now - _legacy_ttl()
        expired_predicate = or_(
            TradeRequest.expires_at < now,  # type: ignore[operator]
            and_(  # type: ignore[operator]
                TradeRequest.expires_at.is_(None),  # type: ignore[union-attr]
                TradeRequest.created_at < cutoff,  # type: ignore[operator]
            ),
        )
        await self.session.execute(
            update(TradeRequest)
            .where(TradeRequest.status.in_(list(_LEGACY_EXPIRABLE_REQUEST_STATUSES)))  # type: ignore[attr-defined]
            .where(expired_predicate)
            .values(status=TradeStatus.CANCELLED, updated_at=now)
        )

        match_expired_predicate = or_(
            TradeMatch.expires_at < now,  # type: ignore[operator]
            and_(  # type: ignore[operator]
                TradeMatch.expires_at.is_(None),  # type: ignore[union-attr]
                TradeMatch.created_at < cutoff,  # type: ignore[operator]
            ),
        )
        await self.session.execute(
            update(TradeMatch)
            .where(TradeMatch.status.in_(list(_LEGACY_EXPIRABLE_MATCH_STATUSES)))  # type: ignore[attr-defined]
            .where(match_expired_predicate)
            .values(status=TradeStatus.CANCELLED, updated_at=now)
        )

        negotiation_expired_predicate = or_(
            TradeNegotiation.expires_at < now,  # type: ignore[operator]
            and_(  # type: ignore[operator]
                TradeNegotiation.expires_at.is_(None),  # type: ignore[union-attr]
                TradeNegotiation.created_at < cutoff,  # type: ignore[operator]
            ),
        )
        await self.session.execute(
            update(TradeNegotiation)
            .where(TradeNegotiation.status.in_(list(_LEGACY_EXPIRABLE_NEGOTIATION_STATUSES)))  # type: ignore[attr-defined]
            .where(negotiation_expired_predicate)
            .values(status=NegotiationStatus.EXPIRED, updated_at=now)
        )
        await self.session.commit()

    async def list_requests(
        self,
        status: str | None = None,
        buyer_agent_id: str | None = None,
        trade_type: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[TradeRequest]:
        """List trade requests"""
        await self.expire_stale_legacy()
        stmt = select(TradeRequest)
        if status:
            stmt = stmt.where(TradeRequest.status == status)
        if buyer_agent_id:
            stmt = stmt.where(TradeRequest.buyer_agent_id == buyer_agent_id)
        if trade_type:
            stmt = stmt.where(TradeRequest.trade_type == trade_type)
        result = await self.session.execute(stmt.limit(limit).offset(offset))
        return list(result.scalars().all())

    async def get_request(self, request_id: str) -> TradeRequest | None:
        """Get a specific trade request"""
        await self.expire_stale_legacy()
        stmt = select(TradeRequest).where(TradeRequest.request_id == request_id)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def create_request(self, request_data: dict[str, Any]) -> TradeRequest:
        """Create a new trade request"""
        data = {k: v for k, v in request_data.items() if k not in _REQUEST_SERVER_FIELDS}
        data.setdefault("request_id", f"req_{uuid4().hex[:8]}")
        _validate_request_data(data)
        request = _model_or_value_error(TradeRequest, data)
        request.status = TradeStatus.OPEN
        self.session.add(request)
        await self.session.commit()
        await self.session.refresh(request)
        return request

    async def list_matches(
        self,
        status: str | None = None,
        buyer_agent_id: str | None = None,
        seller_agent_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[TradeMatch]:
        """List trade matches"""
        await self.expire_stale_legacy()
        stmt = select(TradeMatch)
        if status:
            stmt = stmt.where(TradeMatch.status == status)
        if buyer_agent_id:
            stmt = stmt.where(TradeMatch.buyer_agent_id == buyer_agent_id)
        if seller_agent_id:
            stmt = stmt.where(TradeMatch.seller_agent_id == seller_agent_id)
        result = await self.session.execute(stmt.limit(limit).offset(offset))
        return list(result.scalars().all())

    async def create_match(self, match_data: dict[str, Any]) -> TradeMatch:
        """Create a new trade match"""
        data = {k: v for k, v in match_data.items() if k not in _MATCH_SERVER_FIELDS}
        data.setdefault("match_id", f"match_{uuid4().hex[:8]}")
        _validate_match_data(data)
        match = _model_or_value_error(TradeMatch, data)
        match.status = TradeStatus.MATCHING
        self.session.add(match)
        await self.session.commit()
        await self.session.refresh(match)
        return match

    async def list_agreements(
        self,
        status: str | None = None,
        buyer_agent_id: str | None = None,
        seller_agent_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[TradeAgreement]:
        """List trade agreements"""
        stmt = select(TradeAgreement)
        if status:
            stmt = stmt.where(TradeAgreement.status == status)
        if buyer_agent_id:
            stmt = stmt.where(TradeAgreement.buyer_agent_id == buyer_agent_id)
        if seller_agent_id:
            stmt = stmt.where(TradeAgreement.seller_agent_id == seller_agent_id)
        result = await self.session.execute(stmt.limit(limit).offset(offset))
        return list(result.scalars().all())

    async def create_agreement(self, agreement_data: dict[str, Any]) -> TradeAgreement:
        """Create a new trade agreement"""
        data = {k: v for k, v in agreement_data.items() if k not in _AGREEMENT_SERVER_FIELDS}
        data.setdefault("agreement_id", f"agree_{uuid4().hex[:8]}")
        _validate_agreement_data(data)
        agreement = _model_or_value_error(TradeAgreement, data)
        agreement.status = TradeStatus.AGREED
        self.session.add(agreement)
        await self.session.commit()
        await self.session.refresh(agreement)
        return agreement

    async def create_settlement(self, settlement_data: dict[str, Any]) -> TradeSettlement:
        """Create a new trade settlement.

        #1554: settlements get a finite lifetime — TRADE_SETTLEMENT_TTL_SECONDS
        (default 7d, mirroring the inter-chain trade TTL). Stale SETTLING rows
        are failed lazily on the next create, the only write path this table
        has.
        """
        await self._expire_stale_settlements()
        data = {k: v for k, v in settlement_data.items() if k not in _SETTLEMENT_SERVER_FIELDS}
        data.setdefault("settlement_id", f"settle_{uuid4().hex[:8]}")
        _validate_settlement_data(data)
        settlement = _model_or_value_error(TradeSettlement, data)
        settlement.status = TradeStatus.SETTLING
        settlement.expires_at = datetime.now(UTC).replace(tzinfo=None) + _settlement_ttl()
        self.session.add(settlement)
        await self.session.commit()
        await self.session.refresh(settlement)
        return settlement

    async def _expire_stale_settlements(self) -> int:
        """Fail SETTLING settlements past expires_at (#1554).

        Lazy, like the inter-chain trade expiry: there is no sweeper in this
        service and create_settlement is the only write path, so the sweep
        runs here. Rows predating the column (NULL expires_at) are left
        alone — no created_at fallback because a settlement legitimately
        waits on counterparty action and there is no safe age guess.
        """
        # Naive UTC like the inter-chain trade expiry — sqlite drops tzinfo
        # and lexicographic comparison needs both sides in the same shape.
        now = datetime.now(UTC).replace(tzinfo=None)
        result = await self.session.execute(
            update(TradeSettlement)
            .where(col(TradeSettlement.status) == TradeStatus.SETTLING)
            .where(col(TradeSettlement.expires_at).is_not(None))
            .where(col(TradeSettlement.expires_at) < now)
            .values(status=TradeStatus.FAILED)
        )
        expired = result.rowcount or 0
        if expired:
            await self.session.commit()
        return expired

    async def get_analytics(self, period_type: str = "daily") -> dict[str, Any]:
        """Get trading analytics"""
        await self.expire_stale_legacy()
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
            # str(Decimal), not float(): these are monetary aggregates on a
            # public reporting endpoint — float() loses precision (#1635).
            "total_trade_volume": str(completed_volume),
            "average_trade_value": str(average_trade_value),
        }
