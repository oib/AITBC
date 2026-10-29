"""Agent-staking commands for the V23-42 agent-economy surface.

These leaves call the operator-signed ``/rpc/agent-staking/*`` routes on the
blockchain node — a different surface from consensus ``/rpc/staking/*`` (the
``aitbc wallet stake``/``aitbc stake`` path). Every write body is signed by
the operator wallet: canonical JSON of the field dict → keccak256 →
secp256k1, verified on the node against ``AGENT_ECONOMICS_OPERATOR_ADDRESS``.

``status`` is a read leaf: agent-stake rows are node-local, so it reports the
on-chain STAKE_LOCK/STAKE_RELEASE protocol transfers carrying the stake id —
the consensus-visible part of the stake's lifecycle.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

import click

from ..utils import DECIMAL, output, resolve_output_format
from ..utils.error_handling import abort
from ..utils.http_client import AITBCHTTPClient
from ..utils.signed_rpc import amount_to_units, operator_options, post_signed, resolve_rpc_url


@click.group(
    name="agent-staking",
    epilog="""Examples:

  aitbc agent-staking stake --stake-id stake-1 --agent-wallet 0xAgent... --amount 100 --lock-days 30 --wallet-name operator

  aitbc agent-staking status --stake-id stake-1 --rpc-url http://localhost:8202""",
)
def agent_staking():
    """Manage agent-economy stakes (operator-signed /rpc/agent-staking routes)."""
    pass


@agent_staking.command(
    epilog="""Examples:

  aitbc agent-staking stake --stake-id stake-1 --agent-wallet 0xAgent... --amount 100 --lock-days 30

  aitbc agent-staking stake --agent-wallet 0xAgent... --amount 50 --metadata '{"label":"bot"}'"""
)
@click.option("--stake-id", "stake_id", default=None, help="Stake identifier (generated when omitted)")
@click.option("--agent-wallet", "agent_wallet", required=True, help="Agent wallet address the stake is locked for")
@click.option(
    "--user-address",
    "user_address",
    default=None,
    help="Staker address (defaults to the signing wallet's address)",
)
@click.option("--amount", "amount", required=True, type=DECIMAL, help="Amount to lock, in AIT")
@click.option("--lock-days", "lock_period", required=True, type=int, help="Lock period in days (1-3650)")
@click.option("--metadata", "metadata", default=None, help="Optional metadata string carried in the signed body")
@operator_options
@click.pass_context
def stake(ctx, stake_id, agent_wallet, user_address, amount: Decimal, lock_period, metadata, **kw):
    """Lock an agent stake (queues a STAKE_LOCK protocol transfer)."""
    fields = {
        "stake_id": stake_id or f"agent-stake-{uuid.uuid4().hex[:16]}",
        "user_address": user_address,
        "agent_wallet": agent_wallet,
        "amount": amount_to_units(amount),
        "lock_period": lock_period,
        "metadata": metadata,
    }
    post_signed(ctx, "/rpc/agent-staking/stake", fields, default_user_field="user_address", title="Agent Stake", **kw)


@agent_staking.command(
    epilog="""Example:

  aitbc agent-staking add --stake-id stake-1 --amount 25 --wallet-name operator"""
)
@click.option("--stake-id", "stake_id", required=True, help="Stake identifier to top up")
@click.option("--amount", "amount", required=True, type=DECIMAL, help="Additional amount to lock, in AIT")
@click.option("--user-address", "user_address", default=None, help="Staker address (defaults to the signing wallet)")
@operator_options
@click.pass_context
def add(ctx, stake_id, amount: Decimal, user_address, **kw):
    """Top up an active agent stake (queues another STAKE_LOCK)."""
    fields = {"stake_id": stake_id, "additional_amount": amount_to_units(amount), "user_address": user_address}
    post_signed(
        ctx,
        f"/rpc/agent-staking/stake/{stake_id}/add",
        fields,
        default_user_field="user_address",
        title="Stake Top-Up",
        **kw,
    )


@agent_staking.command(
    epilog="""Example:

  aitbc agent-staking unbond --stake-id stake-1 --wallet-name operator"""
)
@click.option("--stake-id", "stake_id", required=True, help="Stake identifier to unbond")
@click.option("--user-address", "user_address", default=None, help="Staker address (defaults to the signing wallet)")
@operator_options
@click.pass_context
def unbond(ctx, stake_id, user_address, **kw):
    """Start unbonding an agent stake once its lock period expired."""
    fields = {"stake_id": stake_id, "user_address": user_address}
    post_signed(
        ctx,
        f"/rpc/agent-staking/stake/{stake_id}/unbond",
        fields,
        default_user_field="user_address",
        title="Unbond",
        **kw,
    )


