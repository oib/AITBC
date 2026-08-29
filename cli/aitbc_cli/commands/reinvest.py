"""Provider reinvestment commands for AITBC CLI."""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import click

from ..utils import output
from ..utils.error_handling import abort


def _load_miner_app():
    """Load the miner reinvestment engine if available."""
    repo_root = Path(__file__).resolve().parents[4]
    miner_path = repo_root / "apps" / "miner"
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
@click.option("--staking-pct", default="50", help="Percentage directed to staking")
@click.option("--reserve-pct", default="30", help="Percentage kept in reserve")
@click.option("--min-reinvest", default="1", help="Minimum amount to reinvest")
@click.pass_context
def policy(ctx, agent_id: str, staking_pct: str, reserve_pct: str, min_reinvest: str):
    """Show or record a reinvestment policy for an agent."""
    try:
        result = {
            "agent_id": agent_id,
            "staking_pct": staking_pct,
            "reserve_pct": reserve_pct,
            "min_reinvest": min_reinvest,
            "status": "simulated",
        }
        output(result, ctx.obj.get("output_format", "table"), title="Reinvestment Policy")
    except Exception as e:
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
@click.pass_context
def simulate(ctx, agent_id: str, earnings: str, budget_total: str, staking_contract: str, reserve_address: str):
    """Simulate reinvestment actions for a given earnings amount."""
    try:
        ReinvestmentEngine, ReinvestmentPolicy, Budget = _load_miner_app()
        budget = Budget(budget_id="sim", agent_id=agent_id, chain_id="ait-hub", token="AITBC", total=Decimal(budget_total))
        policy = ReinvestmentPolicy(
            min_reinvest_amount=Decimal("0"),
            staking_contract=staking_contract,
            reserve_address=reserve_address,
        )
        engine = ReinvestmentEngine(budget, policy)
        actions = engine.apply(Decimal(earnings), agent_id)
        result = {
            "agent_id": agent_id,
            "earnings": earnings,
            "actions": [
                {"action_type": a.action_type, "contract_address": a.contract_address, "amount": str(a.amount)}
                for a in actions
            ],
        }
        output(result, ctx.obj.get("output_format", "table"), title="Reinvestment Simulation")
    except Exception as e:
        abort(ctx, f"Error simulating reinvestment for {agent_id}: {e}", from_exception=e)
