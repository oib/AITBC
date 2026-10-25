"""Misc wallet commands for AITBC CLI"""

import json
from datetime import datetime, UTC
from decimal import InvalidOperation
from pathlib import Path

import click

from ...utils import error, output, success
from ...utils.error_handling import abort
from ...utils.http_client import AITBCHTTPClient
from ...utils.wallet_paths import (
    find_wallet_file_report,
    wallet_dir as resolve_wallet_dir,
    wallet_write_restricted_message,
)
from . import _load_wallet, wallet


# Public wallet-file fields inspect may print. Deny-by-default: anything not
# listed is refused, so a new secret-bearing field can never leak by accident.
_INSPECT_PUBLIC_FIELDS = frozenset(
    {
        "address",
        "wallet_id",
        "name",
        "type",
        "created_at",
        "public_key",
        "encrypted",
        "balance",
        "chain_id",
    }
)

# Names that are refused outright with a clear "private field" error — kept
# explicit so the refusal message names the reason, not just "not allowed".
_INSPECT_PRIVATE_FIELDS = frozenset(
    {
        "private_key",
        "seed",
        "seed_phrase",
        "mnemonic",
        "password",
        "secret",
        "keystore",
        "encrypted_data",
        "salt",
        "nonce",
        "iv",
        "xprv",
    }
)


@wallet.command(
    epilog="""Examples:

  aitbc wallet inspect --path /var/lib/aitbc/wallets/shop.json --field address

  aitbc wallet inspect --path ./genesis.json"""
)
@click.option("--path", "wallet_file", required=True, help="Path to the wallet JSON file")
@click.option("--field", "field", default=None, help="Print a single public field (e.g. address)")
@click.pass_context
def inspect(ctx, wallet_file: str, field: str | None):
    """Print public metadata from a wallet file without decrypting it.

    Reads the JSON directly and only ever returns fields on a public
    allowlist — private_key, seed/mnemonic material, and any unknown field
    are refused. Only scalar values are printed: a public field holding a
    dict or list (e.g. `encrypted` as a crypto object in some keystore
    formats) is refused rather than dumped. Works on encrypted wallets
    without a password."""
    path = Path(wallet_file)
    if not path.is_file():
        error(f"Wallet file not found: {wallet_file}")
        raise click.Abort()
    try:
        with open(path) as f:
            wallet_data = json.load(f)
    except json.JSONDecodeError:
        error(f"Not a JSON wallet file: {wallet_file}")
        raise click.Abort() from None
    if not isinstance(wallet_data, dict):
        error(f"Not a wallet JSON object: {wallet_file}")
        raise click.Abort()

    if field is not None:
        if field in _INSPECT_PRIVATE_FIELDS:
            error(f"refusing: '{field}' is a private field — inspect prints public wallet metadata only")
            raise click.Abort()
        if field not in _INSPECT_PUBLIC_FIELDS:
            error(f"refusing: '{field}' is not a public wallet field (allowed: {', '.join(sorted(_INSPECT_PUBLIC_FIELDS))})")
            raise click.Abort()
        value = wallet_data.get(field)
        if isinstance(value, (dict, list)):
            error(f"refusing: '{field}' holds a structured value — inspect prints plain scalar fields only")
            raise click.Abort()
        output(
            {"field": field, "value": value},
            ctx.obj.get("output_format", "table"),
        )
        return

    public_view = {
        k: "<redacted: structured value>" if isinstance(wallet_data[k], (dict, list)) else wallet_data[k]
        for k in sorted(_INSPECT_PUBLIC_FIELDS)
        if k in wallet_data
    }
    public_view["path"] = str(path)
    output(public_view, ctx.obj.get("output_format", "table"))