@agent_staking.command(
    epilog="""Example:

  aitbc agent-staking complete --stake-id stake-1 --wallet-name operator"""
)
@click.option("--stake-id", "stake_id", required=True, help="Unbonding stake identifier to complete")
@click.option("--user-address", "user_address", default=None, help="Staker address (defaults to the signing wallet)")
@operator_options
@click.pass_context
def complete(ctx, stake_id, user_address, **kw):
    """Complete an unbonded agent stake (queues the STAKE_RELEASE payout)."""
    fields = {"stake_id": stake_id, "user_address": user_address}
    post_signed(
        ctx,
        f"/rpc/agent-staking/stake/{stake_id}/complete",
        fields,
        default_user_field="user_address",
        title="Stake Release",
        **kw,
    )


@agent_staking.command(
    epilog="""Example:

  aitbc agent-staking performance --stake-id stake-1 --memo 'uptime 99.9%' --wallet-name operator"""
)
@click.option("--stake-id", "stake_id", default=None, help="Stake identifier the memo belongs to")
@click.option("--agent-wallet", "agent_wallet", default=None, help="Agent wallet the memo belongs to")
@click.option("--memo", "memo", required=True, help="Free-form performance note stored in the memo payload")
@operator_options
@click.pass_context
def performance(ctx, stake_id, agent_wallet, memo, **kw):
    """Record a performance memo for a stake or agent wallet."""
    if not stake_id and not agent_wallet:
        raise click.UsageError("pass --stake-id or --agent-wallet so the memo has an external id")
    fields = {"stake_id": stake_id, "agent_wallet": agent_wallet, "memo": memo}
    post_signed(ctx, "/rpc/agent-staking/performance", fields, title="Performance Memo", **kw)


@agent_staking.command(
    epilog="""Example:

  aitbc agent-staking distribute --agent-wallet 0xAgent... --memo 'epoch 42 payout' --wallet-name operator"""
)
@click.option("--agent-wallet", "agent_wallet", required=True, help="Agent wallet the distribution memo belongs to")
@click.option("--memo", "memo", required=True, help="Free-form distribution note stored in the memo payload")
@operator_options
@click.pass_context
def distribute(ctx, agent_wallet, memo, **kw):
    """Record an earnings-distribution memo for an agent wallet."""
    fields = {"agent_wallet": agent_wallet, "memo": memo}
    post_signed(
        ctx,
        f"/rpc/agent-staking/agents/{agent_wallet}/distribute",
        fields,
        title="Distribution Memo",
        **kw,
    )


@agent_staking.command(
    epilog="""Example:

  aitbc agent-staking claim --stake-id stake-1 --wallet-name operator"""
)
@click.option("--stake-id", "stake_id", required=True, help="Stake identifier the rewards claim refers to")
@click.option("--memo", "memo", default=None, help="Optional note stored in the claim memo payload")
@operator_options
@click.pass_context
def claim(ctx, stake_id, memo, **kw):
    """Record a rewards-claim memo for an agent stake."""
    fields = {"stake_id": stake_id, "memo": memo}
    post_signed(ctx, "/rpc/agent-staking/claim-rewards", fields, title="Claim Memo", **kw)


@agent_staking.command(
    epilog="""Examples:

  aitbc agent-staking status --stake-id stake-1

  aitbc agent-staking status --stake-id stake-1 --rpc-url http://node2.example.net:8202 --json"""
)
@click.option("--stake-id", "stake_id", required=True, help="Stake identifier to look up on-chain")
@click.option("--chain-id", "chain_id", default=None, help="Chain ID to query (defaults to the node's)")
@click.option("--rpc-url", "rpc_url", default=None, help="Blockchain RPC URL (overrides config)")
@click.option("--limit", "limit", default=200, type=int, help="Max transactions scanned per type")
@click.option("--json", "as_json", is_flag=True, help="Emit the result as JSON")
@click.pass_context
def status(ctx, stake_id, chain_id, rpc_url, limit, as_json):
    """Show the on-chain lock/release transfers recorded for an agent stake."""
    rpc = resolve_rpc_url(ctx, rpc_url)
    client = AITBCHTTPClient(base_url=rpc, timeout=15)
    found: dict[str, Any] = {}
    for tx_type in ("STAKE_LOCK", "STAKE_RELEASE"):
        params = {"transaction_type": tx_type, "chain_id": chain_id, "limit": limit}
        try:
            rows: Any = client.get("/rpc/transactions", params={k: v for k, v in params.items() if v is not None})
        except Exception as e:
            abort(ctx, f"/rpc/transactions lookup failed: {e}", from_exception=e)
        txs: list[dict[str, Any]] = rows if isinstance(rows, list) else []
        matches = [tx for tx in txs if str((tx.get("payload") or {}).get("agent_stake_id")) == stake_id]
        if matches:
            found[tx_type] = matches
    output(
        {"stake_id": stake_id, "transactions": found},
        "json" if as_json else resolve_output_format(ctx),
        title=f"Agent stake {stake_id}",
    )
