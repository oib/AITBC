"""Bounty commands for the V23-42 agent-economy surface.

Calls the operator-signed ``/rpc/bounty/*`` routes: deploy locks the reward
(BOUNTY_LOCK), submit records a solution, verify pays the winner
(BOUNTY_PAYOUT), dispute marks the contract disputed, and expire refunds the
remaining amount to the creator (BOUNTY_REFUND). Every write body is signed
by the operator wallet — canonical JSON → keccak256 → secp256k1 — and the
signed ``bounty_id`` must match the path id where the route binds it.
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
    epilog="""Examples:

  aitbc bounty deploy --bounty-id bounty-1 --amount 50 --wallet-name operator

  aitbc bounty submit --bounty-id bounty-1 --submission-id sub-1 --wallet-name operator"""
)
def bounty():
    """Manage bounty locks and submissions (operator-signed /rpc/bounty routes)."""
    pass


@bounty.command(
    epilog="""Examples:

  aitbc bounty deploy --bounty-id bounty-1 --amount 50

  aitbc bounty deploy --amount 25 --memo 'summarise the whitepaper'"""
)
@click.option("--bounty-id", "bounty_id", default=None, help="Bounty identifier (generated when omitted)")
@click.option("--amount", "amount", required=True, type=DECIMAL, help="Reward amount to lock, in AIT")
@click.option(
    "--user-address",
    "user_address",
    default=None,
    help="Creator address funding the lock (defaults to the signing wallet)",
)
@click.option("--memo", "memo", default=None, help="Optional description carried in the signed body")
@operator_options
@click.pass_context
def deploy(ctx, bounty_id, amount: Decimal, user_address, memo, **kw):
    """Deploy a bounty lock (queues a BOUNTY_LOCK protocol transfer)."""
    fields = {
        "bounty_id": bounty_id or f"bounty-{uuid.uuid4().hex[:16]}",
        "user_address": user_address,
        "reward_amount": amount_to_units(amount),
        "memo": memo,
    }
    post_signed(ctx, "/rpc/bounty/deploy", fields, default_user_field="user_address", title="Bounty Deploy", **kw)


@bounty.command(
    epilog="""Example:

  aitbc bounty submit --bounty-id bounty-1 --submission-id sub-1 --memo 'ipfs://solution'"""
)
@click.option("--bounty-id", "bounty_id", required=True, help="Bounty identifier to submit against")
@click.option("--submission-id", "submission_id", default=None, help="Submission identifier (generated when omitted)")
@click.option(
    "--user-address",
    "user_address",
    default=None,
    help="Submitter address (defaults to the signing wallet)",
)
@click.option("--memo", "memo", default=None, help="Solution reference/note carried in the signed body")
@operator_options
@click.pass_context
def submit(ctx, bounty_id, submission_id, user_address, memo, **kw):
    """Submit a solution for a bounty (submission record)."""
    fields = {
        "bounty_id": bounty_id,
        "submission_id": submission_id or f"submission-{uuid.uuid4().hex[:16]}",
        "user_address": user_address,
        "memo": memo,
    }
    post_signed(
        ctx,
        f"/rpc/bounty/{bounty_id}/submit",
        fields,
        default_user_field="user_address",
        title="Bounty Submission",
        **kw,
    )


@bounty.command(
    epilog="""Examples:

  aitbc bounty verify --bounty-id bounty-1 --submission-id sub-1

  aitbc bounty verify --bounty-id bounty-1 --submission-id sub-1 --reject"""
)
@click.option("--bounty-id", "bounty_id", required=True, help="Bounty identifier")
@click.option("--submission-id", "submission_id", required=True, help="Submission identifier under review")
@click.option(
    "--reject/--approve",
    "reject",
    default=False,
    help="Reject the submission instead of paying it out (default: approve)",
)
@operator_options
@click.pass_context
def verify(ctx, bounty_id, submission_id, reject, **kw):
    """Verify a bounty submission — approval queues the BOUNTY_PAYOUT."""
    fields = {"bounty_id": bounty_id, "submission_id": submission_id, "verified": not reject}
    post_signed(ctx, f"/rpc/bounty/{bounty_id}/verify", fields, title="Bounty Verify", **kw)


@bounty.command(
    epilog="""Example:

  aitbc bounty dispute --bounty-id bounty-1 --submission-id sub-1 --reason 'plagiarised'"""
)
@click.option("--bounty-id", "bounty_id", required=True, help="Bounty identifier to dispute")
@click.option("--submission-id", "submission_id", default=None, help="Submission to mark disputed")
@click.option("--reason", "reason", default=None, help="Dispute reason carried in the signed body")
@operator_options
@click.pass_context
def dispute(ctx, bounty_id, submission_id, reason, **kw):
    """Mark a bounty (and optionally one submission) disputed."""
    fields = {"bounty_id": bounty_id, "submission_id": submission_id, "reason": reason}
    post_signed(ctx, f"/rpc/bounty/{bounty_id}/dispute", fields, title="Bounty Dispute", **kw)


@bounty.command(
    epilog="""Example:

  aitbc bounty expire --bounty-id bounty-1 --wallet-name operator"""
)
@click.option("--bounty-id", "bounty_id", required=True, help="Bounty identifier to expire")
@click.option(
    "--user-address",
    "user_address",
    default=None,
    help="Creator address the refund pays (defaults to the signing wallet)",
)
@operator_options
@click.pass_context
def expire(ctx, bounty_id, user_address, **kw):
    """Expire a bounty and refund the remaining lock to its creator."""
    fields = {"bounty_id": bounty_id, "user_address": user_address}
    post_signed(
        ctx,
        f"/rpc/bounty/{bounty_id}/expire",
        fields,
        default_user_field="user_address",
        title="Bounty Expire",
        **kw,
    )


@bounty.command(
    epilog="""Examples:

  aitbc bounty status --bounty-id bounty-1

  aitbc bounty status --bounty-id bounty-1 --rpc-url http://node2.example.net:8202 --json"""
)
@click.option("--bounty-id", "bounty_id", required=True, help="Bounty identifier to look up on-chain")
@click.option("--chain-id", "chain_id", default=None, help="Chain ID to query (defaults to the node's)")
@click.option("--rpc-url", "rpc_url", default=None, help="Blockchain RPC URL (overrides config)")
@click.option("--limit", "limit", default=200, type=int, help="Max transactions scanned per type")
@click.option("--json", "as_json", is_flag=True, help="Emit the result as JSON")
@click.pass_context
def status(ctx, bounty_id, chain_id, rpc_url, limit, as_json):
    """Show the on-chain lock/payout/refund transfers recorded for a bounty."""
    rpc = resolve_rpc_url(ctx, rpc_url)
    client = AITBCHTTPClient(base_url=rpc, timeout=15)
    found: dict[str, Any] = {}
    for tx_type in ("BOUNTY_LOCK", "BOUNTY_PAYOUT", "BOUNTY_REFUND"):
        params = {"transaction_type": tx_type, "chain_id": chain_id, "limit": limit}
        try:
            rows: Any = client.get("/rpc/transactions", params={k: v for k, v in params.items() if v is not None})
        except Exception as e:
            abort(ctx, f"/rpc/transactions lookup failed: {e}", from_exception=e)
        txs: list[dict[str, Any]] = rows if isinstance(rows, list) else []
        matches = [tx for tx in txs if str((tx.get("payload") or {}).get("bounty_id")) == bounty_id]
        if matches:
            found[tx_type] = matches
    output(
        {"bounty_id": bounty_id, "transactions": found},
        "json" if as_json else resolve_output_format(ctx),
        title=f"Bounty {bounty_id}",
    )
