"""Portfolio tracking shared types for AITBC (v0.13.0 §A1).

Provides a lightweight ``Portfolio`` aggregate over ``ChainHoldings`` with
valuation, allocation percentages, and rebalance detection.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from .rebalance import ChainHoldings


@dataclass
class Portfolio:
    """Snapshot of an agent's holdings across chains and tokens."""

    portfolio_id: str
    agent_id: str
    positions: list[ChainHoldings] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.agent_id:
            raise ValueError("agent_id is required")

    @property
    def total_value(self) -> Decimal:
        """Sum of all position amounts."""
        return sum((p.amount for p in self.positions), Decimal("0"))

    def allocation(self, chain_id: str, token: str) -> Decimal:
        """Return the percentage allocation for a chain/token pair."""
        total = self.total_value
        if total == 0:
            return Decimal("0")
        position_total = sum(
            (p.amount for p in self.positions if p.chain_id == chain_id and p.token == token),
            Decimal("0"),
        )
        return (position_total / total) * Decimal("100")

    def deviations(self) -> dict[tuple[str, str], Decimal]:
        """Map each chain/token pair to (current % - target %)."""
        result: dict[tuple[str, str], Decimal] = {}
        for p in self.positions:
            key = (p.chain_id, p.token)
            current = self.allocation(p.chain_id, p.token)
            result[key] = current - p.target_percent
        return result

    def add_position(self, position: ChainHoldings) -> None:
        """Add a new position or update an existing one."""
        existing = next(
            (p for p in self.positions if p.chain_id == position.chain_id and p.token == position.token),
            None,
        )
        if existing:
            existing.amount += position.amount
            existing.current_percent = (
                Decimal("0") if self.total_value == 0 else (existing.amount / self.total_value) * Decimal("100")
            )
        else:
            self.positions.append(position)

    def rebalance_needed(self, threshold: Decimal | None = None) -> list[ChainHoldings]:
        """Return positions whose current/target deviation exceeds ``threshold``."""
        if threshold is None:
            threshold = Decimal("5")
        deviations = self.deviations()
        return [p for p in self.positions if abs(deviations.get((p.chain_id, p.token), Decimal("0"))) > threshold]
