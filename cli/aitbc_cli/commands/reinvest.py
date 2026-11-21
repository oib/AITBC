"""Provider reinvestment commands for AITBC CLI."""

from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path

import click

from aitbc.exceptions import AITBCError

from ..config import get_config
from ..utils import output, warning
from ..utils.error_handling import NotFoundError, abort

_POLICY_STORE = Path.home() / ".aitbc" / "reinvest_policies.json"

# Engine-side placeholder for an unconfigured leg address: OnChainAction
# requires a non-empty contract_address, so simulate feeds this sentinel and
# reports ``null`` — never a fake address like the old ``0xSTAKE`` (#2448).
_UNCONFIGURED_ADDRESS = "__unconfigured__"


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
@click.option(
    "--staking-contract",
    default=None,
    help="Staking contract address (default: staking_contract_address config / STAKING_CONTRACT_ADDRESS env)",
)
@click.option(
    "--reserve-address",
    default=None,
    help="Reserve address for capacity funds (default: reinvest_reserve_address config / REINVEST_RESERVE_ADDRESS env)",
)
@click.option("--staking-pct", default=None, help="Override stored policy: % of reinvested funds to staking")
@click.option("--reserve-pct", default=None, help="Override stored policy: % of reinvested funds to capacity reserve")
@click.option("--min-reinvest", default=None, help="Override stored policy: minimum reinvest amount")
@click.option("--strict", is_flag=True, help="Exit non-zero when the agent has no recorded policy")
@click.pass_context
def simulate(
    ctx,
    agent_id: str,
    earnings: str,
    budget_total: str,
    staking_contract: str | None,
    reserve_address: str | None,
    staking_pct: str | None,
    reserve_pct: str | None,
    min_reinvest: str | None,
    strict: bool,
):
    """Simulate reinvestment actions for a given earnings amount.

    Uses the policy recorded by ``aitbc reinvest policy --agent-id <id>``
    when present; option overrides take precedence, else engine defaults.
    """
    try:
        ReinvestmentEngine, ReinvestmentPolicy, Budget = _load_miner_app()
        saved = _policy_params(agent_id) or {}
        # #2448: an agent with no recorded policy used to get a plausible
        # invented result silently — say so, or refuse under --strict.
        if not saved:
            if strict:
                abort(
                    ctx,
                    f"agent '{agent_id}' has no recorded reinvestment policy — "
                    f"run `aitbc reinvest policy --agent-id {agent_id}` first or drop --strict",
                    error_type=NotFoundError,
                )
            warning(f"agent '{agent_id}' has no recorded reinvestment policy — simulating with default policy values")
        effective = _effective_policy(saved)
        staking = Decimal(staking_pct if staking_pct is not None else effective["staking_pct"])
        reserve = Decimal(reserve_pct if reserve_pct is not None else effective["reserve_pct"])
        if staking + reserve != Decimal("100"):
            abort(ctx, f"staking-pct + reserve-pct must equal 100 (got {staking}+{reserve})")
            return
        config = get_config()
        resolved_staking = staking_contract or config.staking_contract_address or ""
        resolved_reserve = reserve_address or config.reinvest_reserve_address or ""
        budget = Budget(budget_id="sim", agent_id=agent_id, chain_id="ait-hub", token="AITBC", total=Decimal(budget_total))
        policy = ReinvestmentPolicy(
            staking_pct=staking,
            capacity_reserve_pct=reserve,
            min_reinvest_amount=Decimal(min_reinvest if min_reinvest is not None else effective["min_reinvest"]),
            staking_contract=resolved_staking or _UNCONFIGURED_ADDRESS,
            reserve_address=resolved_reserve or _UNCONFIGURED_ADDRESS,
        )
        engine = ReinvestmentEngine(budget, policy)
        actions = engine.apply(Decimal(earnings), agent_id)
        action_dicts = [
            {
                "action_type": a.action_type,
                "contract_address": None if a.contract_address == _UNCONFIGURED_ADDRESS else a.contract_address,
                "amount": str(a.amount),
            }
            for a in actions
        ]
        # #2448: name the unallocated remainder — reinvest_pct is a fixed
        # engine default the CLI does not expose, so earnings minus the
        # action total is what stays spendable, never silently dropped.
        retained = Decimal(earnings) - sum((Decimal(a["amount"]) for a in action_dicts), start=Decimal("0"))
        if retained > 0:
            action_dicts.append({"action_type": "retain", "contract_address": None, "amount": str(retained)})
        result = {
            "agent_id": agent_id,
            "earnings": earnings,
            "policy_source": "override" if (staking_pct or reserve_pct or min_reinvest) else ("saved" if saved else "default"),
            "actions": action_dicts,
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
