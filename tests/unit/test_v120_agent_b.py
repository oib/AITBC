"""Unit tests for v0.12.0 Agent B tasks.

Imports coordinator-api domain modules directly via sys.path so the tests can
run from the shared `tests/unit` suite without requiring coordinator-api to be
installed as a package.
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch
from types import ModuleType
from typing import Any


_COORD_SRC = Path(__file__).resolve().parent.parent.parent / "apps" / "coordinator-api" / "src"
_MINER_SRC = Path(__file__).resolve().parent.parent.parent / "apps" / "miner"
if str(_COORD_SRC) not in sys.path:
    sys.path.insert(0, str(_COORD_SRC))
if str(_MINER_SRC) not in sys.path:
    sys.path.insert(0, str(_MINER_SRC))


def _import_module(module_path: str) -> ModuleType:
    """Import a module, skipping the test if the source tree is unavailable."""
    try:
        return __import__(module_path, fromlist=["__name__"])
    except ImportError:  # pragma: no cover - defensive
        pass


def _import_coordinator(module_path: str) -> ModuleType:
    """Import a coordinator-api module, skipping if the source tree is unavailable."""
    return _import_module(module_path)


# ---------------------------------------------------------------------------
# B1 — OpenClaw DAO economic governance
# ---------------------------------------------------------------------------


def test_economic_proposal_status_enum() -> None:
    """Economic proposal statuses cover the OpenClaw lifecycle."""
    economic_proposal = _import_coordinator("coordinator_api.contexts.governance.domain.economic_proposal")
    statuses = {s.value for s in economic_proposal.EconomicProposalStatus}
    assert statuses == {"draft", "submitted", "active", "passed", "rejected", "executed"}


# ---------------------------------------------------------------------------
# B2 — Provider reinvestment loop
# ---------------------------------------------------------------------------


def test_reinvestment_engine_plans_actions() -> None:
    """The reinvestment engine converts earnings into on-chain actions."""
    reinvestment = _import_module("miner_app.reinvestment")
    agent_economics = __import__("aitbc.agent_economics", fromlist=["Budget"])

    budget = agent_economics.Budget(budget_id="b1", agent_id="agent-1", chain_id="ait-hub", token="AITBC", total=10)
    policy = reinvestment.ReinvestmentPolicy(
        reinvest_pct=50,
        staking_pct=60,
        capacity_reserve_pct=40,
        staking_contract="0xSTAKE",
        reserve_address="0xRESERVE",
    )
    engine = reinvestment.ReinvestmentEngine(budget, policy)
    actions = engine.apply(earnings=4, agent_id="agent-1")

    assert len(actions) == 2
    assert actions[0].action_type.value == "stake"
    assert actions[1].action_type.value == "transfer"
    assert budget.allocated == sum(a.amount for a in actions)


def test_reinvestment_engine_skips_small_earnings() -> None:
    """Earnings below the minimum threshold are held, not reinvested."""
    reinvestment = _import_module("miner_app.reinvestment")
    agent_economics = __import__("aitbc.agent_economics", fromlist=["Budget"])

    budget = agent_economics.Budget(budget_id="b1", agent_id="agent-1", chain_id="ait-hub", token="AITBC", total=10)
    policy = reinvestment.ReinvestmentPolicy(min_reinvest_amount=1)
    engine = reinvestment.ReinvestmentEngine(budget, policy)
    assert engine.apply(earnings=0.5, agent_id="agent-1") == []


def test_reinvestment_worker_dispatches_actions() -> None:
    """The worker fetches earnings and dispatches planned actions."""
    reinvestment = _import_module("miner_app.reinvestment")
    worker_mod = _import_module("miner_app.worker")
    agent_economics = __import__("aitbc.agent_economics", fromlist=["Budget"])

    budget = agent_economics.Budget(budget_id="b1", agent_id="agent-1", chain_id="ait-hub", token="AITBC", total=10)
    policy = reinvestment.ReinvestmentPolicy(staking_contract="0xSTAKE", reserve_address="0xRESERVE")
    engine = reinvestment.ReinvestmentEngine(budget, policy)

    dispatched: list[Any] = []
    worker = worker_mod.ReinvestmentWorker(
        engine,
        agent_id="agent-1",
        earnings_source=lambda: Decimal("4"),
        dispatcher=lambda actions: dispatched.extend(actions),
    )
    actions = worker.run_once()
    assert actions == dispatched
    assert len(actions) == 2


# ---------------------------------------------------------------------------
# B3 — CLI extensions
# ---------------------------------------------------------------------------


def test_agent_wallet_cli_commands_exist() -> None:
    """The agent-wallet command group exposes balance, stake, and rebalance."""
    agent_wallet = _import_module("aitbc_cli.commands.agent_wallet")
    assert "balance" in agent_wallet.agent_wallet.commands
    assert "stake" in agent_wallet.agent_wallet.commands
    assert "rebalance" in agent_wallet.agent_wallet.commands


def test_agent_wallet_balance_invocation() -> None:
    """agent-wallet balance can be invoked without error."""
    from click.testing import CliRunner

    agent_wallet = _import_module("aitbc_cli.commands.agent_wallet")
    runner = CliRunner()
    result = runner.invoke(agent_wallet.agent_wallet, ["balance", "--agent-id", "agent-1"], obj={"output_format": "json"})
    assert result.exit_code == 0
    assert "agent-1" in result.output


def test_economics_governance_commands_exist() -> None:
    """The economics group exposes propose, vote, and status."""
    economics = _import_module("aitbc_cli.commands.economics")
    assert "propose" in economics.economics.commands
    assert "vote" in economics.economics.commands
    assert "status" in economics.economics.commands


def test_economics_propose_invocation() -> None:
    """economics propose can be invoked without error."""
    from click.testing import CliRunner

    economics = _import_module("aitbc_cli.commands.economics")
    runner = CliRunner()
    with patch(
        "aitbc_cli.commands.economics.get_config", return_value=MagicMock(coordinator_api_url=None, timeout=30, api_key=None)
    ):
        result = runner.invoke(
            economics.economics,
            ["propose", "--parameter", "network_fee", "--current", "1", "--proposed", "2"],
            obj={"output_format": "json"},
        )
    assert result.exit_code == 0
    assert "network_fee" in result.output


# ---------------------------------------------------------------------------
# B4 — Economic eventing & audit
# ---------------------------------------------------------------------------


def test_reconcile_agent_wallets_finds_mismatch() -> None:
    """The reconciliation script reports budget/expected mismatches."""

    scripts_audit = Path(__file__).resolve().parent.parent.parent / "scripts" / "audit"
    if scripts_audit not in [Path(p) for p in sys.path]:
        sys.path.insert(0, str(scripts_audit))

    reconcile = _import_module("reconcile_agent_wallets")
    budget = __import__("aitbc.agent_economics", fromlist=["Budget"]).Budget(
        budget_id="agent-1",
        agent_id="agent-1",
        chain_id="ait-hub",
        token="AITBC",
        total=Decimal("100"),
    )
    ok, messages = reconcile.reconcile([budget], {"agent-1": "200"})
    assert not ok
    assert any("expected 200, got 100" in m for m in messages)
    ok, messages = reconcile.reconcile([budget], {"agent-1": "100"})
    assert ok
