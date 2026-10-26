"""
Market commands for GPU/software offers published by shop miners.
"""

import hashlib
import json
import os
import re
import socket
from datetime import datetime
from typing import Any, cast

import click

from aitbc.config.hub import normalize_hub_base

from ...config import get_config
from ...utils.wallet_secret import wallet_password_options
from ...utils import error, info, output, success, warning
from ...utils.address import to_canonical
from ...utils.error_handling import abort
from ...utils.http_client import AITBCHTTPClient, NetworkError, get_logger
from ...utils.island_credentials import CREDENTIALS_PATH, load_island_credentials
from ...utils.wallet_loader import find_wallet_by_address, load_wallet_for_payment
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
            chain_id = os.getenv("CHAIN_ID")
            if not chain_id:
                error(
                    "Cannot determine the chain id to sign with: this hub has no "
                    "island credentials and CHAIN_ID is not set — set CHAIN_ID"
                )
                raise click.Abort() from e
            return {
                "credentials": {"p2p_port": 8200},
                "island_id": os.getenv("ISLAND_ID", "ait-hub"),
                "chain_id": chain_id,
            }
        abort(
            None,
            f"Island credentials required for market operations: {e}\n"
            "Note: Hub nodes do not need to join islands - market works with blockchain config.\n"
            "For follower nodes, run: aitbc node island join <island_id> <island_name> <chain_id>\n"
            "Example: aitbc edge island join my-island 'AIT Hub' my-chain-id",
        )
        return None


def get_chain_id() -> str:
    """Get chain ID from CHAIN_ID, island credentials, or the configured node RPC.

    Signing callers must never sign a fabricated chain id — a wrong value
    produces a transaction no node serves. When no honest source answers,
    abort instead of guessing one from the hub's hostname.

    CHAIN_ID wins: it is the deployment truth the node's own units run.
    Credentials are a join-time cache that can go stale (a chain rebirth
    leaves the old id behind); when the file and the env disagree the env
    wins and the mismatch is warned about, never silent. A credentials file
    that exists but cannot be loaded (permission guard, bad JSON) must not
    shadow a usable CHAIN_ID either.
    """
    creds_chain_id: str | None = None
    try:
        creds = load_island_credentials()
        # Credentials use 'island_chain_id' key
        raw = creds.get("island_chain_id") or creds.get("chain_id")
        creds_chain_id = str(raw) if raw else None
    except (FileNotFoundError, ValueError):
        logger.debug("Island credentials not available for chain_id", exc_info=True)
    except PermissionError:
        logger.warning(
            "island credentials at %s are present but unreadable (mode/owner guard) — falling through to CHAIN_ID",
            CREDENTIALS_PATH,
        )

    env_chain_id = os.getenv("CHAIN_ID")
    if env_chain_id:
        if creds_chain_id and creds_chain_id != env_chain_id:
            warning(
                f"chain id mismatch: island credentials at {CREDENTIALS_PATH} say "
                f"'{creds_chain_id}' but CHAIN_ID='{env_chain_id}' — signing for "
                f"'{env_chain_id}'. Refresh credentials: aitbc node island join"
            )
        return env_chain_id
    if creds_chain_id:
        return creds_chain_id

    config = get_config()
    rpc_url = config.blockchain_rpc_url or "http://localhost:8202"
    try:
        from ...utils.chain_id import get_chain_id as _probe_chain_id

        return _probe_chain_id(rpc_url, override=None, timeout=5, strict=True)
    except Exception as e:
        error(
            f"Cannot determine the chain id to sign with: no island credentials, CHAIN_ID unset, "
            f"and the chain-id lookup via {rpc_url} failed: {e}. "
            "Set CHAIN_ID or point blockchain_rpc_url at a serving node"
        )
        raise click.Abort() from e


def get_island_id() -> str:
    """Get island ID — env ISLAND_ID first, then island credentials.

    Env stays authoritative (same rule as get_chain_id); a credentials file
    carrying a different island id produces a warning, not silence.
    """
    env_island = os.getenv("ISLAND_ID")
    creds_island: str | None = None
    try:
        raw = load_island_credentials().get("island_id")
        creds_island = str(raw) if raw else None
    except FileNotFoundError:
        pass
    if env_island:
        if creds_island and creds_island != env_island:
            warning(
                f"island id mismatch: island credentials at {CREDENTIALS_PATH} say "
                f"'{creds_island}' but ISLAND_ID='{env_island}' — using ISLAND_ID"
            )
        return env_island
    if creds_island:
        return creds_island
    # Hub / shop / follower nodes all publish to the hub island by default.
    return os.getenv("ISLAND_ID", "ait-hub")


def _wallet_address(wallet: dict[str, Any]) -> str | None:
    metadata = wallet.get("metadata", {})
    return cast(str | None, metadata.get("address") or metadata.get("original_address"))


def _account_balance(address: str, chain_id: str) -> int:
    """Query the hub for the canonical account balance of an address."""
    try:
        config = get_config()
        hub = config.hub_discovery_url or "hub.aitbc.invalid"
        client = AITBCHTTPClient(base_url=normalize_hub_base(hub) or hub, timeout=5)
        data = client.get(f"/rpc/accounts/{address}", params={"chain_id": chain_id})
        return int(data.get("balance", 0))
    except Exception as e:
        logger.debug("Could not get balance for %s: %s", address, e)
        return 0


