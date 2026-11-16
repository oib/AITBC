"""Provider reinvestment commands for AITBC CLI."""

from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path

import click

from aitbc.exceptions import AITBCError

from ..utils import output
from ..utils.error_handling import abort

_POLICY_STORE = Path.home() / ".aitbc" / "reinvest_policies.json"


def _load_policies() -> dict:
    try:
        data: dict = json.loads(_POLICY_STORE.read_text())
        return data
    except (OSError, ValueError):
        return {}


def _save_policies(policies: dict) -> None:
    _POLICY_STORE.parent.mkdir(parents=True, exist_ok=True)
    _POLICY_STORE.write_text(json.dumps(policies, indent=2))


def _policy_params(agent_id: str) -> dict | None:
    params = _load_policies().get(agent_id)
    return params if isinstance(params, dict) else None


def _load_miner_app():
    """Load the miner reinvestment engine if available."""
    repo_root = Path(__file__).resolve().parents[3]
    miner_path = repo_root / "apps" / "miner" / "src"
    if str(miner_path) not in sys.path:
        sys.path.insert(0, str(miner_path))
    from miner_app.reinvestment import ReinvestmentEngine, ReinvestmentPolicy
    from aitbc.agent_economics import Budget

    return ReinvestmentEngine, ReinvestmentPolicy, Budget


@click.group(
    epilog="""Examples:

  aitbc reinvest policy --agent-id agent-1

  aitbc reinvest simulate --agent-id agent-1"""
)
def reinvest():
    """Configure and simulate autonomous reinvestment policies for agents."""
    pass


@reinvest.command(
    epilog="""Examples:

  aitbc reinvest policy --agent-id agent-1

  aitbc reinvest policy --agent-id agent-1 --staking-pct 50 --reserve-pct 30"""
)
@click.option("--agent-id", "agent_id", required=True, help="The Agent-id.")
@click.option("--staking-pct", default="60", help="Percentage of reinvested funds directed to staking")
@click.option("--reserve-pct", default="40", help="Percentage of reinvested funds kept as capacity reserve")
@click.option("--min-reinvest", default="0.01", help="Minimum amount to reinvest")
@click.pass_context
def policy(ctx, agent_id: str, staking_pct: str, reserve_pct: str, min_reinvest: str):
    """Record a reinvestment policy for an agent (persisted locally)."""
    try:
        staking, reserve = Decimal(staking_pct), Decimal(reserve_pct)
        if staking + reserve != Decimal("100"):
            abort(ctx, f"staking-pct + reserve-pct must equal 100 (got {staking_pct}+{reserve_pct})")
            return
        policies = _load_policies()
        policies[agent_id] = {
            "staking_pct": staking_pct,
            "reserve_pct": reserve_pct,
            "min_reinvest": min_reinvest,
        }
        _save_policies(policies)
        result = {**policies[agent_id], "agent_id": agent_id, "status": "saved"}
        output(result, ctx.obj.get("output_format", "table"), title="Reinvestment Policy")
    except (ArithmeticError, OSError, ValueError, TypeError) as e:
        abort(ctx, f"Error recording reinvestment policy: {e}", from_exception=e)


@reinvest.command(
    epilog="""Examples:

  aitbc reinvest simulate --agent-id agent-1

  aitbc reinvest simulate --agent-id agent-1 --earnings 10 --budget-total 100"""
)
@click.option("--agent-id", "agent_id", required=True, help="The Agent-id.")
@click.option("--earnings", default="10", help="Earnings amount to simulate")
@click.option("--budget-total", default="100", help="Total budget for the agent")
@click.option("--staking-contract", default="0xSTAKE", help="Staking contract address")
@click.option("--reserve-address", default="0xRESERVE", help="Reserve address for capacity funds")
@click.option("--staking-pct", default=None, help="Override stored policy: % of reinvested funds to staking")
@click.option("--reserve-pct", default=None, help="Override stored policy: % of reinvested funds to capacity reserve")
@click.option("--min-reinvest", default=None, help="Override stored policy: minimum reinvest amount")
@click.pass_context
def simulate(
    ctx,
    agent_id: str,
    earnings: str,
    budget_total: str,
    staking_contract: str,
    reserve_address: str,
    staking_pct: str | None,
    reserve_pct: str | None,
    min_reinvest: str | None,
):
    """Simulate reinvestment actions for a given earnings amount.

    Uses the policy recorded by ``aitbc reinvest policy --agent-id <id>``
    when present; option overrides take precedence, else engine defaults.
    """
    try:
        ReinvestmentEngine, ReinvestmentPolicy, Budget = _load_miner_app()
        saved = _policy_params(agent_id) or {}
        staking = Decimal(staking_pct if staking_pct is not None else saved.get("staking_pct", "60"))
        reserve = Decimal(reserve_pct if reserve_pct is not None else saved.get("reserve_pct", "40"))
        if staking + reserve != Decimal("100"):
            abort(ctx, f"staking-pct + reserve-pct must equal 100 (got {staking}+{reserve})")
            return
        budget = Budget(budget_id="sim", agent_id=agent_id, chain_id="ait-hub", token="AITBC", total=Decimal(budget_total))
        policy = ReinvestmentPolicy(
            staking_pct=staking,
            capacity_reserve_pct=reserve,
            min_reinvest_amount=Decimal(min_reinvest if min_reinvest is not None else saved.get("min_reinvest", "0.01")),
            staking_contract=staking_contract,
            reserve_address=reserve_address,
        )
        engine = ReinvestmentEngine(budget, policy)
        actions = engine.apply(Decimal(earnings), agent_id)
        result = {
            "agent_id": agent_id,
            "earnings": earnings,
            "policy_source": "override" if (staking_pct or reserve_pct or min_reinvest) else ("saved" if saved else "default"),
            "actions": [
                {"action_type": a.action_type, "contract_address": a.contract_address, "amount": str(a.amount)}
                for a in actions
            ],
        }
        output(result, ctx.obj.get("output_format", "table"), title="Reinvestment Simulation")
    # _load_miner_app() does a dynamic first-party import (ImportError) and the
    # engine raises standard data-shape errors (#1860).
    except (
        AITBCError,
        ImportError,
        OSError,
        ArithmeticError,
        ValueError,
        KeyError,
        TypeError,
        AttributeError,
        RuntimeError,
    ) as e:
        abort(ctx, f"Error simulating reinvestment for {agent_id}: {e}", from_exception=e)
