"""
Island Credential Loading Utility
Provides functions to load and validate island credentials from the local filesystem
"""

import json
import os
from typing import Dict, Optional
from pathlib import Path


CREDENTIALS_PATH = '/var/lib/aitbc/island_credentials.json'


def load_island_credentials() -> Dict:
    """
    Load island credentials from the local filesystem

    Returns:
        dict: Island credentials containing island_id, island_name, chain_id, credentials, etc.

    Raises:
        FileNotFoundError: If credentials file does not exist
        json.JSONDecodeError: If credentials file is invalid JSON
        ValueError: If credentials are invalid or missing required fields
    """
    credentials_path = Path(CREDENTIALS_PATH)

    if not credentials_path.exists():
        raise FileNotFoundError(
            f"Island credentials not found at {CREDENTIALS_PATH}. "
            f"Run 'aitbc node island join' to join an island first."
        )

    with open(credentials_path, 'r') as f:
        credentials = json.load(f)

    # Validate required fields
    required_fields = ['island_id', 'island_name', 'island_chain_id', 'credentials']
    for field in required_fields:
        if field not in credentials:
            raise ValueError(f"Invalid credentials: missing required field '{field}'")

    return credentials


def get_rpc_endpoint() -> str:
    """
    Get the RPC endpoint from island credentials

    Returns:
        str: RPC endpoint URL

    Raises:
        FileNotFoundError: If credentials file does not exist
        ValueError: If RPC endpoint is missing from credentials
    """
    credentials = load_island_credentials()
    rpc_endpoint = credentials.get('credentials', {}).get('rpc_endpoint')

    if not rpc_endpoint:
        raise ValueError("RPC endpoint not found in island credentials")

    return rpc_endpoint


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
    chain_id = credentials.get('island_chain_id')

    if not chain_id:
        raise ValueError("Chain ID not found in island credentials")

    return chain_id


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
    island_id = credentials.get('island_id')

    if not island_id:
        raise ValueError("Island ID not found in island credentials")

    return island_id


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
    island_name = credentials.get('island_name')

    if not island_name:
        raise ValueError("Island name not found in island credentials")

    return island_name


def get_genesis_block_hash() -> Optional[str]:
    """
    Get the genesis block hash from island credentials

    Returns:
        str: Genesis block hash, or None if not available
    """
    try:
        credentials = load_island_credentials()
        return credentials.get('credentials', {}).get('genesis_block_hash')
    except (FileNotFoundError, ValueError):
        return None


def get_genesis_address() -> Optional[str]:
    """
    Get the genesis address from island credentials

    Returns:
        str: Genesis address, or None if not available
    """
    try:
        credentials = load_island_credentials()
        return credentials.get('credentials', {}).get('genesis_address')
    except (FileNotFoundError, ValueError):
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
        return all(key in credentials for key in ['island_id', 'island_name', 'island_chain_id', 'credentials'])
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        return False


def get_p2p_port() -> Optional[int]:
    """
    Get the P2P port from island credentials

    Returns:
        int: P2P port, or None if not available
    """
    try:
        credentials = load_island_credentials()
        return credentials.get('credentials', {}).get('p2p_port')
    except (FileNotFoundError, ValueError):
        return None
