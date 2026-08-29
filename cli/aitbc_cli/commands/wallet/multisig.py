"""Multisig wallet commands for AITBC CLI"""

import json
import os
from datetime import datetime
from decimal import Decimal

import click
from eth_utils import to_checksum_address

from ...utils import DECIMAL, error, output, success
from ...utils.money import wallet_amount as _wallet_amount
from ...utils.wallet_paths import wallet_dir as resolve_wallet_dir
from . import wallet


@wallet.command(
    name="multisig-create",
    epilog="""Examples:

  aitbc wallet multisig-create --signers 0xA... --signers 0xB... --threshold 2 --name team-wallet""",
)
@click.option("--signers", "signers", required=True, multiple=True, help="One or more signer addresses.")
@click.option("--threshold", type=int, required=True, help="Required signatures to approve")
@click.option("--name", required=True, help="Multisig wallet name")
@click.pass_context
def multisig_create(ctx, signers: tuple, threshold: int, name: str):
    """Create a multi-signature wallet with a threshold and a list of signers."""
    wallet_dir = ctx.obj.get("wallet_dir") or resolve_wallet_dir()
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
        "address": to_checksum_address(f"0x{secrets.token_hex(20)}"),
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


@wallet.command(
    name="multisig-propose",
    epilog="""Examples:

  aitbc wallet multisig-propose --wallet team-wallet --to-address 0xAbc... --amount 5.0""",
)
@click.option("--wallet", "wallet_name", required=True, help="Multisig wallet name")
@click.option("--to-address", "to_address", required=True, help="Destination address.")
@click.option("--amount", "amount", required=True, type=DECIMAL, help="Amount of AIT.")
@click.option("--description", help="Transaction description")
@click.pass_context
def multisig_propose(ctx, wallet_name: str, to_address: str, amount: Decimal, description: str | None):
    """Propose a multi-signature payment to a destination address."""
    wallet_dir = ctx.obj.get("wallet_dir") or resolve_wallet_dir()
    multisig_path = wallet_dir / f"{wallet_name}_multisig.json"

    if not multisig_path.exists():
        error(f"Multisig wallet '{wallet_name}' not found")
        return

    with open(multisig_path) as f:
        ms_data = json.load(f)

    if _wallet_amount(ms_data.get("balance", 0)) < amount:
        error(f"Insufficient balance. Available: {ms_data['balance']}, Required: {amount}")
        ctx.exit(1)
        return

    import secrets

    tx_id = f"mstx_{secrets.token_hex(8)}"
    pending_tx = {
        "tx_id": tx_id,
        "to": to_address,
        "amount": str(amount),
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
            "amount": str(amount),
            "signatures_needed": ms_data["threshold"],
            "status": "pending",
        },
        ctx.obj.get("output_format", "table"),
    )


@wallet.command(
    name="multisig-sign",
    epilog="""Examples:

  aitbc wallet multisig-sign --wallet team-wallet --tx-id tx-1234 --signer 0xAbc...""",
)
@click.option("--wallet", "wallet_name", required=True, help="Multisig wallet name")
@click.option("--tx-id", "tx_id", required=True, help="Transaction ID.")
@click.option("--signer", required=True, help="Signer address")
@click.pass_context
def multisig_sign(ctx, wallet_name: str, tx_id: str, signer: str):
    """Sign a pending multi-signature transaction with the given signer address."""
    wallet_dir = ctx.obj.get("wallet_dir") or resolve_wallet_dir()
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
