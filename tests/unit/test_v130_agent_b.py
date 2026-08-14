"""Unit tests for v0.13.0 Agent B deliverables."""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[2]


def _import_module(module_path: str, package_dir: Path) -> ModuleType:
    """Import a module by adding ``package_dir`` to ``sys.path``."""
    if str(package_dir) not in sys.path:
        sys.path.insert(0, str(package_dir))
    return __import__(module_path, fromlist=["__name__"])


def test_reinvestment_worker_dispatches_and_publishes_capacity() -> None:
    """The worker plans actions and best-effort publishes capacity."""
    reinvestment = _import_module("miner_app.reinvestment", REPO_ROOT / "apps/miner")
    worker_mod = _import_module("miner_app.worker", REPO_ROOT / "apps/miner")
    agent_economics = _import_module("aitbc.agent_economics", REPO_ROOT)

    budget = agent_economics.Budget(budget_id="b1", agent_id="agent-1", chain_id="ait-hub", token="AITBC", total=10)
    policy = reinvestment.ReinvestmentPolicy(staking_contract="0xSTAKE", reserve_address="0xRESERVE")
    engine = reinvestment.ReinvestmentEngine(budget, policy)
    actions = worker_mod.ReinvestmentWorker(
        engine,
        agent_id="agent-1",
        earnings_source=lambda: Decimal("4"),
    ).run_once()
    assert len(actions) == 2


def test_yield_adapter_registry_and_harvest() -> None:
    """The yield registry returns adapters and the demo adapter compounds rewards."""
    ya = _import_module(
        "coordinator_api.contexts.agent_economics.yield_adapter",
        REPO_ROOT / "apps/coordinator-api/src",
    )

    assert "demo_staking" in ya.yield_registry.list_adapters()
    adapter = ya.DemoStakingAdapter(apy=Decimal("10"))
    position = ya.YieldPosition(
        venue=ya.YieldVenue.STAKING,
        agent_id="agent-1",
        principal=Decimal("100"),
        rewards=Decimal("5"),
    )
    harvested = adapter.harvest(position)
    assert harvested == Decimal("5")
    assert position.principal == Decimal("105")
    assert position.rewards == Decimal("0")


def test_risk_circuit_breaker_and_solvency() -> None:
    """Risk stubs compute scores and trip circuit breakers under simulated stress."""
    from datetime import UTC, datetime
    from decimal import Decimal

    from aitbc.risk import CircuitBreaker, CircuitState, MarketStressEvent, SolvencyEngine
    from aitbc.risk.scoring import RiskCategory, RiskScore

    score = RiskScore(entity_id="provider-1", category=RiskCategory.PROVIDER, score=0.85)
    assert score.level.value == "critical"

    breaker = CircuitBreaker(name="market-stress", threshold=Decimal("70"))
    breaker.record(MarketStressEvent(event_id="evt-1", stress_score=Decimal("80"), timestamp=datetime.now(UTC)))
    assert breaker.state == CircuitState.OPEN
    assert not breaker.can_execute()

    engine = SolvencyEngine()
    report = engine.assess("provider-1", Decimal("100"), Decimal("120"))
    assert not report.is_solvent
    assert "liquidate_or_appeal" in report.recommendations