def get_wallet_address() -> str:
    """Get a funded provider address from the wallet service.

    P2.5: market offers require a sender with enough balance to pay the
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
        http_client = AITBCHTTPClient(base_url="http://localhost:8108", timeout=5, api_key=get_config().wallet_api_key)
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
    hub = config.hub_discovery_url or "hub.aitbc.invalid"
    # Prefer the local blockchain RPC; the hub discovery URL may not expose /rpc.
    for base_url in (rpc_url, normalize_hub_base(hub) or hub):
        try:
            http_client = AITBCHTTPClient(base_url=base_url, timeout=10)
            response = http_client.get(f"/rpc/accounts/{address}?chain_id={chain_id}")
            nonce = response.get("nonce")
            if nonce is None:
                raise ValueError(f"/rpc/accounts/{address} response carried no nonce")
            return int(nonce)
        except Exception as e:
            logger.debug("Failed to get nonce from %s: %s", base_url, e)
            continue
    error(
        f"Failed to get account nonce for {address} via {rpc_url} or the hub RPC — "
        "a failed lookup must not mean nonce 0; point --rpc-url at a serving node"
    )
    raise click.Abort()


def get_next_nonce(wallet_address: str | None = None) -> int:
    """Get next transaction nonce from blockchain (confirmed nonce + 1)."""
    if not wallet_address:
        wallet_address = get_wallet_address()
    get_config()
    chain_id = get_chain_id()
    return get_account_nonce(wallet_address, chain_id)


def get_market_wallet(ctx, require_private_key: bool = False) -> tuple[str, str | None, str]:
    """Resolve the wallet used by market commands.

    Priority: group-level --wallet / --wallet-path, then the
    ``SHOP_WALLET_ADDRESS`` / ``AITBC_MARKET_WALLET`` environment, then
    configuration.  ``SHOP_WALLET_ADDRESS`` names a provider account rather
    than a wallet file, so a local file wallet holding that address is
    resolved and loaded for signing when one exists — listing paths must be
    able to sign.  Returns ``(address, private_key_or_none, wallet_name)``.
    """
    wallet_name = ctx.obj.get("market_wallet")
    wallet_path = ctx.obj.get("market_wallet_path")
    password = ctx.obj.get("market_password")
    password_file = ctx.obj.get("market_password_file")
    password_stdin = ctx.obj.get("market_password_stdin", False)

    # If no wallet was specified on the command line, fall back to the shop
    # environment.  This keeps backwards compatibility for unattended offers
    # while still allowing a human buyer to pass --wallet for paid jobs.
    if not wallet_name and not wallet_path:
        shop_address = os.environ.get("SHOP_WALLET_ADDRESS")
        if shop_address:
            shop_wallet = find_wallet_by_address(shop_address)
            if require_private_key:
                # A signing caller must sign *as* the shop address — silently
                # falling back to another wallet would attribute the
                # transaction to the wrong sender.
                if shop_wallet is None:
                    abort(
                        ctx,
                        f"SHOP_WALLET_ADDRESS {shop_address} matches no wallet file "
                        "(searched AITBC_WALLET_DIR, ~/.aitbc/wallets, "
                        "/var/lib/aitbc/wallets); pass --wallet or --wallet-path",
                    )
                return load_wallet_for_payment(
                    ctx,
                    wallet_path=str(shop_wallet),
                    password=password,
                    password_file=password_file,
                    password_stdin=password_stdin,
                )
            if shop_wallet is not None:
                try:
                    return load_wallet_for_payment(
                        ctx,
                        wallet_path=str(shop_wallet),
                        password=password,
                        password_file=password_file,
                        password_stdin=password_stdin,
                    )
                except Exception:
                    # An explicit --password that failed is a real operator
                    # error and must surface; anything else (encrypted and no
                    # password env, daemon-style file) degrades to address-only
                    # as before so display paths keep working.
                    if password:
                        raise
                    logger.warning(
                        "SHOP_WALLET_ADDRESS %s matched %s but it could not be loaded for signing",
                        shop_address,
                        shop_wallet,
                        exc_info=True,
                    )
            return shop_address, None, "shop"

    return load_wallet_for_payment(
        ctx,
        wallet_name=wallet_name,
        wallet_path=wallet_path,
        password=password,
        password_file=password_file,
        password_stdin=password_stdin,
        require_private_key=require_private_key,
    )


from ._group import market

# Import submodules to register all commands
from . import escrow, exchange, jobs, offers, payments, ratings
from .escrow import _escrow_create, _get_blockchain_rpc_url
from . import gpu as gpu_module
from .host import (
    cancel as market_cancel_cmd,
    download as market_download_cmd,
    host as market_host_cmd,
    jobs as market_jobs_cmd,
)

market.add_command(escrow.escrow)
market.add_command(gpu_module.gpu)
market.add_command(market_host_cmd)
market.add_command(market_download_cmd)
market.add_command(market_cancel_cmd)
market.add_command(market_jobs_cmd)
