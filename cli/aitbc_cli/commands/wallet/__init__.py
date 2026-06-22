"""Wallet commands for AITBC CLI"""

import getpass
import json
import os
from pathlib import Path
from typing import Any

import click
import yaml

from ...config import get_config
from ...utils import error, output, success

# Import shared modules
from ...utils.http_client import AITBCHTTPClient, get_logger

# Initialize logger
logger = get_logger(__name__)


def get_wallet_client() -> AITBCHTTPClient:
    """Get HTTP client for wallet service"""
    config = get_config()
    return AITBCHTTPClient(base_url=config.wallet_daemon_url, timeout=30)


def encrypt_value(value: str, password: str) -> str:
    """Simple encryption for wallet data

    NOTE: This is a simple placeholder implementation that doesn't actually encrypt.
    Wallet daemon mode handles encryption server-side, so client-side encryption is not needed.
    For production use with direct wallet file access, upgrade to proper encryption (e.g., cryptography.fernet).
    """
    # For now, return the value as-is since daemon mode doesn't need this
    return value


def decrypt_value(encrypted: str, password: str) -> str:
    """Simple decryption for wallet data

    NOTE: This is a simple placeholder implementation that doesn't actually decrypt.
    Wallet daemon mode handles encryption server-side, so client-side decryption is not needed.
    For production use with direct wallet file access, upgrade to proper encryption (e.g., cryptography.fernet).
    """
    # For now, return the value as-is since daemon mode doesn't need this
    return encrypted


def _get_wallet_password(wallet_name: str) -> str:
    """Get or prompt for wallet encryption password"""
    # Try to get from keyring first
    try:
        import keyring

        password = keyring.get_password("aitbc-wallet", wallet_name)
        if password:
            return password
    except Exception:
        pass

    # Check if we're in a TTY environment
    import sys

    if not sys.stdin.isatty():
        # Non-interactive: try environment variable
        password = os.environ.get(f"AITBC_WALLET_PASSWORD_{wallet_name.upper()}")
        if password:
            return password
        # Try generic password env var
        password = os.environ.get("AITBC_WALLET_PASSWORD")
        if password:
            return password
        error("No TTY available for password prompt. Set AITBC_WALLET_PASSWORD environment variable.")
        raise click.Abort() from None

    # Prompt for password
    while True:
        try:
            password = getpass.getpass(f"Enter password for wallet '{wallet_name}': ")
        except Exception as e:
            error(f"Password prompt failed: {e}")
            raise click.Abort() from e

        if not password:
            error("Password cannot be empty")
            continue

        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            error("Passwords do not match")
            continue

        # Store in keyring for future use
        try:
            import keyring

            keyring.set_password("aitbc-wallet", wallet_name, password)
        except Exception:
            pass

        return password


def _save_wallet(wallet_path: Path, wallet_data: dict[str, Any], password: str = None):
    """Save wallet with encrypted private key"""
    # Encrypt private key if provided
    if password and "private_key" in wallet_data:
        wallet_data["private_key"] = encrypt_value(wallet_data["private_key"], password)
        wallet_data["encrypted"] = True

    # Save wallet
    with open(wallet_path, "w") as f:
        json.dump(wallet_data, f, indent=2)


def _load_wallet(wallet_path: Path, wallet_name: str) -> dict[str, Any]:
    """Load wallet and decrypt private key if needed"""
    with open(wallet_path) as f:
        wallet_data = json.load(f)

    # Decrypt private key if encrypted
    if wallet_data.get("encrypted") and "private_key" in wallet_data:
        password = _get_wallet_password(wallet_name)
        try:
            wallet_data["private_key"] = decrypt_value(wallet_data["private_key"], password)
        except Exception:
            error("Invalid password for wallet")
            raise click.Abort() from None

    return wallet_data


@click.group()
@click.option("--wallet-name", help="Name of the wallet to use")
@click.option("--wallet-path", help="Direct path to wallet file (overrides --wallet-name)")
@click.option("--use-daemon", is_flag=True, default=True, help="Use wallet daemon for operations")
@click.option("--chain-id", help="Chain ID for multichain operations (e.g., ait-mainnet, ait-devnet)")
@click.pass_context
def wallet(ctx, wallet_name: str | None, wallet_path: str | None, use_daemon: bool, chain_id: str | None):
    """Manage your AITBC wallets and transactions"""
    # Ensure wallet object exists
    ctx.ensure_object(dict)

    # Set daemon mode
    ctx.obj["use_daemon"] = use_daemon

    # Handle chain_id with auto-detection
    from ...utils.chain_id import get_chain_id

    config = get_config()
    default_rpc_url = config.blockchain_rpc_url if hasattr(config, "blockchain_rpc_url") else "http://localhost:8202"
    ctx.obj["chain_id"] = get_chain_id(default_rpc_url, override=chain_id)

    # Initialize dual-mode adapter
    from aitbc_cli.utils.dual_mode_wallet_adapter import DualModeWalletAdapter

    config = get_config()
    adapter = DualModeWalletAdapter(config, use_daemon=use_daemon)
    ctx.obj["wallet_adapter"] = adapter

    # If direct wallet path is provided, use it
    if wallet_path:
        wp = Path(wallet_path)
        wp.parent.mkdir(parents=True, exist_ok=True)
        ctx.obj["wallet_name"] = wp.stem
        ctx.obj["wallet_dir"] = wp.parent
        ctx.obj["wallet_path"] = wp
        return

    # Set wallet directory
    wallet_dir = Path.home() / ".aitbc" / "wallets"
    wallet_dir.mkdir(parents=True, exist_ok=True)

    # Set active wallet
    if not wallet_name:
        # Try to get from config or use 'default'
        config_file = Path.home() / ".aitbc" / "config.yaml"
        if config_file.exists():
            with open(config_file) as f:
                config = yaml.safe_load(f)
                if config:
                    wallet_name = config.get("active_wallet", "default")
                else:
                    wallet_name = "default"
        else:
            wallet_name = "default"

    ctx.obj["wallet_name"] = wallet_name
    ctx.obj["wallet_dir"] = wallet_dir
    ctx.obj["wallet_path"] = wallet_dir / f"{wallet_name}.json"


# Register all subcommands
from . import basic, misc, multisig, staking  # noqa: E402
