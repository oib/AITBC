"""Risk scoring for chains, validators, and storage providers (v0.13.0 §A3).

Supports both individual ``RiskScore`` values (0–1) and a weighted
``RiskScorer`` that maps per-factor inputs into an aggregate score.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any

from .errors import RiskError


class RiskLevel(StrEnum):
    """Discrete risk levels."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RiskCategory(StrEnum):
    """Categories of risk that can be scored."""

    CHAIN = "chain"
    VALIDATOR = "validator"
    STORAGE = "storage"
    PROVIDER = "provider"
    TOKEN = "token"


@dataclass
class RiskScore:
    """Numeric and categorical risk score for an entity.

    ``score`` is a float between 0 and 1. The risk ``level`` is derived
    automatically from the score unless explicitly supplied.
    """

    entity_id: str
    category: RiskCategory | str
    score: float
    level: RiskLevel | str = RiskLevel.LOW
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.category, str):
            self.category = RiskCategory(self.category)
        if isinstance(self.level, str):
            self.level = RiskLevel(self.level)
        if not 0 <= self.score <= 1:
            raise ValueError("score must be between 0 and 1")
        if self.score >= 0.8:
            self.level = RiskLevel.CRITICAL
        elif self.score >= 0.6:
            self.level = RiskLevel.HIGH
        elif self.score >= 0.3:
            self.level = RiskLevel.MEDIUM
        else:
            self.level = RiskLevel.LOW

    @property
    def is_critical(self) -> bool:
        return self.level == RiskLevel.CRITICAL


@dataclass
class RiskScorer:
    """Configurable weighted risk scorer and aggregate calculator.

    When ``weights`` is provided, ``assess`` normalizes the weights, applies
    them to factor values (each 0–100), and returns a ``RiskScore``.
    When ``weights`` is omitted, the scorer acts as an aggregator over scores
    added with ``add``.
    """

    weights: dict[str, Decimal] = field(default_factory=dict)
    scores: dict[str, RiskScore] = field(default_factory=dict)

    def __post_init__(self) -> None:
        total = sum(self.weights.values(), Decimal("0"))
        if self.weights and total <= 0:
            raise RiskError("weights must sum to a positive value")
        self._normalized = (
            {name: (weight / total) * Decimal("100") for name, weight in self.weights.items()} if self.weights else {}
        )

    def add(self, score: RiskScore) -> None:
        """Add or replace a score by entity id."""
        self.scores[score.entity_id] = score

    def aggregate(self, entity_ids: list[str] | None = None) -> float:
        """Return the average score for the selected entities."""
        scores = list(self.scores.values())
        if entity_ids:
            scores = [s for s in scores if s.entity_id in entity_ids]
        if not scores:
            return 0.0
        return round(sum(s.score for s in scores) / len(scores), 10)

    def assess(
        self,
        entity_id: str,
        category: RiskCategory | str,
        factors: dict[str, Decimal],
    ) -> RiskScore:
        """Compute a ``RiskScore`` from raw factor values (0–100 each)."""
        if not self._normalized:
            raise RiskError("no weights configured for RiskScorer.assess")
        if isinstance(category, str):
            category = RiskCategory(category)
        unknown = set(factors.keys()) - set(self._normalized.keys())
        if unknown:
            raise RiskError(f"unknown factors for scorer: {sorted(unknown)}")

        score = Decimal("0")
        for name, value in factors.items():
            if value < 0 or value > 100:
                raise ValueError(f"factor {name} must be between 0 and 100")
            score += self._normalized[name] * (value / Decimal("100"))

        score_float = float(min(max(score, Decimal("0")), Decimal("100")) / Decimal("100"))
        return RiskScore(
            entity_id=entity_id,
            category=category,
            score=score_float,
        )
