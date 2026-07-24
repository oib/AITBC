"""AITBC risk and solvency shared types (v0.13.0 §A3).

Provides:
- Risk scoring for chains, validators, and storage providers
- Solvency engine for predicting bond shortfalls and action recommendations
- Market-stress circuit breakers for autonomous actions
"""

from __future__ import annotations

from .circuit_breaker import CircuitBreaker, CircuitState, MarketStressEvent
from .errors import RiskError
from .scoring import RiskCategory, RiskLevel, RiskScore, RiskScorer
from .solvency import SolvencyEngine, SolvencyReport

__all__ = [
    "CircuitBreaker",
    "CircuitState",
    "MarketStressEvent",
    "RiskCategory",
    "RiskError",
    "RiskLevel",
    "RiskScore",
    "RiskScorer",
    "SolvencyEngine",
    "SolvencyReport",
]
