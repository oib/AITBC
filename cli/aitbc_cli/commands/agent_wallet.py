"""Agent wallet commands for OpenClaw autonomous economics."""

from __future__ import annotations

import click

from ..utils import output
from ..utils.error_handling import abort


@click.group(
    epilog="""Examples:

  aitbc agent-wallet balance --agent-id agent-1

  aitbc agent-wallet stake --agent-id agent-1 --amount 100"""
)
def agent_wallet():
    """Show and manage agent-owned wallets, staking, and rebalancing allocations."""
    pass


@agent_wallet.command(
    epilog="""Examples:

  aitbc agent-wallet balance --agent-id agent-1

  aitbc agent-wallet balance --agent-id agent-1 --output json"""
)
@click.option("--agent-id", "agent_id", required=True, help="Agent ID.")
@click.pass_context
def balance(ctx, agent_id: str):
    """Show the wallet balance and allocation for a given agent ID."""
    try:
        result = {
            "agent_id": agent_id,
            "total": "0.00000000",
            "allocated": "0.00000000",
            "available": "0.00000000",
            "currency": "AITBC",
            "status": "simulated",
        }
        output(result, ctx.obj.get("output_format", "table"), title="Agent Wallet Balance")
    except Exception as e:
        abort(ctx, f"Error fetching agent wallet balance: {e}", from_exception=e)


@agent_wallet.command(
    epilog="""Examples:

  aitbc agent-wallet stake --agent-id agent-1 --amount 100

  aitbc agent-wallet stake --agent-id agent-1 --amount 100 --contract 0xStakeContract"""
)
@click.option("--agent-id", "agent_id", required=True, help="Agent ID.")
@click.option("--amount", default="0", help="Amount to stake")
@click.option("--contract", default="", help="Staking contract address")
@click.pass_context
def stake(ctx, agent_id: str, amount: str, contract: str):
    """Stake AITBC on behalf of a specified agent ID."""
    try:
        result = {
            "agent_id": agent_id,
            "action": "stake",
            "amount": amount,
            "contract": contract or "0xSTAKE",
            "status": "simulated",
        }
        output(result, ctx.obj.get("output_format", "table"), title="Agent Stake")
    except Exception as e:
        abort(ctx, f"Error staking for agent {agent_id}: {e}", from_exception=e)


@agent_wallet.command(
    epilog="""Examples:

  aitbc agent-wallet rebalance --agent-id agent-1 --earnings 50

  aitbc agent-wallet rebalance --agent-id agent-1 --earnings 50 --reinvest-pct 75"""
)
@click.option("--agent-id", "agent_id", required=True, help="Agent ID.")
@click.option("--earnings", default="0", help="Earnings to reinvest")
@click.option("--reinvest-pct", default="50", help="Percentage of earnings to reinvest")
@click.pass_context
def rebalance(ctx, agent_id: str, earnings: str, reinvest_pct: str):
    """Rebalance an agent wallet by reinvesting the specified earnings."""
    try:
        result = {
            "agent_id": agent_id,
            "action": "rebalance",
            "earnings": earnings,
            "reinvest_pct": reinvest_pct,
            "status": "simulated",
        }
        output(result, ctx.obj.get("output_format", "table"), title="Agent Rebalance")
    except Exception as e:
        abort(ctx, f"Error rebalancing agent {agent_id}: {e}", from_exception=e)
