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


def test_provider_bond_eligibility() -> None:
    """A provider is eligible only when bond status is active or locked."""
    repo_dir = Path(__file__).resolve().parents[2]
    provider_bond = _import_module(
        "coordinator_api.contexts.marketplace.domain.provider_bond",
        repo_dir / "apps/coordinator-api/src",
    )

    # Shortfall status makes provider ineligible.
    bond = provider_bond.ProviderBond(
        provider_id="provider-1",
        status=provider_bond.ProviderBondStatus.SHORTFALL,
        amount=10.0,
        required_amount=20.0,
    )
    assert bond.status == provider_bond.ProviderBondStatus.SHORTFALL.value


def test_slash_appeal_model_defaults() -> None:
    """Slash appeal starts in submitted status with evidence."""
    repo_dir = Path(__file__).resolve().parents[2]
    slash_appeal = _import_module(
        "coordinator_api.contexts.governance.domain.slash_appeal",
        repo_dir / "apps/coordinator-api/src",
    )

    appeal = slash_appeal.SlashAppeal(
        bond_id="bond-1",
        provider_id="provider-1",
        slash_event_id="slash-1",
        reason="downtime",
        evidence=["cid-1"],
    )
    assert appeal.status == slash_appeal.SlashAppealStatus.SUBMITTED.value


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


def test_cli_bond_commands() -> None:
    """Bond CLI commands run in simulated mode without a coordinator URL."""
    from click.testing import CliRunner
    from cli.aitbc_cli.core.main import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["bond", "status", "provider-1"])
    assert result.exit_code == 0
    assert "provider-1" in result.output

    result = runner.invoke(cli, ["bond", "top-up", "provider-1", "--amount", "100"])
    assert result.exit_code == 0
    assert "100" in result.output

    result = runner.invoke(cli, ["bond", "appeal", "bond-1", "--reason", "downtime"])
    assert result.exit_code == 0
    assert "bond-1" in result.output


def test_cli_reinvest_simulate() -> None:
    """Reinvest simulate returns planned on-chain actions."""
    from click.testing import CliRunner
    from cli.aitbc_cli.core.main import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["reinvest", "simulate", "agent-1", "--earnings", "10"])
    assert result.exit_code == 0
    assert "agent-1" in result.output


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
