"""Performance bond commands for providers and agents."""

from __future__ import annotations

import json
import os
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

import click

from aitbc.crypto.crypto import derive_ethereum_address, sign_transaction_hash
from aitbc.utils import ait_to_seconds, format_ait
from aitbc.utils.units import seconds_to_ait

from ..config import get_config
from ..utils import DECIMAL, error, output, success
from ..utils.crypto_utils import bech32_to_hex
from ..utils.error_handling import abort
from ..utils.http_client import AITBCHTTPClient, NetworkError


def _api_client() -> AITBCHTTPClient | None:
    """Return a client for the coordinator API if a URL is configured."""
    config = get_config()
    url = config.coordinator_api_url or os.getenv("COORDINATOR_API_URL", "")
    if not url:
        return None
    return AITBCHTTPClient(base_url=url, timeout=config.timeout, api_key=config.api_key or "")





def _chain_id() -> str:
    """Return the active chain id, defaulting to the environment."""
    from ..utils.chain_id import get_chain_id

    config = get_config()
    rpc_url = _rpc_url_base()
    return get_chain_id(rpc_url, override=None, timeout=5)


def _rpc_url_base() -> str:
    """Return the raw blockchain RPC URL without the /rpc suffix."""
    config = get_config()
    return getattr(config, "blockchain_rpc_url", None) or os.getenv("HUB_RPC_URL") or os.getenv("BLOCKCHAIN_RPC_URL") or "http://localhost:8202"


def _rpc_client() -> AITBCHTTPClient:
    """Return a client for the blockchain RPC."""
    rpc_url = _rpc_url_base().rstrip("/")
    if not rpc_url.endswith("/rpc"):
        rpc_url = f"{rpc_url}/rpc"
    return AITBCHTTPClient(base_url=rpc_url, timeout=30)


def _get_nonce(address: str) -> int:
    client = _rpc_client()
    try:
        data = client.get(f"/account/{address}")
        return data.get("nonce", 0)
    except Exception:
        return 0


def _find_wallet_path(wallet_name: str) -> Path | None:
    """Locate a wallet file by name."""
    config = get_config()
    wallet_dir = Path(getattr(config, "wallet_dir", os.path.expanduser("~/.aitbc/wallets")))
    for candidate in [wallet_dir / f"{wallet_name}.json", Path(os.path.expanduser(f"~/.aitbc/wallets/{wallet_name}.json"))]:
        if candidate.exists():
            return candidate
    return None


def _load_wallet(wallet_path: Path, wallet_name: str) -> dict[str, Any]:
    """Load wallet data and decrypt the private key if needed."""
    with open(wallet_path) as f:
        wallet_data: dict[str, Any] = json.load(f)

    if wallet_data.get("encrypted") and "private_key" in wallet_data:
        priv = wallet_data["private_key"]
        if isinstance(priv, str):
            return wallet_data  # legacy plaintext
        from ..commands.wallet import decrypt_value, _get_wallet_password

        password = _get_wallet_password(wallet_name)
        wallet_data["private_key"] = decrypt_value(priv, password)
    return wallet_data


def _sign_tx(wallet_data: dict[str, Any], tx_data: dict[str, Any]) -> str:
    """Sign the canonical transaction data with the wallet's private key."""
    from eth_utils import keccak

    private_key = wallet_data.get("private_key")
    if not private_key:
        raise click.ClickException("Wallet private key is not available")

    signable = {k: v for k, v in tx_data.items() if k != "signature"}
    if "amount" in signable:
        signable.pop("value", None)
    message = json.dumps(signable, sort_keys=True, separators=(",", ":")).encode()
    message_hash = keccak(message).hex()
    return sign_transaction_hash(message_hash, str(private_key))


def _default_bond_escrow() -> str:
    """Return the deterministic bond escrow address used by the chain."""
    from eth_utils import keccak

    return "0x" + keccak(b"aitbc.bond.escrow").hex()[:40]


def _get_bond_escrow() -> str:
    return os.getenv("BOND_ESCROW_ADDRESS") or _default_bond_escrow()


@click.group()
def bond():
    """Provider performance bond lifecycle commands."""
    pass


