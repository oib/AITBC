"""
Island Credential Loading Utility
Provides functions to load and validate island credentials from the local filesystem
"""

import json
import os
from pathlib import Path
from typing import Any

from .http_client import get_logger

logger = get_logger(__name__)

CREDENTIALS_PATH = "/var/lib/aitbc/island_credentials.json"


def load_island_credentials() -> dict[str, Any]:
    """
    Load island credentials from the local filesystem

    Returns:
        dict: Island credentials containing island_id, island_name, chain_id, credentials, etc.

    Raises:
        FileNotFoundError: If credentials file does not exist
        PermissionError: If credentials file is not owned by the user or is too permissive
        json.JSONDecodeError: If credentials file is invalid JSON
        ValueError: If credentials are invalid or missing required fields
    """
    credentials_path = Path(CREDENTIALS_PATH)

    if not credentials_path.exists():
        raise FileNotFoundError(
            f"Island credentials not found at {CREDENTIALS_PATH}. Run 'aitbc node island join' to join an island first."
        )

    file_stat = credentials_path.stat()
    if file_stat.st_mode & 0o777 > 0o600:
        raise PermissionError(f"Island credentials file {CREDENTIALS_PATH} has overly permissive mode; set it to 0o600")
    # Root (euid 0) is the operator login on shop nodes; the credentials file is
    # owned by the `aitbc` service user at mode 0600. Refusing that pair made
    # `aitbc market offer` unusable both as root and as aitbc (the latter then
    # dies on root-owned /etc/aitbc/blockchain-secrets.env).
    if file_stat.st_uid != os.geteuid() and os.geteuid() != 0:
        raise PermissionError(f"Island credentials file {CREDENTIALS_PATH} must be owned by the current user")

    with open(credentials_path) as f:
        credentials: dict[str, Any] = json.load(f)

    # Validate required fields
    required_fields = ["island_id", "island_name", "island_chain_id", "credentials"]
    for field in required_fields:
        if field not in credentials:
            raise ValueError(f"Invalid credentials: missing required field '{field}'")

    return credentials


def get_rpc_endpoint() -> str:
    """
    Get the RPC endpoint from island credentials.

    Falls back to the hub blockchain RPC base (/rpc) when the island
    credentials file does not yet contain an explicit RPC endpoint.
    """
    credentials = load_island_credentials()
    rpc_endpoint = credentials.get("credentials", {}).get("rpc_endpoint")

    if not rpc_endpoint:
        from ..config import get_config

        fallback = getattr(get_config(), "blockchain_rpc_url", "")
        if not fallback:
            raise ValueError("RPC endpoint not found in island credentials")
        fallback = fallback.rstrip("/")
        if not fallback.endswith("/rpc"):
            fallback = fallback + "/rpc"
        return fallback

    return rpc_endpoint  # type: ignore[no-any-return]


def get_chain_id() -> str:
    """
    Get the chain ID from island credentials

    Returns:
        str: Chain ID

    Raises:
        FileNotFoundError: If credentials file does not exist
        ValueError: If chain ID is missing from credentials
    """
    credentials = load_island_credentials()
    chain_id = credentials.get("island_chain_id")

    if not chain_id:
        raise ValueError("Chain ID not found in island credentials")

    return chain_id  # type: ignore[no-any-return]


def get_island_id() -> str:
    """
    Get the island ID from island credentials

    Returns:
        str: Island ID

    Raises:
        FileNotFoundError: If credentials file does not exist
        ValueError: If island ID is missing from credentials
    """
    credentials = load_island_credentials()
    island_id = credentials.get("island_id")

    if not island_id:
        raise ValueError("Island ID not found in island credentials")

    return island_id  # type: ignore[no-any-return]


def get_island_name() -> str:
    """
    Get the island name from island credentials

    Returns:
        str: Island name

    Raises:
        FileNotFoundError: If credentials file does not exist
        ValueError: If island name is missing from credentials
    """
    credentials = load_island_credentials()
    island_name = credentials.get("island_name")

    if not island_name:
        raise ValueError("Island name not found in island credentials")

    return island_name  # type: ignore[no-any-return]


def get_genesis_block_hash() -> str | None:
    """
    Get the genesis block hash from island credentials

    Returns:
        str: Genesis block hash, or None if not available
    """
    try:
        credentials = load_island_credentials()
        return credentials.get("credentials", {}).get("genesis_block_hash")  # type: ignore[no-any-return]
    except (FileNotFoundError, ValueError):
        logger.debug("Island credentials missing for genesis block hash", exc_info=True)
        return None


def get_genesis_address() -> str | None:
    """
    Get the genesis address from island credentials

    Returns:
        str: Genesis address, or None if not available
    """
    try:
        credentials = load_island_credentials()
        return credentials.get("credentials", {}).get("genesis_address")  # type: ignore[no-any-return]
    except (FileNotFoundError, ValueError):
        logger.debug("Island credentials missing for genesis address", exc_info=True)
        return None


def validate_credentials() -> bool:
    """
    Validate that island credentials exist and are valid

    Returns:
        bool: True if credentials are valid, False otherwise
    """
    try:
        credentials = load_island_credentials()
        # Check for essential fields
        return all(key in credentials for key in ["island_id", "island_name", "island_chain_id", "credentials"])
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        logger.debug("Island credentials invalid or missing", exc_info=True)
        return False


def get_p2p_port() -> int | None:
    """
    Get the P2P port from island credentials

    Returns:
        int: P2P port, or None if not available
    """
    try:
        credentials = load_island_credentials()
        return credentials.get("credentials", {}).get("p2p_port")  # type: ignore[no-any-return]
    except (FileNotFoundError, ValueError):
        logger.debug("Island credentials missing for p2p_port", exc_info=True)
        return None
