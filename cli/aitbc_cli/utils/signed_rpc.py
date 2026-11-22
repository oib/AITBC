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
import re
import uuid
from decimal import Decimal
from typing import Any

import click

from aitbc.utils import ait_to_units

from aitbc.exceptions import AITBCError

from ..config import get_config
from . import output, resolve_output_format
from .chain_id import ChainIdLookupError, get_chain_id
from .error_handling import ValidationError, abort
from .http_client import AITBCHTTPClient, http_error_detail, http_response_status
from .wallet_loader import load_wallet_for_payment
from .wallet_secret import wallet_password_options

_LOCKED_UNTIL_RE = re.compile(r"Locked until:\s*(\S+)")


def _abort_request_error(ctx: click.Context, path: str, exc: Exception) -> None:
    """Abort a failed signed/GET RPC call with an honest error class.

    ``AITBCHTTPClient`` wraps every HTTP failure — including 4xx policy
    refusals — in ``NetworkError``, so a "lock period not expired" 400 used
    to surface as a network failure (exit 2, #2456, same class as #2437).
    When the server answered with a 4xx, report a ValidationError (exit 4)
    carrying the node's ``detail``; genuine transport failures keep the
    auto-categorised path.
    """
    status = http_response_status(exc)
    if status is not None and 400 <= status < 500:
        detail = http_error_detail(exc) or str(exc)
        extra: dict[str, Any] = {}
        m = _LOCKED_UNTIL_RE.search(detail)
        if m:
            extra["locked_until"] = m.group(1)
        abort(ctx, f"{path} failed: {detail}", error_type=ValidationError, from_exception=exc, extra=extra)
        return
    abort(ctx, f"{path} failed: {exc}", from_exception=exc)


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
    except ChainIdLookupError as e:
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


def _fresh_auth_nonce(body: dict[str, Any]) -> None:
    """Stamp the one-shot ``auth_nonce`` a signed body must carry (#2480).

    The operator signature covers every field except ``signature``, so a
    unique nonce inside the body makes each authorization's signature
    unique — the replay bound the node enforces at admission and at apply
    (v29). Callers may pin ``auth_nonce`` explicitly (tests, retries of the
    identical authorization); otherwise a fresh uuid4 hex is used.
    """
    body.setdefault("auth_nonce", uuid.uuid4().hex)


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
    _fresh_auth_nonce(body)
    body["signature"] = sign_fields(body, private_key)
    try:
        result = AITBCHTTPClient(base_url=rpc, timeout=30).post(path, json=body)
    except (AITBCError, ValueError, TypeError, KeyError, AttributeError) as e:
        _abort_request_error(ctx, path, e)
    output(result, "json" if as_json else resolve_output_format(ctx), title=title)
    return result


def post_signed_resolved(
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
    """Two-phase signed POST for resolved-value protocol transfers (#2472).

    Phase 1 posts the caller's fields plus ``resolve_only``: a #2472-aware
    node answers ``{"resolved": {"to", "amount"}}`` without mutating; an
    older node ignores the flag and executes the legacy path, in which case
    the probe response *is* the result and is rendered as-is (no second
    post, so nothing executes twice). Phase 2 re-signs the same fields plus
    the resolved ``to``/``amount`` so ``payload.auth`` binds both legs and
    the transfer becomes gossip-admissible.
    """
    rpc = resolve_rpc_url(ctx, rpc_url)
    address, private_key = load_operator_wallet(ctx, wallet_name, wallet_path, password, password_file, password_stdin)
    if default_user_field and fields.get(default_user_field) is None:
        fields[default_user_field] = address
    cid = resolve_chain_id(ctx, rpc, chain_id)
    client = AITBCHTTPClient(base_url=rpc, timeout=30)

    probe = {k: v for k, v in fields.items() if v is not None}
    probe["chain_id"] = cid
    probe["resolve_only"] = True
    _fresh_auth_nonce(probe)
    probe["signature"] = sign_fields(probe, private_key)
    try:
        probe_result = client.post(path, json=probe)
    except (AITBCError, ValueError, TypeError, KeyError, AttributeError) as e:
        _abort_request_error(ctx, path, e)

    resolved = probe_result.get("resolved") if isinstance(probe_result, dict) else None
    if not isinstance(resolved, dict) or "to" not in resolved or "amount" not in resolved:
        # Legacy node (executed) or nothing left to resolve — the probe
        # response is the outcome.
        output(probe_result, "json" if as_json else resolve_output_format(ctx), title=title)
        return probe_result

    body = {k: v for k, v in fields.items() if v is not None}
    body["chain_id"] = cid
    body["to"] = resolved["to"]
    body["amount"] = resolved["amount"]
    _fresh_auth_nonce(body)
    body["signature"] = sign_fields(body, private_key)
    try:
        result = client.post(path, json=body)
    except (AITBCError, ValueError, TypeError, KeyError, AttributeError) as e:
        _abort_request_error(ctx, path, e)
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
    except (AITBCError, ValueError, TypeError, KeyError, AttributeError) as e:
        _abort_request_error(ctx, path, e)
    output(result, "json" if as_json else resolve_output_format(ctx), title=title)
    return result


def amount_to_units(amount: Decimal | str | int) -> int:
    """Convert an ``--amount`` AIT value to base units for int fields."""
    return int(ait_to_units(amount))
