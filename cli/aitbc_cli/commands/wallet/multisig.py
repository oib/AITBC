"""Multisig wallet commands for AITBC CLI"""

import json
import os
from datetime import datetime
from pathlib import Path

import click

from ...utils import error, output, success
from . import wallet


@wallet.command(name="multisig-create")
@click.argument("signers", nargs=-1, required=True)
@click.option("--threshold", type=int, required=True, help="Required signatures to approve")
@click.option("--name", required=True, help="Multisig wallet name")
@click.pass_context
def multisig_create(ctx, signers: tuple, threshold: int, name: str):
    """Create a multi-signature wallet"""
    wallet_dir = ctx.obj.get("wallet_dir", Path.home() / ".aitbc" / "wallets")
    wallet_dir.mkdir(parents=True, exist_ok=True)
    multisig_path = wallet_dir / f"{name}_multisig.json"

    if multisig_path.exists():
        error(f"Multisig wallet '{name}' already exists")
        return

    if threshold > len(signers):
        error(f"Threshold ({threshold}) cannot exceed number of signers ({len(signers)})")
        return

    import secrets

    multisig_data = {
        "wallet_id": name,
        "type": "multisig",
        "address": f"aitbc1ms{secrets.token_hex(18)}",
        "signers": list(signers),
        "threshold": threshold,
        "created_at": datetime.now().isoformat(),
        "balance": 0.0,
        "transactions": [],
        "pending_transactions": [],
    }

    with open(multisig_path, "w") as f:
        json.dump(multisig_data, f, indent=2)

    success(f"Multisig wallet '{name}' created ({threshold}-of-{len(signers)})")
    output(
        {
            "name": name,
            "address": multisig_data["address"],
            "signers": list(signers),
            "threshold": threshold,
        },
        ctx.obj.get("output_format", "table"),
    )


@wallet.command(name="multisig-propose")
@click.option("--wallet", "wallet_name", required=True, help="Multisig wallet name")
@click.argument("to_address")
@click.argument("amount", type=float)
@click.option("--description", help="Transaction description")
@click.pass_context
def multisig_propose(ctx, wallet_name: str, to_address: str, amount: float, description: str | None):
    """Propose a multisig transaction"""
    wallet_dir = ctx.obj.get("wallet_dir", Path.home() / ".aitbc" / "wallets")
    multisig_path = wallet_dir / f"{wallet_name}_multisig.json"

    if not multisig_path.exists():
        error(f"Multisig wallet '{wallet_name}' not found")
        return

    with open(multisig_path) as f:
        ms_data = json.load(f)

    if ms_data.get("balance", 0) < amount:
        error(f"Insufficient balance. Available: {ms_data['balance']}, Required: {amount}")
        ctx.exit(1)
        return

    import secrets

    tx_id = f"mstx_{secrets.token_hex(8)}"
    pending_tx = {
        "tx_id": tx_id,
        "to": to_address,
        "amount": amount,
        "description": description or "",
        "proposed_at": datetime.now().isoformat(),
        "proposed_by": os.environ.get("USER", "unknown"),
        "signatures": [],
        "status": "pending",
    }

    ms_data.setdefault("pending_transactions", []).append(pending_tx)
    with open(multisig_path, "w") as f:
        json.dump(ms_data, f, indent=2)

    success(f"Transaction proposed: {tx_id}")
    output(
        {
            "tx_id": tx_id,
            "to": to_address,
            "amount": amount,
            "signatures_needed": ms_data["threshold"],
            "status": "pending",
        },
        ctx.obj.get("output_format", "table"),
    )


@wallet.command(name="multisig-sign")
@click.option("--wallet", "wallet_name", required=True, help="Multisig wallet name")
@click.argument("tx_id")
@click.option("--signer", required=True, help="Signer address")
@click.pass_context
def multisig_sign(ctx, wallet_name: str, tx_id: str, signer: str):
    """Sign a pending multisig transaction"""
    wallet_dir = ctx.obj.get("wallet_dir", Path.home() / ".aitbc" / "wallets")
    multisig_path = wallet_dir / f"{wallet_name}_multisig.json"

    if not multisig_path.exists():
        error(f"Multisig wallet '{wallet_name}' not found")
        return

    with open(multisig_path) as f:
        ms_data = json.load(f)

    if signer not in ms_data.get("signers", []):
        error(f"'{signer}' is not an authorized signer")
        ctx.exit(1)
        return

    pending = ms_data.get("pending_transactions", [])
    tx = next((t for t in pending if t["tx_id"] == tx_id and t["status"] == "pending"), None)

    if not tx:
        error(f"Pending transaction '{tx_id}' not found")
        ctx.exit(1)
        return

    if signer in tx["signatures"]:
        error(f"'{signer}' has already signed this transaction")
        return

    tx["signatures"].append(signer)

    # Check if threshold met
    if len(tx["signatures"]) >= ms_data["threshold"]:
        tx["status"] = "approved"
        # Execute the transaction
        ms_data["balance"] = ms_data.get("balance", 0) - tx["amount"]
        ms_data["transactions"].append(
            {
                "type": "multisig_send",
                "amount": -tx["amount"],
                "to": tx["to"],
                "tx_id": tx["tx_id"],
                "signatures": tx["signatures"],
                "timestamp": datetime.now().isoformat(),
            }
        )
        success(f"Transaction {tx_id} approved and executed!")
    else:
        success(f"Signed. {len(tx['signatures'])}/{ms_data['threshold']} signatures collected")

    with open(multisig_path, "w") as f:
        json.dump(ms_data, f, indent=2)

    output(
        {
            "tx_id": tx_id,
            "signatures": tx["signatures"],
            "threshold": ms_data["threshold"],
            "status": tx["status"],
        },
        ctx.obj.get("output_format", "table"),
    )
