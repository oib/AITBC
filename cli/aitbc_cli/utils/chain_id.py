"""Chain ID utilities for AITBC CLI

This module provides functions for auto-detecting and validating chain IDs
from blockchain nodes, supporting multichain operations.
"""

from .http_client import AITBCHTTPClient, NetworkError, get_logger

logger = get_logger(__name__)


def get_default_chain_id() -> str:
    """Return the default chain ID from environment."""
    import os

    # Get from environment variable (set in /etc/aitbc/blockchain.env)
    chain_id = os.getenv("CHAIN_ID")
    if chain_id:
        return chain_id

    # No default available - empty string
    return ""


def validate_chain_id(chain_id: str) -> bool:
    """Validate a chain ID format (basic validation, not against hardcoded list).

    Args:
        chain_id: The chain ID to validate

    Returns:
        True if the chain ID format is valid, False otherwise
    """
    # Basic format validation - chain IDs should be non-empty strings
    # Actual chain validity is determined by the blockchain node
    return bool(chain_id and isinstance(chain_id, str) and len(chain_id) > 0)


def get_chain_id_from_health(rpc_url: str, timeout: int = 5) -> str:
    """Auto-detect chain ID from the blockchain node.

    Public hubs proxy the root ``/health`` endpoint to the agent-coordinator,
    so the blockchain RPC ``/proposer`` endpoint is tried first. It reliably
    returns ``chain_id`` and ``supported_chains`` on every blockchain node.

    Args:
        rpc_url: The blockchain node RPC URL (e.g., http://localhost:8202)
        timeout: Request timeout in seconds

    Returns:
        The detected chain ID, or default if detection fails
    """
    try:
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=timeout, max_retries=0)
    except NetworkError:
        logger.debug("Network error creating chain ID client for %s", rpc_url, exc_info=True)
    except Exception:
        logger.debug("Chain ID client creation for %s failed", rpc_url, exc_info=True)
    else:
        # Try the blockchain RPC /proposer endpoint first: it works behind the
        # public reverse proxy and returns both chain_id and supported_chains.
        for endpoint in ("/rpc/proposer", "/health"):
            try:
                data = http_client.get(endpoint)
                supported_chains = data.get("supported_chains") or []
                if supported_chains:
                    first_chain = supported_chains[0] if isinstance(supported_chains, list) else str(supported_chains)
                    return str(first_chain)
                chain_id = data.get("chain_id")
                if chain_id:
                    return str(chain_id)
            except NetworkError:
                logger.debug("Network error detecting chain ID from %s", endpoint, exc_info=True)
            except Exception:
                logger.debug("Chain ID detection from %s failed", endpoint, exc_info=True)

    # Fallback to environment variable if detection fails
    import os

    chain_id = os.getenv("CHAIN_ID")
    if chain_id:
        return chain_id

    # Final fallback - empty string to indicate no chain detected
    return ""


def get_chain_id(rpc_url: str, override: str | None = None, timeout: int = 5) -> str:
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
