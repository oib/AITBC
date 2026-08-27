"""Misc wallet commands for AITBC CLI"""

import json
from datetime import datetime
from decimal import InvalidOperation
from pathlib import Path

import click

from aitbc.utils import ait_to_seconds
from aitbc.utils.validation import validate_address_strict
from ...utils import error, output, success
from ...utils.wallet_paths import wallet_dir as resolve_wallet_dir
from . import _load_wallet, wallet


@wallet.command()
@click.pass_context
def rewards(ctx):
    """View all earned rewards (staking + liquidity)"""
    wallet_name = ctx.obj["wallet_name"]
    wallet_path = ctx.obj.get("wallet_path")
    if not wallet_path or not Path(wallet_path).exists():
        error("Wallet not found")
        ctx.exit(1)
        return

    wallet_data = _load_wallet(Path(wallet_path), wallet_name)

    staking = wallet_data.get("staking", [])
    liquidity = wallet_data.get("liquidity", [])

    # Staking rewards
    staking_rewards = sum(s.get("rewards", 0) for s in staking if s.get("status") == "completed")
    active_staking = sum(s["amount"] for s in staking if s.get("status") == "active")

    # Liquidity rewards
    liq_rewards = sum(r.get("rewards", 0) for r in liquidity if r.get("status") == "completed")
    active_liquidity = sum(r["amount"] for r in liquidity if r.get("status") == "active")

    # Estimate pending rewards for active positions
    pending_staking = 0
    for s in staking:
        if s.get("status") == "active":
            start = datetime.fromisoformat(s["start_date"])
            days = max((datetime.now() - start).total_seconds() / 86400, 0)
            pending_staking += s["amount"] * (s["apy"] / 100) * (days / 365)

    pending_liquidity = 0
    for r in liquidity:
        if r.get("status") == "active":
            start = datetime.fromisoformat(r["start_date"])
            days = max((datetime.now() - start).total_seconds() / 86400, 0)
            pending_liquidity += r["amount"] * (r["apy"] / 100) * (days / 365)

    output(
        {
            "staking_rewards_earned": round(staking_rewards, 6),
            "staking_rewards_pending": round(pending_staking, 6),
            "staking_active_amount": active_staking,
            "liquidity_rewards_earned": round(liq_rewards, 6),
            "liquidity_rewards_pending": round(pending_liquidity, 6),
            "liquidity_active_amount": active_liquidity,
            "total_earned": round(staking_rewards + liq_rewards, 6),
            "total_pending": round(pending_staking + pending_liquidity, 6),
            "total_staked": active_staking + active_liquidity,
        },
        ctx.obj.get("output_format", "table"),
    )


@wallet.command()
@click.argument("address")
@click.option("--amount", default=3600000000, help="Amount to request from faucet in compute-seconds (default: 3600000000)")
@click.option("--amount-ait", default=None, help="Amount to request from faucet in AIT (overrides --amount)")
@click.option("--chain-id", help="Chain ID (defaults to node's chain)")
@click.pass_context
def fund(ctx, address: str, amount: int, amount_ait: str | None, chain_id: str):
    """Fund wallet using blockchain faucet"""
    import httpx

    from ...config import get_config
    from ...utils.chain_id import get_chain_id

    config = get_config()
    rpc_url = config.blockchain_rpc_url if hasattr(config, "blockchain_rpc_url") else "http://localhost:8202"

    # Get chain_id
    if not chain_id:
        chain_id = get_chain_id(rpc_url)

    # Convert AIT to compute-seconds if requested
    if amount_ait is not None:
        # Passed through as a string so ait_to_seconds parses it as a Decimal
        # instead of a float that click already rounded.
        try:
            amount = int(ait_to_seconds(amount_ait))
        except (InvalidOperation, ValueError):
            error(f"Invalid --amount-ait: {amount_ait}")
            return

    # Normalize and validate address (canonical 0x only)
    try:
        address = validate_address_strict(address).lower()
    except Exception as e:
        error(f"Invalid address: {e}")
        return

    # Call faucet endpoint at /rpc/faucet
    faucet_url = f"{rpc_url}/rpc/faucet"
    faucet_data = {"address": address, "amount": amount, "chain_id": chain_id}

    try:
        response = httpx.post(faucet_url, json=faucet_data, timeout=10)
        response.raise_for_status()
        result = response.json()

        if result.get("success"):
            success(f"Successfully funded wallet {address} with {amount} units")
            output(result, ctx.obj.get("output_format", "table"))
        else:
            error(f"Failed to fund wallet: {result.get('message', 'Unknown error')}")
    except httpx.HTTPError as e:
        error(f"HTTP error calling faucet: {e}")
    except Exception as e:
        error(f"Error funding wallet: {e}")


@wallet.command()
@click.option("--destination", help="Destination file path (default: wallet_name_export.json)")
@click.pass_context
def export(ctx, destination: str | None):
    """Export wallet to JSON file"""
    wallet_name = ctx.obj["wallet_name"]
    wallet_path = ctx.obj["wallet_path"]

    if not wallet_path.exists():
        error(f"Wallet '{wallet_name}' not found")
        return

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
        error(f"Error exporting wallet: {e}")


@wallet.command()
@click.argument("file_path")
@click.option("--name", help="New wallet name (default: from file)")
@click.pass_context
def import_wallet(ctx, file_path: str, name: str | None):
    """Import wallet from JSON file"""
    wallet_dir = ctx.obj.get("wallet_dir") or resolve_wallet_dir()
    wallet_dir.mkdir(parents=True, exist_ok=True)

    import_path = Path(file_path)

    if not import_path.exists():
        error(f"Import file not found: {file_path}")
        return

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
        error("Invalid JSON file")
    except Exception as e:
        error(f"Error importing wallet: {e}")
