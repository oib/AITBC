"""Chain ID utilities for AITBC CLI

This module provides functions for auto-detecting and validating chain IDs
from blockchain nodes, supporting multichain operations.
"""

from typing import Optional
from aitbc import AITBCHTTPClient, NetworkError


# Known chain IDs
KNOWN_CHAINS = ["ait-mainnet", "ait-devnet", "ait-testnet", "ait-healthchain"]


def get_default_chain_id() -> str:
    """Return the default chain ID (ait-mainnet for production)."""
    return "ait-mainnet"


def validate_chain_id(chain_id: str) -> bool:
    """Validate a chain ID against known chains.
    
    Args:
        chain_id: The chain ID to validate
        
    Returns:
        True if the chain ID is known, False otherwise
    """
    return chain_id in KNOWN_CHAINS


def get_chain_id_from_health(rpc_url: str, timeout: int = 5) -> str:
    """Auto-detect chain ID from blockchain node's /health endpoint.
    
    Args:
        rpc_url: The blockchain node RPC URL (e.g., http://localhost:8006)
        timeout: Request timeout in seconds
        
    Returns:
        The detected chain ID, or default if detection fails
    """
    try:
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=timeout)
        health_data = http_client.get("/health")
        supported_chains = health_data.get("supported_chains", [])
        
        if supported_chains:
            # Return the first supported chain (typically the primary chain)
            return supported_chains[0]
    except NetworkError:
        pass
    except Exception:
        pass
    
    # Fallback to default if detection fails
    return get_default_chain_id()


def get_chain_id(rpc_url: str, override: Optional[str] = None, timeout: int = 5) -> str:
    """Get chain ID with override support and auto-detection fallback.
    
    Args:
        rpc_url: The blockchain node RPC URL
        override: Optional chain ID override (e.g., from --chain-id flag)
        timeout: Request timeout in seconds
        
    Returns:
        The chain ID to use (override takes precedence, then auto-detection, then default)
    """
    # If override is provided, validate and use it
    if override:
        if validate_chain_id(override):
            return override
        # If unknown, still use it (user may be testing new chains)
        return override
    
    # Otherwise, auto-detect from health endpoint
    return get_chain_id_from_health(rpc_url, timeout)
