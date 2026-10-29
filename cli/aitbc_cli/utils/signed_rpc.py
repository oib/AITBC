"""Signed-RPC helpers for operator-authenticated POST surfaces.

The agent-economics routes (``/rpc/agent-staking/*``, ``/rpc/bounty/*``) and
similar write surfaces authenticate with ``require_operator_signature``: the
POST body is a JSON dict whose every field except ``signature`` is signed —
canonical JSON (sorted keys, compact separators) → keccak256 → secp256k1 —
and the recovered address must equal the node's
``AGENT_ECONOMICS_OPERATOR_ADDRESS``. This module holds the CLI half of that
convention: resolve the signing wallet, build the signed body, post it.
"""

from __future__ import annotations

import json
import os
from decimal import Decimal
from typing import Any

import click

from aitbc.utils import ait_to_units

from ..config import get_config
from . import output, resolve_output_format
from .chain_id import get_chain_id
from .error_handling import abort
from .http_client import AITBCHTTPClient
from .wallet_loader import load_wallet_for_payment
from .wallet_secret import wallet_password_options


def operator_options(f):
    """Add the standard operator-signing option set to a command.

    ``--wallet-name``/``--wallet-path`` select the operator wallet,
    ``--password*`` unlock it, ``--rpc-url``/``--chain-id`` pin the target
    node, and ``--json`` flips the rendered result to machine-readable.
    """
    f = click.option("--json", "as_json", is_flag=True, help="Emit the result as JSON")(f)
    f = click.option(
        "--chain-id",
        "chain_id",
        default=None,
        help="Chain ID to sign with (skips auto-detection)",
    )(f)
    f = click.option(
        "--rpc-url",
        "rpc_url",
        default=None,
        help="Blockchain RPC URL (overrides config)",
    )(f)
    f = click.option(
        "--wallet-path",
        "wallet_path",
        default=None,
        help="Direct path to operator wallet file (overrides --wallet-name)",
    )(f)
    f = click.option(
        "--wallet-name",
        "wallet_name",
        default=None,
        help="Operator wallet that signs the request (its address must be the node's operator address)",
    )(f)
    f = wallet_password_options(f)
    return f


def resolve_rpc_url(ctx: click.Context, rpc_url: str | None) -> str:
    """Resolve the blockchain RPC URL: flag > ctx > config > localhost."""
    if rpc_url:
        return rpc_url.rstrip("/")
    if ctx and ctx.obj and ctx.obj.get("rpc_url"):
        return str(ctx.obj["rpc_url"]).rstrip("/")
    config = get_config()
    return (getattr(config, "blockchain_rpc_url", None) or "http://localhost:8202").rstrip("/")


def resolve_chain_id(ctx: click.Context, rpc_url: str, chain_id: str | None) -> str:
    """Resolve the chain id to sign with; abort when nothing reliable answers."""
    explicit = chain_id or (ctx.obj or {}).get("chain_id_explicit") or os.getenv("CHAIN_ID")
    if explicit:
        return str(explicit)
    try:
        return get_chain_id(rpc_url, override=None, timeout=5, strict=True)
    except Exception as e:
        abort(
            ctx,
            f"Chain ID lookup via {rpc_url} failed: {e}. Pass --chain-id or point --rpc-url at a serving node",
            from_exception=e,
        )
        raise  # unreachable — abort exits


def load_operator_wallet(
    ctx: click.Context,
    wallet_name: str | None,
    wallet_path: str | None,
    password: str | None,
    password_file: str | None,
    password_stdin: bool,
) -> tuple[str, str]:
    """Load the operator wallet and return ``(address, private_key)``."""
    address, private_key, resolved_name = load_wallet_for_payment(
        ctx,
        wallet_name,
        wallet_path=wallet_path,
        password=password,
        password_file=password_file,
        password_stdin=password_stdin,
        require_private_key=True,
    )
    if not private_key:
        abort(ctx, f"Wallet '{resolved_name}' has no usable private key for signing")
    return address, str(private_key)


def sign_fields(fields: dict[str, Any], private_key: str) -> str:
    """Sign the canonical JSON of *fields* — the exact bytes the RPC verifies."""
    from aitbc.crypto.crypto import sign_transaction_hash
    from eth_utils import keccak

    message = json.dumps(fields, sort_keys=True, separators=(",", ":")).encode()
    return sign_transaction_hash("0x" + keccak(message).hex(), private_key)


def post_signed(
    ctx: click.Context,
    path: str,
    fields: dict[str, Any],
    *,
    wallet_name: str | None,
    wallet_path: str | None,
    rpc_url: str | None,
    chain_id: str | None,
    password: str | None,
    password_file: str | None,
    password_stdin: bool,
    as_json: bool = False,
    title: str | None = None,
    default_user_field: str | None = None,
) -> dict[str, Any]:
    """Sign ``fields`` with the operator wallet and POST to ``path``.

    ``chain_id`` is resolved and injected into the signed body; ``None``
    values are dropped so the signed body only carries fields the caller set.
    When ``default_user_field`` names a field that is still ``None``, it is
    filled with the signing wallet's address — the staker/creator defaults
    to the operator, while an explicit ``--user-address`` still wins.
    """
    rpc = resolve_rpc_url(ctx, rpc_url)
    address, private_key = load_operator_wallet(ctx, wallet_name, wallet_path, password, password_file, password_stdin)
    if default_user_field and fields.get(default_user_field) is None:
        fields[default_user_field] = address
    body = {k: v for k, v in fields.items() if v is not None}
    body.setdefault("chain_id", resolve_chain_id(ctx, rpc, chain_id))
    body["signature"] = sign_fields(body, private_key)
    try:
        result = AITBCHTTPClient(base_url=rpc, timeout=30).post(path, json=body)
    except Exception as e:
        abort(ctx, f"{path} failed: {e}", from_exception=e)
    output(result, "json" if as_json else resolve_output_format(ctx), title=title)
    return result


def get_json(
    ctx: click.Context,
    path: str,
    *,
    rpc_url: str | None,
    params: dict[str, Any] | None = None,
    as_json: bool = False,
    title: str | None = None,
) -> Any:
    """GET ``path`` against the resolved RPC URL and render the result."""
    rpc = resolve_rpc_url(ctx, rpc_url)
    try:
        result = AITBCHTTPClient(base_url=rpc, timeout=15).get(
            path, params={k: v for k, v in (params or {}).items() if v is not None}
        )
    except Exception as e:
        abort(ctx, f"{path} failed: {e}", from_exception=e)
    output(result, "json" if as_json else resolve_output_format(ctx), title=title)
    return result


def amount_to_units(amount: Decimal | str | int) -> int:
    """Convert an ``--amount`` AIT value to base units for int fields."""
    return int(ait_to_units(amount))
