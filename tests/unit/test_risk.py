"""Unit tests for aitbc.risk scoring, solvency, and circuit breaker (v0.13.0 §A3)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from aitbc.agent_economics import PerformanceBond
from aitbc.risk import (
    CircuitBreaker,
    CircuitState,
    MarketStressEvent,
    RiskCategory,
    RiskError,
    RiskLevel,
    RiskScore,
    RiskScorer,
    SolvencyEngine,
)


def test_risk_score_level() -> None:
    score = RiskScore(
        entity_id="provider-1",
        category=RiskCategory.PROVIDER,
        score=0.85,
    )
    assert score.level == RiskLevel.CRITICAL


def test_risk_score_invalid_range() -> None:
    with pytest.raises(ValueError):
        RiskScore(
            entity_id="provider-1",
            category=RiskCategory.PROVIDER,
            score=1.5,
        )


def test_risk_scorer_assess() -> None:
    scorer = RiskScorer(
        weights={
            "latency": Decimal("1"),
            "downtime": Decimal("2"),
            "missed_proofs": Decimal("1"),
        }
    )
    score = scorer.assess(
        entity_id="val-1",
        category=RiskCategory.VALIDATOR,
        factors={
            "latency": Decimal("10"),
            "downtime": Decimal("80"),
            "missed_proofs": Decimal("50"),
        },
    )
    assert score.category == RiskCategory.VALIDATOR
    assert 0 <= score.score <= 1
    assert score.level in {RiskLevel.MEDIUM, RiskLevel.HIGH}


def test_risk_scorer_unknown_factor() -> None:
    scorer = RiskScorer(weights={"latency": Decimal("1")})
    with pytest.raises(RiskError):
        scorer.assess(
            entity_id="val-1",
            category=RiskCategory.VALIDATOR,
            factors={"unknown": Decimal("50")},
        )


def test_risk_scorer_aggregate() -> None:
    scorer = RiskScorer()
    scorer.add(RiskScore("p1", RiskCategory.PROVIDER, 0.4))
    scorer.add(RiskScore("p2", RiskCategory.PROVIDER, 0.8))
    assert scorer.aggregate() == pytest.approx(0.6)


def test_solvency_report_healthy() -> None:
    engine = SolvencyEngine(min_collateral_ratio=Decimal("1.0"))
    bond = PerformanceBond(
        bond_id="b1",
        agent_id="agent-a",
        amount=Decimal("100"),
        token="AITBC",
    )
    report = engine.assess(
        entity_id="agent-a",
        assets=Decimal("500"),
        liabilities=Decimal("100"),
        bonds=[bond],
    )
    assert report.healthy is True
    assert report.shortfall == Decimal("0")


def test_solvency_report_shortfall() -> None:
    engine = SolvencyEngine(
        min_collateral_ratio=Decimal("1.5"),
        stress_buffer=Decimal("0.1"),
    )
    bond = PerformanceBond(
        bond_id="b1",
        agent_id="agent-a",
        amount=Decimal("100"),
        token="AITBC",
    )
    report = engine.assess(
        entity_id="agent-a",
        assets=Decimal("100"),
        liabilities=Decimal("100"),
        bonds=[bond],
    )
    assert report.healthy is False
    assert report.shortfall > Decimal("0")
    assert any("top_up_bond" in rec for rec in report.recommendations)


def test_solvency_report_insolvent_recommends_liquidation() -> None:
    engine = SolvencyEngine()
    report = engine.assess(
        entity_id="provider-1",
        assets=Decimal("100"),
        liabilities=Decimal("120"),
    )
    assert not report.is_solvent
    assert "liquidate_or_appeal" in report.recommendations


def test_circuit_breaker_opens_on_stress() -> None:
    breaker = CircuitBreaker(name="market", threshold=Decimal("80"))
    assert breaker.can_execute() is True
    breaker.record(MarketStressEvent(event_id="e1", stress_score=Decimal("90")))
    assert breaker.state == CircuitState.OPEN
    assert breaker.is_open()


def test_circuit_breaker_opens_on_severity_fraction() -> None:
    breaker = CircuitBreaker(name="market", threshold=Decimal("0.7"))
    breaker.record(MarketStressEvent(metric="volatility", severity=Decimal("0.8")))
    assert breaker.is_open()


def test_circuit_breaker_half_open_recovery() -> None:
    now = datetime.now(UTC)
    breaker = CircuitBreaker(
        name="market",
        threshold=Decimal("80"),
        recovery_timeout=timedelta(seconds=1),
    )
    breaker.record(MarketStressEvent(event_id="e1", stress_score=Decimal("90")), now=now)
    assert breaker.state == CircuitState.OPEN
    after = now + timedelta(seconds=2)
    assert breaker.can_execute(now=after) is True
    assert breaker.state == CircuitState.HALF_OPEN


def test_circuit_breaker_reopens_on_half_open_failure() -> None:
    now = datetime.now(UTC)
    breaker = CircuitBreaker(
        name="market",
        threshold=Decimal("80"),
        recovery_timeout=timedelta(seconds=1),
    )
    breaker.record(MarketStressEvent(event_id="e1", stress_score=Decimal("90")), now=now)
    after = now + timedelta(seconds=2)
    breaker.can_execute(now=after)
    breaker.record(MarketStressEvent(event_id="e2", stress_score=Decimal("95")), now=after)
    assert breaker.state == CircuitState.OPEN