@bond.command()
@click.argument("amount", type=DECIMAL)
@click.option("--wallet", "wallet_name", default="default", help="Wallet name to use")
@click.option("--lock-days", default=30, help="Days the bond is locked")
@click.option("--bond-id", default="", help="Optional bond ID; generated if omitted")
@click.pass_context
def create(ctx, amount: Decimal, wallet_name: str, lock_days: int, bond_id: str):
    """Lock a performance bond on-chain."""
    wallet_path = _find_wallet_path(wallet_name)
    if not wallet_path or not wallet_path.exists():
        error(f"Wallet '{wallet_name}' not found")
        return

    wallet_data = _load_wallet(wallet_path, wallet_name)
    provider_hex = bech32_to_hex(wallet_data["address"])
    chain_id = _chain_id()
    amount_seconds = ait_to_seconds(amount)

    if not bond_id:
        bond_id = f"bond_{provider_hex}_{int(time.time())}"

    tx = {
        "from": provider_hex,
        "to": _get_bond_escrow(),
        "amount": amount_seconds,
        "value": amount_seconds,
        "fee": max(36, amount_seconds // 100),
        "nonce": _get_nonce(provider_hex),
        "type": "BOND_LOCK",
        "chain_id": chain_id,
        "payload": {
            "bond_id": bond_id,
            "provider": provider_hex,
            "lock_days": lock_days,
        },
    }
    tx["signature"] = _sign_tx(wallet_data, tx)

    client = _rpc_client()
    try:
        result = client.post("/transactions/marketplace", json=tx)
        success(f"Bond lock submitted: {bond_id}")
        output(
            {
                "bond_id": bond_id,
                "provider": provider_hex,
                "amount": str(amount),
                "amount_seconds": amount_seconds,
                "lock_days": lock_days,
                "tx_hash": result.get("transaction_hash"),
                "chain_id": chain_id,
            },
            ctx.obj.get("output_format", "table"),
        )
    except Exception as e:
        error(f"Failed to submit bond lock: {e}")


@bond.command()
@click.option("--bond-id", help="Bond ID to query")
@click.option("--provider", help="Provider address to list bonds for")
@click.pass_context
def status(ctx, bond_id: str | None, provider: str | None):
    """Show bond status or list bonds for a provider."""
    client = _rpc_client()
    try:
        if bond_id:
            result = client.get(f"/bond/{bond_id}")
        elif provider:
            result = client.get(f"/bond/provider/{provider}")
        else:
            error("--bond-id or --provider is required")
            return
        output(result, ctx.obj.get("output_format", "table"), title="Bond Status")
    except NetworkError as e:
        abort(ctx, f"Blockchain RPC error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error fetching bond status: {e}", from_exception=e)


@bond.command()
@click.argument("bond-id")
@click.option("--wallet", "wallet_name", default="default", help="Wallet name to use")
@click.pass_context
def release(ctx, bond_id: str, wallet_name: str):
    """Release a matured bond back to the provider."""
    wallet_path = _find_wallet_path(wallet_name)
    if not wallet_path or not wallet_path.exists():
        error(f"Wallet '{wallet_name}' not found")
        return

    wallet_data = _load_wallet(wallet_path, wallet_name)
    provider_hex = bech32_to_hex(wallet_data["address"])
    chain_id = _chain_id()

    tx = {
        "from": provider_hex,
        "to": provider_hex,
        "amount": 0,
        "value": 0,
        "fee": 36,
        "nonce": _get_nonce(provider_hex),
        "type": "BOND_RELEASE",
        "chain_id": chain_id,
        "payload": {
            "bond_id": bond_id,
            "provider": provider_hex,
        },
    }
    tx["signature"] = _sign_tx(wallet_data, tx)

    client = _rpc_client()
    try:
        result = client.post("/transactions/marketplace", json=tx)
        success(f"Bond release submitted: {bond_id}")
        output(
            {"bond_id": bond_id, "tx_hash": result.get("transaction_hash"), "chain_id": chain_id},
            ctx.obj.get("output_format", "table"),
        )
    except Exception as e:
        error(f"Failed to submit bond release: {e}")


@bond.command()
@click.argument("bond-id")
@click.option("--amount", default="0", help="Amount to add to the bond")
@click.option("--token", default="AITBC", help="Token symbol")
@click.pass_context
def top_up(ctx, bond_id: str, amount: str, token: str):
    """Top up a provider's performance bond."""
    client = _api_client()
    try:
        if client is None:
            result = {
                "bond_id": bond_id,
                "action": "bond_top_up",
                "amount": amount,
                "token": token,
                "status": "simulated",
            }
        else:
            result = client.post(
                f"/v1/marketplace/bonds/{bond_id}/top-up",
                json={"amount": amount, "token": token},
            )
        output(result, ctx.obj.get("output_format", "table"), title="Bond Top-Up")
    except NetworkError as e:
        abort(ctx, f"Coordinator API error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error topping up bond for {bond_id}: {e}", from_exception=e)


@bond.command()
@click.argument("bond-id")
@click.option("--reason", default="", help="Reason for the appeal")
@click.option("--evidence", default="", help="Evidence URL or CID")
@click.pass_context
def appeal(ctx, bond_id: str, reason: str, evidence: str):
    """Appeal a slashing decision for a bond."""
    client = _api_client()
    try:
        if client is None:
            result = {
                "bond_id": bond_id,
                "action": "slash_appeal",
                "reason": reason,
                "evidence": evidence,
                "status": "simulated",
            }
        else:
            result = client.post(
                "/v1/governance/slash-appeals",
                json={"bond_id": bond_id, "reason": reason, "evidence": [evidence] if evidence else []},
            )
        output(result, ctx.obj.get("output_format", "table"), title="Slash Appeal")
    except NetworkError as e:
        abort(ctx, f"Coordinator API error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error submitting slash appeal for {bond_id}: {e}", from_exception=e)
