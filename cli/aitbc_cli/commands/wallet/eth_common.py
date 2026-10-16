"""Shared EVM plumbing for the wallet Sepolia commands (``eth-send``,
``eth-balance``).

These are the non-signing legs both commands run: resolving a ``--wallet``
name-or-path to a wallet file, reading the file's plaintext ``address``
field (a raw JSON read — never the key, never a password), and pinning the
resolved RPC endpoint to Sepolia's chain id before any reply is trusted.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import click

from ...utils import error, info, warning
from ...utils.address import to_eip55
from ...utils.error_handling import abort
from ...utils.evm_rpc import display_rpc_url, hex_to_int, rpc_call
from ...utils.wallet_paths import (
    ambiguous_wallet_note,
    find_wallet_file_report,
    service_dir_wallet_note,
    wallet_not_found_message,
)
from . import _emit_wallet_path_note

SEPOLIA_CHAIN_ID = 11155111


def resolve_wallet_path(ctx, wallet_name: str) -> Path:
    """Resolve a wallet name to a readable file via the shared search order.

    The group-set ``ctx.obj['wallet_sign_path']`` wins for the active wallet (it is
    already search-resolved and honours an explicit --wallet-path); any other
    name goes through the configured dir then the service wallet dir.
    """
    if wallet_name == ctx.obj.get("wallet_name") and ctx.obj.get("wallet_sign_path"):
        _emit_wallet_path_note(ctx)
        return Path(ctx.obj["wallet_sign_path"])
    report = find_wallet_file_report(wallet_name)
    if report.path is not None:
        note = ambiguous_wallet_note(report)
        if note:
            warning(note)
        service_note = service_dir_wallet_note(report)
        if service_note:
            info(service_note)
        return report.path
    error(wallet_not_found_message(report))
    raise click.Abort()


def resolve_wallet_file(ctx, wallet: str | None) -> tuple[str | None, Path]:
    """``--wallet`` names a wallet (standard search order) or gives a wallet
    file path — which is only ever opened locally; remote fetch does not
    exist, so a file on another host cannot be used."""
    name = wallet or (ctx.obj or {}).get("wallet_name")
    if name and (os.sep in name or name.endswith(".json")):
        path = Path(name)
        if not path.is_file():
            abort(ctx, f"wallet file not found: {path}")
        return Path(name).stem, path
    if not name:
        abort(ctx, "no wallet selected — pass --wallet <name|path> or the group --wallet-name")
    return name, resolve_wallet_path(ctx, str(name))


def wallet_address_only(ctx, wallet_path: Path) -> str:
    """The wallet file's plaintext ``address`` — a raw JSON read, no
    decryption, no password resolution."""
    try:
        with open(wallet_path) as f:
            data: dict[str, Any] = json.load(f)
    except OSError as e:
        abort(ctx, f"cannot read wallet file {wallet_path}: {e}", from_exception=e)
        raise AssertionError("unreachable: abort always raises") from e
    address = data.get("address")
    if not address:
        abort(ctx, f"wallet file {wallet_path} has no address field")
    return to_eip55(str(address))


def check_rpc_chain(ctx, rpc_url: str) -> None:
    rpc_chain = hex_to_int(ctx, rpc_call(ctx, rpc_url, "eth_chainId", []), "chain id")
    if rpc_chain != SEPOLIA_CHAIN_ID:
        abort(
            ctx,
            f"RPC at {display_rpc_url(rpc_url)} reports chain id {rpc_chain}, not Sepolia ({SEPOLIA_CHAIN_ID}) — refusing",
        )
