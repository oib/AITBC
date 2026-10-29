"""Liquidity pool transaction builders (``/rpc/liquidity/build-*``).

The ``aitbc wallet liquidity-*`` commands build, sign and submit
``LIQUIDITY_*`` transactions locally. These leaves instead call the node's
``build-*`` routes, which return the *unsigned* transaction (correct nonce,
pool address, payload) for offline/external signing — no wallet key touches
the node.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import click

from aitbc.utils import ait_to_units
from aitbc.utils.units import DEFAULT_TX_FEE_AIT

from ..utils import DECIMAL, output, resolve_output_format
from ..utils.error_handling import abort
from ..utils.http_client import AITBCHTTPClient
from ..utils.signed_rpc import resolve_rpc_url
from ..utils.wallet_loader import load_wallet_for_payment


def _resolve_address(ctx, address: str | None, wallet_name: str | None) -> str:
    """Return ``--address`` or load the address of ``--wallet-name``."""
    if address:
        return address
    if wallet_name:
        resolved, _, _ = load_wallet_for_payment(ctx, wallet_name, require_private_key=False)
        return resolved
    abort(ctx, "pass --address or --wallet-name so the built transaction has a sender")
    raise AssertionError("unreachable")


def _build(ctx, path: str, body: dict[str, Any], rpc_url: str | None, chain_id: str | None, as_json: bool, title: str):
    rpc = resolve_rpc_url(ctx, rpc_url)
    if chain_id:
        path = f"{path}?chain_id={chain_id}"
    try:
        result = AITBCHTTPClient(base_url=rpc, timeout=15).post(path, json=body)
    except Exception as e:
        abort(ctx, f"{path} failed: {e}", from_exception=e)
    output(result, "json" if as_json else resolve_output_format(ctx), title=title)
    return result


def _build_options(f):
    f = click.option("--json", "as_json", is_flag=True, help="Emit the unsigned transaction as JSON")(f)
    f = click.option("--chain-id", "chain_id", default=None, help="Chain ID the transaction is built for")(f)
    f = click.option("--rpc-url", "rpc_url", default=None, help="Blockchain RPC URL (overrides config)")(f)
    f = click.option("--fee", "fee", type=DECIMAL, default=DEFAULT_TX_FEE_AIT, help="Transaction fee in AIT")(f)
    f = click.option("--pool-id", "pool_id", default="main", help="Liquidity pool identifier (default: main)")(f)
    f = click.option("--wallet-name", "wallet_name", default=None, help="Wallet whose address is the sender")(f)
    f = click.option("--address", "address", default=None, help="Sender address (overrides --wallet-name)")(f)
    return f


@click.group(
    epilog="""Examples:

  aitbc liquidity build-deposit --address 0xAbc... --amount 50 --lock-days 7

  aitbc liquidity build-withdraw --address 0xAbc... --stake-id lstake-1234 --json"""
)
def liquidity():
    """Build unsigned LIQUIDITY_* transactions via the node's build routes."""
    pass


@liquidity.command(
    name="build-deposit",
    epilog="""Example:

  aitbc liquidity build-deposit --address 0xAbc... --amount 50 --pool-id main --lock-days 7""",
)
@click.option("--amount", "amount", required=True, type=DECIMAL, help="Deposit amount in AIT")
@click.option("--lock-days", "lock_days", default=0, type=int, help="Lock period in days (higher APY)")
@_build_options
@click.pass_context
def build_deposit(ctx, amount: Decimal, lock_days, address, wallet_name, pool_id, fee, rpc_url, chain_id, as_json):
    """Build an unsigned LIQUIDITY_DEPOSIT transaction."""
    body = {
        "address": _resolve_address(ctx, address, wallet_name),
        "amount": int(ait_to_units(amount)),
        "lock_days": lock_days,
        "pool_id": pool_id,
        "fee": int(ait_to_units(fee)),
    }
    _build(ctx, "/rpc/liquidity/build-deposit", body, rpc_url, chain_id, as_json, "Unsigned LIQUIDITY_DEPOSIT")


@liquidity.command(
    name="build-claim",
    epilog="""Example:

  aitbc liquidity build-claim --address 0xAbc... --stake-id lstake-1234""",
)
@click.option("--stake-id", "stake_id", required=True, help="Liquidity stake identifier to claim rewards from")
@_build_options
@click.pass_context
def build_claim(ctx, stake_id, address, wallet_name, pool_id, fee, rpc_url, chain_id, as_json):
    """Build an unsigned LIQUIDITY_CLAIM transaction."""
    body = {
        "address": _resolve_address(ctx, address, wallet_name),
        "stake_id": stake_id,
        "pool_id": pool_id,
        "fee": int(ait_to_units(fee)),
    }
    _build(ctx, "/rpc/liquidity/build-claim", body, rpc_url, chain_id, as_json, "Unsigned LIQUIDITY_CLAIM")


@liquidity.command(
    name="build-withdraw",
    epilog="""Example:

  aitbc liquidity build-withdraw --address 0xAbc... --stake-id lstake-1234""",
)
@click.option("--stake-id", "stake_id", required=True, help="Liquidity stake identifier to withdraw")
@_build_options
@click.pass_context
def build_withdraw(ctx, stake_id, address, wallet_name, pool_id, fee, rpc_url, chain_id, as_json):
    """Build an unsigned LIQUIDITY_WITHDRAW transaction (stake must be unlocked)."""
    body = {
        "address": _resolve_address(ctx, address, wallet_name),
        "stake_id": stake_id,
        "pool_id": pool_id,
        "fee": int(ait_to_units(fee)),
    }
    _build(ctx, "/rpc/liquidity/build-withdraw", body, rpc_url, chain_id, as_json, "Unsigned LIQUIDITY_WITHDRAW")
