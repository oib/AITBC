"""Mining commands for AITBC CLI"""

import json
from pathlib import Path
from typing import Any, cast

import click

from ..utils import error, success
from ..utils.http_client import AITBCHTTPClient, NetworkError

DEFAULT_RPC_URL = "http://localhost:8202"
DEFAULT_KEYSTORE_DIRS = [Path.home() / ".aitbc" / "wallets", Path("/var/lib/aitbc/keystore")]


def _find_wallet_path(wallet_name: str) -> Path | None:
    """Find a wallet file by name in the known keystore directories."""
    for directory in DEFAULT_KEYSTORE_DIRS:
        candidate = directory / f"{wallet_name}.json"
        if candidate.exists():
            return candidate
    return None


def _load_wallet_address(wallet_name: str) -> str:
    """Load the address from a named wallet file."""
    keystore_path = _find_wallet_path(wallet_name)
    if not keystore_path:
        raise FileNotFoundError(f"Wallet '{wallet_name}' not found")

    with open(keystore_path) as f:
        wallet_data = json.load(f)
    return cast(str, wallet_data["address"])


def _default_wallet_name() -> str:
    """Return the first wallet name found in the default keystore directories."""
    for directory in DEFAULT_KEYSTORE_DIRS:
        if directory.exists():
            for entry in sorted(directory.glob("*.json")):
                # Skip non-wallet JSON files such as genesis.json
                if entry.name.startswith("."):
                    continue
                try:
                    with open(entry) as f:
                        data = json.load(f)
                    if "address" in data:
                        return entry.stem
                except (json.JSONDecodeError, OSError):
                    continue
    raise FileNotFoundError("No wallet found in keystore")


def _client(rpc_url: str, wallet_address: str | None = None) -> AITBCHTTPClient:
    """Build an HTTP client for the blockchain RPC, optionally with auth header."""
    headers: dict[str, str] = {}
    if wallet_address:
        headers["X-Wallet-Address"] = wallet_address
    return AITBCHTTPClient(base_url=rpc_url, headers=headers, timeout=30)


@click.group()
def mining():
    """Mining operations commands"""
    pass


@mining.command()
@click.argument("wallet_name")
@click.option("--threads", type=int, default=1, help="Number of mining threads")
@click.option("--rpc-url", help="Blockchain RPC URL")
def start(wallet_name: str, threads: int, rpc_url: str | None):
    """Start mining with specified wallet"""
    if not rpc_url:
        rpc_url = DEFAULT_RPC_URL

    try:
        address = _load_wallet_address(wallet_name)
    except FileNotFoundError as e:
        error(str(e))
        return

    mining_config: dict[str, Any] = {"miner_address": address, "threads": threads, "enabled": True}

    try:
        http_client = _client(rpc_url, address)
        result = http_client.post("/rpc/mining/start", json=mining_config)
        success(f"Mining started with wallet '{wallet_name}'")
        click.echo(f"Miner address: {address}")
        click.echo(f"Threads: {threads}")
        click.echo(f"Status: {result.get('status', 'started')}")
    except NetworkError as e:
        if "404" in str(e):
            error("Mining RPC endpoint not found. Check blockchain-node RPC configuration.")
        elif "401" in str(e):
            error("Authentication failed. Ensure TRUST_X_WALLET_ADDRESS=true on the blockchain RPC.")
        else:
            error(f"Error starting mining: {e}")
    except Exception as e:
        error(f"Error: {e}")


@mining.command()
@click.option("--wallet", "wallet_name", help="Wallet to use for X-Wallet-Address auth")
@click.option("--rpc-url", help="Blockchain RPC URL")
def stop(wallet_name: str | None, rpc_url: str | None):
    """Stop mining"""
    if not rpc_url:
        rpc_url = DEFAULT_RPC_URL

    try:
        wallet = wallet_name or _default_wallet_name()
        address = _load_wallet_address(wallet)
    except FileNotFoundError as e:
        error(str(e))
        return

    try:
        http_client = _client(rpc_url, address)
        result = http_client.post("/rpc/mining/stop")
        success("Mining stopped")
        click.echo(f"Status: {result.get('status', 'stopped')}")
    except NetworkError as e:
        if "401" in str(e):
            error("Authentication failed. Ensure TRUST_X_WALLET_ADDRESS=true on the blockchain RPC.")
        else:
            error(f"Error stopping mining: {e}")
    except Exception as e:
        error(f"Error: {e}")


@mining.command()
@click.option("--wallet", "wallet_name", help="Wallet to use for X-Wallet-Address auth")
@click.option("--rpc-url", help="Blockchain RPC URL")
def status(wallet_name: str | None, rpc_url: str | None):
    """Get mining status"""
    if not rpc_url:
        rpc_url = DEFAULT_RPC_URL

    try:
        wallet = wallet_name or _default_wallet_name()
        address = _load_wallet_address(wallet)
    except FileNotFoundError as e:
        error(str(e))
        return

    try:
        http_client = _client(rpc_url, address)
        result = http_client.get("/rpc/mining/status")
        success("Mining status:")
        click.echo(json.dumps(result, indent=2))
    except NetworkError as e:
        if "401" in str(e):
            error("Authentication failed. Ensure TRUST_X_WALLET_ADDRESS=true on the blockchain RPC.")
        else:
            error(f"Error getting mining status: {e}")
    except Exception as e:
        error(f"Error: {e}")


@mining.command(name="list")
@click.option("--wallet", "wallet_name", help="Wallet to use for X-Wallet-Address auth")
@click.option("--rpc-url", help="Blockchain RPC URL")
def list_miners(wallet_name: str | None, rpc_url: str | None):
    """List active miners"""
    if not rpc_url:
        rpc_url = DEFAULT_RPC_URL

    try:
        wallet = wallet_name or _default_wallet_name()
        address = _load_wallet_address(wallet)
    except FileNotFoundError as e:
        error(str(e))
        return

    try:
        http_client = _client(rpc_url, address)
        result = http_client.get("/rpc/mining/miners")
        success("Active miners:")
        click.echo(json.dumps(result, indent=2))
    except NetworkError as e:
        if "401" in str(e):
            error("Authentication failed. Ensure TRUST_X_WALLET_ADDRESS=true on the blockchain RPC.")
        else:
            error(f"Error listing miners: {e}")
    except Exception as e:
        error(f"Error: {e}")
