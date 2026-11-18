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


_DEFAULT_STAKING_PCT = "60"
_DEFAULT_RESERVE_PCT = "40"
_DEFAULT_MIN_REINVEST = "0.01"


def _effective_policy(saved: dict) -> dict:
    """Merge a stored policy dict over the engine defaults."""
    return {
        "staking_pct": saved.get("staking_pct", _DEFAULT_STAKING_PCT),
        "reserve_pct": saved.get("reserve_pct", _DEFAULT_RESERVE_PCT),
        "min_reinvest": saved.get("min_reinvest", _DEFAULT_MIN_REINVEST),
    }


@reinvest.command(
    epilog="""Examples:

  aitbc reinvest policy --agent-id agent-1

  aitbc reinvest policy --agent-id agent-1 --staking-pct 50 --reserve-pct 30"""
)
@click.option("--agent-id", "agent_id", required=True, help="The Agent-id.")
@click.option("--staking-pct", default=None, help="Percentage of reinvested funds directed to staking")
@click.option("--reserve-pct", default=None, help="Percentage of reinvested funds kept as capacity reserve")
@click.option("--min-reinvest", default=None, help="Minimum amount to reinvest")
@click.pass_context
def policy(ctx, agent_id: str, staking_pct: str | None, reserve_pct: str | None, min_reinvest: str | None):
    """Show or record a reinvestment policy for an agent (persisted locally).

    With no policy options this is a read-back of the stored policy and
    never writes; providing any option records the merged policy.
    """
    try:
        saved = _policy_params(agent_id) or {}
        if staking_pct is None and reserve_pct is None and min_reinvest is None:
            result = {
                **_effective_policy(saved),
                "agent_id": agent_id,
                "policy_source": "saved" if saved else "default",
                "status": "loaded",
            }
            output(result, ctx.obj.get("output_format", "table"), title="Reinvestment Policy")
            return
        effective = _effective_policy(saved)
        effective.update(
            {
                k: v
                for k, v in {
                    "staking_pct": staking_pct,
                    "reserve_pct": reserve_pct,
                    "min_reinvest": min_reinvest,
                }.items()
                if v is not None
            }
        )
        staking, reserve = Decimal(effective["staking_pct"]), Decimal(effective["reserve_pct"])
        Decimal(effective["min_reinvest"])
        if staking + reserve != Decimal("100"):
            abort(
                ctx,
                f"staking-pct + reserve-pct must equal 100 (got {effective['staking_pct']}+{effective['reserve_pct']})",
            )
            return
        policies = _load_policies()
        policies[agent_id] = effective
        _save_policies(policies)
        result = {**effective, "agent_id": agent_id, "status": "saved"}
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
        effective = _effective_policy(saved)
        staking = Decimal(staking_pct if staking_pct is not None else effective["staking_pct"])
        reserve = Decimal(reserve_pct if reserve_pct is not None else effective["reserve_pct"])
        if staking + reserve != Decimal("100"):
            abort(ctx, f"staking-pct + reserve-pct must equal 100 (got {staking}+{reserve})")
            return
        budget = Budget(budget_id="sim", agent_id=agent_id, chain_id="ait-hub", token="AITBC", total=Decimal(budget_total))
        policy = ReinvestmentPolicy(
            staking_pct=staking,
            capacity_reserve_pct=reserve,
            min_reinvest_amount=Decimal(min_reinvest if min_reinvest is not None else effective["min_reinvest"]),
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