@wallet.command(
    epilog="""Examples:

  aitbc wallet rewards"""
)
@click.pass_context
def rewards(ctx):
    """View all earned rewards from staking and on-chain liquidity positions."""
    wallet_name = ctx.obj["wallet_name"]
    wallet_path = ctx.obj.get("wallet_sign_path")
    if not wallet_path or not Path(wallet_path).exists():
        error("Wallet not found")
        ctx.exit(1)
        return

    wallet_data = _load_wallet(Path(wallet_path), wallet_name)

    staking = wallet_data.get("staking", [])
    liquidity = wallet_data.get("liquidity", [])

    from decimal import Decimal as _Decimal

    def _as_number(value):
        if value is None:
            return _Decimal("0")
        try:
            return _Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError, ArithmeticError):
            return _Decimal("0")

    # Staking rewards (kept as local cache; staking is unchanged)
    staking_rewards = sum(_as_number(s.get("rewards", 0)) for s in staking if s.get("status") == "completed")
    active_staking = sum(_as_number(s["amount"]) for s in staking if s.get("status") == "active")

    pending_staking = _Decimal("0")
    for s in staking:
        if s.get("status") == "active":
            start = datetime.fromisoformat(s["start_date"])
            if start.tzinfo is None:
                start = start.replace(tzinfo=UTC)
            days = _Decimal(str(max((datetime.now(UTC) - start).total_seconds() / 86400, 0)))
            pending_staking += _as_number(s["amount"]) * (_as_number(s["apy"]) / _Decimal("100")) * (days / _Decimal("365"))

    # On-chain liquidity rewards: query the canonical pool state.
    liq_rewards = _Decimal("0")
    active_liquidity = _Decimal("0")
    pending_liquidity = _Decimal("0")
    try:
        from ...config import get_config
        from ...utils.chain_id import get_chain_id

        config = get_config()
        rpc_url = getattr(config, "blockchain_rpc_url", "http://localhost:8202")
        chain_id = get_chain_id(rpc_url)
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
        address = wallet_data.get("address", "")
        result = http_client.get(f"/rpc/liquidity/stakes/{address}?chain_id={chain_id}")
        if result.get("success"):
            for s in result.get("stakes", []):
                if s.get("status") == "active":
                    active_liquidity += _as_number(s.get("amount_ait", 0))
                    pending_liquidity += _as_number(s.get("rewards_pending_ait", 0))
                if s.get("status") == "withdrawn":
                    liq_rewards += _as_number(s.get("rewards", 0))
    except Exception:
        # Fall back to the local wallet cache if the node or endpoint is unavailable
        for r in liquidity:
            if r.get("status") == "active":
                active_liquidity += _as_number(r.get("amount", 0))
            elif r.get("status") == "completed":
                liq_rewards += _as_number(r.get("rewards", 0))

    output(
        {
            "staking_rewards_earned": str(round(staking_rewards, 6)),
            "staking_rewards_pending": str(round(pending_staking, 6)),
            "staking_active_amount": str(active_staking),
            "liquidity_rewards_earned": str(round(liq_rewards, 6)),
            "liquidity_rewards_pending": str(round(pending_liquidity, 6)),
            "liquidity_active_amount": str(active_liquidity),
            "total_earned": str(round(staking_rewards + liq_rewards, 6)),
            "total_pending": str(round(pending_staking + pending_liquidity, 6)),
            "total_staked": str(active_staking + active_liquidity),
        },
        ctx.obj.get("output_format", "table"),
    )


@wallet.command(
    epilog="""Examples:

  aitbc wallet export --destination /var/lib/aitbc/wallets/genesis.json"""
)
@click.option("--destination", help="Destination file path (default: wallet_name_export.json)")
@click.pass_context
def export(ctx, destination: str | None):
    """Export the active wallet to a JSON file at the given destination."""
    wallet_name = ctx.obj["wallet_name"]
    # export writes a copy of the wallet file — configured-dir resolution only (CLI-6c).
    wallet_path = ctx.obj["wallet_path"]

    if not wallet_path.exists():
        abort(None, wallet_write_restricted_message(find_wallet_file_report(wallet_name)))

    try:
        wallet_data = _load_wallet(wallet_path, wallet_name)

        # Generate export filename if not provided
        if not destination:
            destination = f"{wallet_name}_export.json"

        export_path = Path(destination)

        # Write export file
        with open(export_path, "w") as f:
            json.dump(wallet_data, f, indent=2)

        success(f"Wallet exported to {export_path}")
        output(
            {
                "wallet": wallet_name,
                "exported_to": str(export_path),
                "address": wallet_data.get("address"),
                "balance": wallet_data.get("balance", 0),
            },
            ctx.obj.get("output_format", "table"),
        )
    except Exception as e:
        abort(None, f"Error exporting wallet: {e}")


@wallet.command(
    epilog="""Examples:

  aitbc wallet import-wallet --file-path /var/lib/aitbc/wallets/genesis.json --name genesis"""
)
@click.option("--file-path", "file_path", required=True, help="Path to the file.")
@click.option("--name", help="New wallet name (default: from file)")
@click.pass_context
def import_wallet(ctx, file_path: str, name: str | None):
    """Import a wallet from a JSON file with an optional new name."""
    wallet_dir = ctx.obj.get("wallet_dir") or resolve_wallet_dir()
    wallet_dir.mkdir(parents=True, exist_ok=True)

    import_path = Path(file_path)

    if not import_path.exists():
        abort(None, f"Import file not found: {file_path}")

    try:
        with open(import_path) as f:
            wallet_data = json.load(f)

        # Determine wallet name
        wallet_name = name or wallet_data.get("name", import_path.stem)
        wallet_path = wallet_dir / f"{wallet_name}.json"

        if wallet_path.exists():
            if not click.confirm(f"Wallet '{wallet_name}' already exists. Overwrite?"):
                return

        # Save imported wallet
        with open(wallet_path, "w") as f:
            json.dump(wallet_data, f, indent=2)

        success(f"Wallet imported as '{wallet_name}'")
        output(
            {
                "wallet": wallet_name,
                "imported_from": str(import_path),
                "address": wallet_data.get("address"),
                "balance": wallet_data.get("balance", 0),
            },
            ctx.obj.get("output_format", "table"),
        )
    except json.JSONDecodeError:
        abort(None, "Invalid JSON file")
    except Exception as e:
        abort(None, f"Error importing wallet: {e}")
