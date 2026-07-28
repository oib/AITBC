"""Cross-chain AITBC swap abstractions (v0.13.0 §A4).

Provides ``SwapRoute``, ``CrossChainSwap``, and ``SwapQuote`` primitives plus a
simple ``quote_swap`` helper for planning cross-chain AITBC transfers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Any

from .errors import SwapError


class SwapStatus(StrEnum):
    """Lifecycle status of a cross-chain swap."""

    PENDING = "pending"
    QUOTED = "quoted"
    EXECUTED = "executed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class SwapRoute:
    """A single leg of a cross-chain swap."""

    source_chain: str
    target_chain: str
    token: str
    amount: Decimal
    expected_output: Decimal
    fees: Decimal = field(default_factory=lambda: Decimal("0"))
    slippage_percent: Decimal = field(default_factory=lambda: Decimal("0"))
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.amount < 0:
            raise ValueError("amount cannot be negative")
        if self.expected_output < 0:
            raise ValueError("expected_output cannot be negative")
        if self.fees < 0:
            raise ValueError("fees cannot be negative")
        if not (Decimal("0") <= self.slippage_percent <= Decimal("100")):
            raise ValueError("slippage_percent must be between 0 and 100")

    @property
    def net_output(self) -> Decimal:
        """Output after fees, before slippage."""
        return self.expected_output - self.fees


@dataclass
class SwapQuote:
    """Aggregated quote for a cross-chain swap."""

    quote_id: str
    agent_id: str
    routes: list[SwapRoute]
    expiry: datetime = field(default_factory=lambda: datetime.now(UTC) + timedelta(minutes=5))
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.agent_id:
            raise ValueError("agent_id is required")

    @property
    def total_amount(self) -> Decimal:
        return sum((r.amount for r in self.routes), Decimal("0"))

    @property
    def total_expected_output(self) -> Decimal:
        return sum((r.expected_output for r in self.routes), Decimal("0"))

    @property
    def total_fees(self) -> Decimal:
        return sum((r.fees for r in self.routes), Decimal("0"))

    @property
    def total_net_output(self) -> Decimal:
        return sum((r.net_output for r in self.routes), Decimal("0"))


@dataclass
class CrossChainSwap:
    """Planned or in-progress cross-chain AITBC swap."""

    swap_id: str
    agent_id: str
    routes: list[SwapRoute] = field(default_factory=list)
    status: SwapStatus | str = SwapStatus.PENDING
    quote: SwapQuote | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    executed_at: datetime | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.status, str):
            self.status = SwapStatus(self.status)
        if not self.agent_id:
            raise ValueError("agent_id is required")

    def add_route(self, route: SwapRoute) -> None:
        """Add a route to the swap."""
        if self.status != SwapStatus.PENDING:
            raise SwapError(f"cannot add route to swap in status {self.status}")
        self.routes.append(route)

    def set_quote(self, quote: SwapQuote) -> None:
        """Attach a quote and transition to quoted status."""
        if self.status != SwapStatus.PENDING:
            raise SwapError(f"cannot set quote on swap in status {self.status}")
        if quote.agent_id != self.agent_id:
            raise SwapError("quote agent_id does not match swap")
        self.quote = quote
        self.status = SwapStatus.QUOTED

    def execute(self, now: datetime | None = None) -> None:
        """Mark the swap as executed."""
        if now is None:
            now = datetime.now(UTC)
        if self.status != SwapStatus.QUOTED:
            raise SwapError(f"cannot execute swap in status {self.status}")
        if self.quote is not None and self.quote.expiry < now:
            raise SwapError("swap quote has expired")
        self.status = SwapStatus.EXECUTED
        self.executed_at = now

    def cancel(self) -> None:
        """Cancel a pending or quoted swap."""
        if self.status not in {SwapStatus.PENDING, SwapStatus.QUOTED}:
            raise SwapError(f"cannot cancel swap in status {self.status}")
        self.status = SwapStatus.CANCELLED


def quote_swap(
    quote_id: str,
    agent_id: str,
    routes: list[SwapRoute],
) -> SwapQuote:
    """Build a ``SwapQuote`` from a list of routes."""
    return SwapQuote(
        quote_id=quote_id,
        agent_id=agent_id,
        routes=list(routes),
    )
