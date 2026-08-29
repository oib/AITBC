"""
Market commands for GPU/software offers published by shop miners.
"""

import hashlib
import json
import os
import re
import socket
from datetime import datetime
from typing import Any

import click

from ...config import get_config
from ...utils import error, info, output, success, warning
from ...utils.address import to_canonical
from ...utils.http_client import AITBCHTTPClient, NetworkError, get_logger
from ...utils.island_credentials import load_island_credentials
from ...utils.wallet_loader import load_wallet_for_payment
from ...utils.wallet_paths import find_wallet_file

# Initialize logger
logger = get_logger(__name__)


def safe_load_credentials():
    """Load island credentials - required for production, except for hub nodes"""
    try:
        return load_island_credentials()
    except FileNotFoundError as e:
        # Check if this is a hub node - hubs don't need island credentials
        _ = get_config()
        node_role = os.getenv("NODE_ROLE", "")
        if node_role == "hub":
            # Hub nodes use blockchain config instead
            return {
                "credentials": {"p2p_port": 8200},
                "island_id": os.getenv("ISLAND_ID", "ait-hub"),
                "chain_id": os.getenv("CHAIN_ID", "ait-hub.aitbc.bubuit.net"),
            }
        error(f"Island credentials required for marketplace operations: {e}")
        error("Note: Hub nodes do not need to join islands - marketplace works with blockchain config")
        error("For follower nodes, run: aitbc node island join <island_id> <island_name> <chain_id>")
        error("Example: aitbc edge island join ait-hub.aitbc.bubuit.net-island 'AIT Hub' ait-hub.aitbc.bubuit.net")
        return None


def get_chain_id() -> str:
    """Get chain ID from island credentials or blockchain config"""
    try:
        creds = load_island_credentials()
        # Credentials use 'island_chain_id' key
        chain_id = creds.get("island_chain_id") or creds.get("chain_id")
        if chain_id:
            return str(chain_id)
    except (FileNotFoundError, ValueError):
        logger.debug("Island credentials not available for chain_id", exc_info=True)
        pass
    # Fall back to hub discovery URL config
    config = get_config()
    hub = config.hub_discovery_url or "hub.aitbc.bubuit.net"
    return f"ait-{hub}"


def get_island_id() -> str:
    """Get island ID from island credentials or blockchain config for hub nodes"""
    env_island = os.getenv("ISLAND_ID")
    if env_island:
        return env_island
    try:
        island_id = load_island_credentials().get("island_id")
        if island_id:
            return str(island_id)
    except FileNotFoundError:
        pass
    # Hub / shop / follower nodes all publish to the hub island by default.
    return os.getenv("ISLAND_ID", "ait-hub")


def _wallet_address(wallet: dict[str, Any]) -> str | None:
    metadata = wallet.get("metadata", {})
    return metadata.get("address") or metadata.get("original_address")


def _account_balance(address: str, chain_id: str) -> int:
    """Query the hub for the canonical account balance of an address."""
    try:
        config = get_config()
        hub = config.hub_discovery_url or "hub.aitbc.bubuit.net"
        client = AITBCHTTPClient(base_url=f"http://{hub}", timeout=5)
        data = client.get(f"/rpc/accounts/{address}", params={"chain_id": chain_id})
        return int(data.get("balance", 0))
    except Exception as e:
        logger.debug("Could not get balance for %s: %s", address, e)
        return 0


def get_wallet_address() -> str:
    """Get a funded provider address from the wallet service.

    P2.5: marketplace offers require a sender with enough balance to pay the
    listing fee (36 compute-units) and, historically, picked my-agent-wallet
    even when it had a zero balance. We now prefer a wallet that can actually
    afford the transaction.
    """
    env_address = os.getenv("SHOP_WALLET_ADDRESS")
    if env_address:
        return env_address

    # Try wallet service API first
    wallets: list[dict[str, Any]] = []
    try:
        http_client = AITBCHTTPClient(base_url="http://localhost:8108", timeout=5)
        response = http_client.get("/v1/wallets")
        wallets = response.get("items", []) if response else []
    except Exception as e:
        logger.warning("Failed to get wallet from service: %s", e)

    if wallets:
        chain_id = get_chain_id()
        # Pick the first wallet that can pay the minimum listing fee.
        for wallet in wallets:
            address = _wallet_address(wallet)
            if address and _account_balance(address, chain_id) >= 36:
                return str(address)
        # Fall back to a hard-coded shop wallet or the first wallet.
        for wallet in wallets:
            address = _wallet_address(wallet)
            if address:
                return str(address)

    # Fallback to local file wallet in the standard directory.
    wallet_path = find_wallet_file("genesis")
    if wallet_path is not None and wallet_path.exists():
        try:
            with open(wallet_path) as f:
                wallet = json.load(f)
                address = wallet.get("address")
                if address:
                    return str(address)
        except Exception as e:
            logger.warning("Failed to load local wallet: %s", e)

    # No wallet available
    error("No wallet address available. Ensure wallet service is running or wallet file exists.")
    raise click.Abort()


