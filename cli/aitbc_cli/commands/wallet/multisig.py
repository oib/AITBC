"""Multisig wallet commands for AITBC CLI"""

import json
import os
from datetime import datetime
from decimal import Decimal

import click
from eth_utils import to_checksum_address

from ...config import get_config
from ...utils import DECIMAL, error, output, success
from ...utils.error_handling import abort
from ...utils.http_client import AITBCHTTPClient, http_response_status
from ...utils.wallet_loader import validate_wallet_name, write_json_0600
from ...utils.wallet_paths import wallet_dir as resolve_wallet_dir
from aitbc.utils.units import units_to_ait
from . import wallet


def _multisig_chain_balance(address: str) -> Decimal | None:
    """Live on-chain balance (AIT) for the multisig address.

    None when the account lookup fails — a failed lookup must not read as
    zero OR as the stale local figure; callers abort instead (#2196).
    """
    try:
        config = get_config()
        rpc_url = config.blockchain_rpc_url or "http://localhost:8202"
        account = AITBCHTTPClient(base_url=rpc_url, timeout=10).get(f"/rpc/account/{address}")
        if account.get("balance") is None:
            return None
        return units_to_ait(int(account["balance"]))
    except Exception as e:  # noqa: BLE001 - any transport/parse failure means "unknown"
        # #2362: a 404 means the account does not exist on-chain — that is a
        # zero balance, not an RPC outage. Reporting it as "check node
        # reachability" sent operators chasing connectivity for an unfunded
        # address.
        if http_response_status(e) == 404:
            return Decimal(0)
        return None


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
    """Create a multi-signature wallet with a threshold and a list of signers.

    .. warning::
        The generated address is a *record-keeping* multisig — there is no
        on-chain multisig primitive and no private key exists for the
        address. Funds sent to it are unrecoverable; ``multisig-propose`` /
        ``multisig-sign`` only track approvals locally. Use it for bookkeeping
        or settle through an escrow flow / authorized signer key instead.
    """
    try:
        validate_wallet_name(name)
    except ValueError as e:
        abort(None, str(e))
        return
    wallet_dir = ctx.obj.get("wallet_dir") or resolve_wallet_dir()
    wallet_dir.mkdir(parents=True, exist_ok=True)
    multisig_path = wallet_dir / f"{name}_multisig.json"

    if multisig_path.exists():
        abort(None, f"Multisig wallet '{name}' already exists")

    if threshold > len(signers):
        abort(None, f"Threshold ({threshold}) cannot exceed number of signers ({len(signers)})")

    import secrets

    multisig_data = {  # not-money: stub/demo response, not a live amount
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

    write_json_0600(multisig_path, multisig_data)

    success(f"Multisig wallet '{name}' created ({threshold}-of-{len(signers)})")
    click.echo(
        "Warning: this address has no spendable key — funds sent to it are "
        "unrecoverable. Multisig propose/sign are local records only.",
        err=True,
    )
    output(
        {
            "name": name,
            "address": multisig_data["address"],
            "signers": list(signers),
            "threshold": threshold,
            "warning": "address is unspendable — no private key exists; local records only",
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
    try:
        validate_wallet_name(wallet_name)
    except ValueError as e:
        abort(None, str(e))
        return

    wallet_dir = ctx.obj.get("wallet_dir") or resolve_wallet_dir()
    multisig_path = wallet_dir / f"{wallet_name}_multisig.json"

    if not multisig_path.exists():
        abort(None, f"Multisig wallet '{wallet_name}' not found")

    with open(multisig_path) as f:
        ms_data = json.load(f)

    # The stored ``balance`` is a creation-time 0 that nothing ever updates —
    # sufficiency must come from the chain, same rule as the token wallets
    # (#2196). A failed lookup aborts rather than proposing against an
    # unknown balance.
    chain_balance = _multisig_chain_balance(ms_data["address"])
    if chain_balance is None:
        abort(None, f"Cannot verify multisig balance on-chain for {ms_data['address']} — check --rpc-url / node reachability")
        return
    ms_data["balance"] = str(chain_balance)
    write_json_0600(multisig_path, ms_data)
    if chain_balance < amount:
        error(f"Insufficient balance. Available: {chain_balance} AIT, Required: {amount} AIT")
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
    write_json_0600(multisig_path, ms_data)

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
    try:
        validate_wallet_name(wallet_name)
    except ValueError as e:
        abort(None, str(e))
        return

    wallet_dir = ctx.obj.get("wallet_dir") or resolve_wallet_dir()
    multisig_path = wallet_dir / f"{wallet_name}_multisig.json"

    if not multisig_path.exists():
        abort(None, f"Multisig wallet '{wallet_name}' not found")

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
        abort(None, f"'{signer}' has already signed this transaction")

    tx["signatures"].append(signer)

    # Check if threshold met
    if len(tx["signatures"]) >= ms_data["threshold"]:
        tx["status"] = "approved"
        # There is no on-chain multisig primitive: "execution" records the
        # approval for manual follow-up and must NOT fake a balance move —
        # the old local debit read as a settlement that never happened
        # (#2196).
        ms_data["transactions"].append(
            {
                "type": "multisig_approved",
                "amount": tx["amount"],
                "to": tx["to"],
                "tx_id": tx["tx_id"],
                "signatures": tx["signatures"],
                "timestamp": datetime.now().isoformat(),
            }
        )
        success(f"Transaction {tx_id} approved ({len(tx['signatures'])}/{ms_data['threshold']} signatures)")
        warning = (
            "Approved locally only — no on-chain transaction was broadcast. "
            "Multisig execution is not supported on-chain; settle via 'aitbc wallet send' "
            "from an authorized key or an escrow flow."
        )
    else:
        success(f"Signed. {len(tx['signatures'])}/{ms_data['threshold']} signatures collected")
        warning = None

    write_json_0600(multisig_path, ms_data)

    result = {
        "tx_id": tx_id,
        "signatures": tx["signatures"],
        "threshold": ms_data["threshold"],
        "status": tx["status"],
    }
    if warning:
        result["warning"] = warning
    output(result, ctx.obj.get("output_format", "table"))
