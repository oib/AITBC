"""
Blockchain marketplace commands for GPU trading
"""

import hashlib
import json
import os
import re
import socket
from datetime import datetime

import click

from ...config import get_config
from ...utils import error, info, output, success, warning
from ...utils.http_client import AITBCHTTPClient, NetworkError, get_logger
from ...utils.island_credentials import load_island_credentials

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
        error("For follower nodes, run: aitbc edge island join <island_id> <island_name> <chain_id>")
        error("Example: aitbc edge island join ait-hub.aitbc.bubuit.net-island 'AIT Hub' ait-hub.aitbc.bubuit.net")
        return None


def get_chain_id() -> str:
    """Get chain ID from island credentials or blockchain config"""
    try:
        creds = load_island_credentials()
        # Credentials use 'island_chain_id' key
        chain_id = creds.get("island_chain_id") or creds.get("chain_id")
        if chain_id:
            return chain_id
    except (FileNotFoundError, ValueError):
        pass
    # Fall back to hub discovery URL config
    config = get_config()
    hub = config.hub_discovery_url or "hub.aitbc.bubuit.net"
    return f"ait-{hub}"


def get_island_id() -> str:
    """Get island ID from island credentials or blockchain config for hub nodes"""
    try:
        return load_island_credentials().get("island_id")
    except FileNotFoundError:
        # Hub nodes use blockchain config
        node_role = os.getenv("NODE_ROLE", "")
        if node_role == "hub":
            return os.getenv("ISLAND_ID", "ait-hub")
        error("Island credentials required for island ID")
        raise click.Abort() from None


def get_wallet_address() -> str:
    """Get address from wallet service - use my-agent-wallet which exists on blockchain"""
    # Try wallet service API first
    try:
        http_client = AITBCHTTPClient(base_url="http://localhost:8108", timeout=5)
        wallets = http_client.get("/v1/wallets")
        if wallets and wallets.get("items"):
            # Use my-agent-wallet which exists on the blockchain
            for wallet in wallets["items"]:
                if wallet.get("wallet_id") == "my-agent-wallet":
                    metadata = wallet.get("metadata", {})
                    address = metadata.get("address") or metadata.get("original_address")
                    if address:
                        return address
            # Fallback to first wallet if my-agent-wallet not found
            genesis_wallet = wallets["items"][0]
            metadata = genesis_wallet.get("metadata", {})
            address = metadata.get("address") or metadata.get("original_address")
            if address:
                return address
    except Exception as e:
        logger.warning("Failed to get wallet from service: %s", e)

    # Fallback to local wallet file
    wallet_path = "/root/.aitbc/wallets/genesis.json"
    if os.path.exists(wallet_path):
        try:
            with open(wallet_path) as f:
                wallet = json.load(f)
                return wallet.get("address")
        except Exception as e:
            logger.warning("Failed to load local wallet: %s", e)

    # No wallet available
    error("No wallet address available. Ensure wallet service is running or wallet file exists.")
    raise click.Abort()


def get_account_nonce(address: str, chain_id: str) -> int:
    """Query blockchain for current account nonce"""
    try:
        from aitbc.network import AITBCHTTPClient

        config = get_config()
        hub_url = f"http://{config.hub_discovery_url or 'hub.aitbc.bubuit.net'}"
        http_client = AITBCHTTPClient(base_url=hub_url, timeout=10)
        response = http_client.get(f"/rpc/accounts/{address}?chain_id={chain_id}")
        return response.get("nonce", 0)
    except Exception as e:
        error(f"Failed to get account nonce: {e}")
        return 0


def get_next_nonce() -> int:
    """Get next transaction nonce from blockchain (confirmed nonce + 1)"""
    wallet_address = get_wallet_address()
    config = get_config()
    hub_url = config.hub_discovery_url or "hub.aitbc.bubuit.net"
    chain_id = "ait-" + hub_url
    return get_account_nonce(wallet_address, chain_id)


@click.group()
def market():
    """Blockchain marketplace commands for GPU trading"""
    pass


# Import submodules to register all commands
from . import escrow, exchange, jobs, offers, ratings
from .escrow import _escrow_create, _get_blockchain_rpc_url
