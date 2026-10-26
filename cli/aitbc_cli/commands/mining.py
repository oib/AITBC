"""Mining commands for AITBC CLI"""

import json
from pathlib import Path
from typing import Any, cast

import click

from ..utils import success
from ..utils.error_handling import abort, is_unauthorized
from ..utils.http_client import KEYSTORE_DIR, AITBCHTTPClient, NetworkError
from ..utils.wallet_paths import wallet_search_dirs

DEFAULT_RPC_URL = "http://localhost:8202"


def _keystore_dirs() -> list[Path]:
    # Shared wallet search order (configured dir, then service wallet dir),
    # plus the legacy daemon keystore which only this command still reads.
    return [*wallet_search_dirs(), Path(KEYSTORE_DIR)]


def _find_wallet_path(wallet_name: str) -> Path | None:
    """Find a wallet file by name in the known keystore directories."""
    for directory in _keystore_dirs():
        candidate = directory / f"{wallet_name}.json"
        if candidate.exists():
            return candidate
    return None


def _load_wallet_address(wallet_name: str) -> str:
    """Load the address from a named wallet file."""
    keystore_path = _find_wallet_path(wallet_name)
    if not keystore_path:
        searched = ", ".join(str(d) for d in _keystore_dirs())
        raise FileNotFoundError(f"Wallet '{wallet_name}' not found (searched: {searched})")

    with open(keystore_path) as f:
        wallet_data = json.load(f)
    return cast(str, wallet_data["address"])


def _default_wallet_name() -> str:
    """Return the first wallet name found in the default keystore directories."""
    for directory in _keystore_dirs():
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


@click.group(
    epilog="""Examples:

  aitbc mining start --wallet-name wallet-1

  aitbc mining status --wallet wallet-1"""
)
def mining():
    """Start, stop, and monitor mining operations using a wallet."""
    pass


@mining.command(
    epilog="""Examples:

  aitbc mining start --wallet-name wallet-1

  aitbc mining start --wallet-name wallet-1 --threads 4"""
)
@click.option("--wallet-name", "wallet_name", required=True, help="The Wallet name.")
@click.option("--threads", type=int, default=1, help="Number of mining threads")
@click.option("--rpc-url", help="Blockchain RPC URL")
@click.pass_context
def start(ctx: click.Context, wallet_name: str, threads: int, rpc_url: str | None):
    """Start mining with a specified wallet and optional thread count."""
    if not rpc_url:
        rpc_url = DEFAULT_RPC_URL

    try:
        address = _load_wallet_address(wallet_name)
    except FileNotFoundError as e:
        abort(ctx, str(e), from_exception=e)

    mining_config: dict[str, Any] = {"miner_address": address, "threads": threads, "enabled": True}

    try:
        http_client = _client(rpc_url, address)
        result = http_client.post("/rpc/mining/start", json=mining_config)
        success(f"Mining started with wallet '{wallet_name}'")
        click.echo(f"Miner address: {address}")
        click.echo(f"Threads: {threads}")
        click.echo(f"Status: {result.get('status', 'started')}")
    except NetworkError as e:
        if is_unauthorized(e):
            abort(
                ctx,
                "Authentication failed. Ensure TRUST_X_WALLET_ADDRESS=true on the blockchain RPC.",
                from_exception=e,
            )
        elif "404" in str(e):
            abort(ctx, "Mining RPC endpoint not found. Check blockchain-node RPC configuration.", from_exception=e)
        else:
            abort(ctx, f"Error starting mining: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error: {e}", from_exception=e)


@mining.command(
    epilog="""Examples:

  aitbc mining stop

  aitbc mining stop --wallet wallet-1"""
)
@click.option("--wallet", "wallet_name", help="Wallet to use for X-Wallet-Address auth")
@click.option("--rpc-url", help="Blockchain RPC URL")
@click.pass_context
def stop(ctx: click.Context, wallet_name: str | None, rpc_url: str | None):
    """Stop mining operations for a wallet."""
    if not rpc_url:
        rpc_url = DEFAULT_RPC_URL

    try:
        wallet = wallet_name or _default_wallet_name()
        address = _load_wallet_address(wallet)
    except FileNotFoundError as e:
        abort(ctx, str(e), from_exception=e)

    try:
        http_client = _client(rpc_url, address)
        result = http_client.post("/rpc/mining/stop")
        success("Mining stopped")
        click.echo(f"Status: {result.get('status', 'stopped')}")
    except NetworkError as e:
        if is_unauthorized(e):
            abort(
                ctx,
                "Authentication failed. Ensure TRUST_X_WALLET_ADDRESS=true on the blockchain RPC.",
                from_exception=e,
            )
        else:
            abort(ctx, f"Error stopping mining: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error: {e}", from_exception=e)


@mining.command(
    epilog="""Examples:

  aitbc mining status

  aitbc mining status --wallet wallet-1"""
)
@click.option("--wallet", "wallet_name", help="Wallet to use for X-Wallet-Address auth")
@click.option("--rpc-url", help="Blockchain RPC URL")
@click.pass_context
def status(ctx: click.Context, wallet_name: str | None, rpc_url: str | None):
    """Get the current mining status for a wallet."""
    if not rpc_url:
        rpc_url = DEFAULT_RPC_URL

    try:
        wallet = wallet_name or _default_wallet_name()
        address = _load_wallet_address(wallet)
    except FileNotFoundError as e:
        abort(ctx, str(e), from_exception=e)

    try:
        http_client = _client(rpc_url, address)
        result = http_client.get("/rpc/mining/status")
        success("Mining status:")
        click.echo(json.dumps(result, indent=2))
    except NetworkError as e:
        if is_unauthorized(e):
            abort(
                ctx,
                "Authentication failed. Ensure TRUST_X_WALLET_ADDRESS=true on the blockchain RPC.",
                from_exception=e,
            )
        else:
            abort(ctx, f"Error getting mining status: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error: {e}", from_exception=e)


@mining.command(
    name="list",
    epilog="""Examples:

  aitbc mining list

  aitbc mining list --wallet wallet-1""",
)
@click.option("--wallet", "wallet_name", help="Wallet to use for X-Wallet-Address auth")
@click.option("--rpc-url", help="Blockchain RPC URL")
@click.pass_context
def list_miners(ctx: click.Context, wallet_name: str | None, rpc_url: str | None):
    """List active miners for a wallet."""
    if not rpc_url:
        rpc_url = DEFAULT_RPC_URL

    try:
        wallet = wallet_name or _default_wallet_name()
        address = _load_wallet_address(wallet)
    except FileNotFoundError as e:
        abort(ctx, str(e), from_exception=e)

    try:
        http_client = _client(rpc_url, address)
        result = http_client.get("/rpc/mining/miners")
        success("Active miners:")
        click.echo(json.dumps(result, indent=2))
    except NetworkError as e:
        if is_unauthorized(e):
            abort(
                ctx,
                "Authentication failed. Ensure TRUST_X_WALLET_ADDRESS=true on the blockchain RPC.",
                from_exception=e,
            )
        else:
            abort(ctx, f"Error listing miners: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error: {e}", from_exception=e)