def get_account_nonce(address: str, chain_id: str) -> int:
    """Query blockchain for current account nonce"""
    from aitbc.network import AITBCHTTPClient

    config = get_config()
    rpc_url = config.blockchain_rpc_url or "http://localhost:8202"
    # Prefer the local blockchain RPC; the hub discovery URL may not expose /rpc.
    for base_url in (rpc_url, f"http://{config.hub_discovery_url or 'hub.aitbc.bubuit.net'}"):
        try:
            http_client = AITBCHTTPClient(base_url=base_url, timeout=10)
            response = http_client.get(f"/rpc/accounts/{address}?chain_id={chain_id}")
            nonce = response.get("nonce", 0)
            return int(nonce) if nonce is not None else 0
        except Exception as e:
            logger.debug("Failed to get nonce from %s: %s", base_url, e)
            continue
    error(f"Failed to get account nonce for {address}")
    return 0


def get_next_nonce(wallet_address: str | None = None) -> int:
    """Get next transaction nonce from blockchain (confirmed nonce + 1)."""
    if not wallet_address:
        wallet_address = get_wallet_address()
    config = get_config()
    hub_url = config.hub_discovery_url or "hub.aitbc.bubuit.net"
    chain_id = "ait-" + hub_url
    return get_account_nonce(wallet_address, chain_id)


def get_market_wallet(ctx, require_private_key: bool = False) -> tuple[str, str | None, str]:
    """Resolve the wallet used by market commands.

    Priority: group-level --wallet / --wallet-path, then the
    ``SHOP_WALLET_ADDRESS`` / ``AITBC_MARKET_WALLET`` environment, then
    configuration.  Returns ``(address, private_key_or_none, wallet_name)``.
    """
    wallet_name = ctx.obj.get("market_wallet")
    wallet_path = ctx.obj.get("market_wallet_path")
    password = ctx.obj.get("market_password")

    # If no wallet was specified on the command line, fall back to the shop
    # environment.  This keeps backwards compatibility for unattended offers
    # while still allowing a human buyer to pass --wallet for paid jobs.
    if not wallet_name and not wallet_path and not require_private_key:
        shop_address = os.environ.get("SHOP_WALLET_ADDRESS")
        if shop_address:
            return shop_address, None, "shop"

    return load_wallet_for_payment(
        ctx,
        wallet_name=wallet_name,
        wallet_path=wallet_path,
        password=password,
        require_private_key=require_private_key,
    )


@click.group(
    epilog="""Examples:

  aitbc market list

  aitbc market run --offer-id-or-plugin-id offer-1 --prompt 'hello'"""
)
@click.option("--wallet", "market_wallet", help="Wallet name for market payments")
@click.option("--wallet-path", "market_wallet_path", help="Direct wallet file path (overrides --wallet)")
@click.option("--password", "market_password", help="Wallet password")
@click.option("--password-file", "market_password_file", type=click.Path(exists=True), help="Wallet password file")
@click.pass_context
def market(ctx, market_wallet, market_wallet_path, market_password, market_password_file):
    """GPU and software marketplace offers published by shop miners and backed by the coordinator."""
    ctx.ensure_object(dict)
    ctx.obj["market_wallet"] = market_wallet
    ctx.obj["market_wallet_path"] = market_wallet_path
    ctx.obj["market_password"] = market_password

    if market_password_file:
        with open(market_password_file) as f:
            ctx.obj["market_password"] = f.read().strip() or market_password


# Import submodules to register all commands
from . import escrow, exchange, jobs, offers, ratings
from .escrow import _escrow_create, _get_blockchain_rpc_url

market.add_command(escrow.escrow)
