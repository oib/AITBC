"""Bond shortfall prediction and action recommendations (v0.13.0 §A3).

Provides ``SolvencyReport`` and ``SolvencyEngine``. The engine consumes
portfolio/bond state from ``aitbc.agent_economics`` and optionally
``RiskScore`` values from ``aitbc.risk.scoring``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from aitbc.agent_economics import PerformanceBond

from .scoring import RiskLevel, RiskScore


@dataclass
class SolvencyReport:
    """Snapshot of an entity's solvency."""

    entity_id: str
    assets: Decimal = Decimal("0")
    liabilities: Decimal = Decimal("0")
    bond_requirements: Decimal = Decimal("0")
    recommendations: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def surplus(self) -> Decimal:
        """Return assets minus liabilities and bond requirements."""
        return self.assets - self.liabilities - self.bond_requirements

    @property
    def shortfall(self) -> Decimal:
        """Amount by which obligations exceed assets."""
        return -self.surplus if self.surplus < 0 else Decimal("0")

    @property
    def is_solvent(self) -> bool:
        """Return True if assets cover liabilities and bond requirements."""
        return self.surplus >= 0

    @property
    def healthy(self) -> bool:
        """Return True if solvent and no critical risk scores attached."""
        return self.is_solvent


@dataclass
class SolvencyEngine:
    """Predict shortfalls and recommend actions for bonds and stakes."""

    stress_buffer: Decimal = Decimal("0.1")
    min_collateral_ratio: Decimal = Decimal("1.0")

    def __post_init__(self) -> None:
        if self.stress_buffer < 0:
            raise ValueError("stress_buffer cannot be negative")
        if self.min_collateral_ratio <= 0:
            raise ValueError("min_collateral_ratio must be positive")

    def assess(
        self,
        entity_id: str,
        assets: Decimal,
        liabilities: Decimal,
        bonds: list[PerformanceBond] | None = None,
        risk_scores: list[RiskScore] | None = None,
    ) -> SolvencyReport:
        """Assess solvency and recommend actions if under stress."""
        if assets < 0:
            raise ValueError("assets cannot be negative")
        if liabilities < 0:
            raise ValueError("liabilities cannot be negative")

        bonds = bonds or []
        risk_scores = risk_scores or []

        bond_requirements = sum((b.amount for b in bonds), Decimal("0"))
        total_obligations = liabilities + bond_requirements
        required_assets = total_obligations * (Decimal("1") + self.stress_buffer) * self.min_collateral_ratio

        recommendations: list[str] = []
        if assets < required_assets:
            recommendations.append("top_up_bond")
        if assets < total_obligations:
            recommendations.append("liquidate_or_appeal")
        for score in risk_scores:
            if score.level in {RiskLevel.HIGH, RiskLevel.CRITICAL}:
                recommendations.append(f"review {score.category} {score.entity_id}: risk {score.level}")

        report = SolvencyReport(
            entity_id=entity_id,
            assets=assets,
            liabilities=liabilities,
            bond_requirements=bond_requirements,
            recommendations=recommendations,
        )
        return report
