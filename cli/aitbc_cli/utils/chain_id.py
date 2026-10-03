"""Chain ID utilities for AITBC CLI

This module provides functions for auto-detecting and validating chain IDs
from blockchain nodes, supporting multichain operations.
"""

from .http_client import AITBCHTTPClient, NetworkError, get_logger

logger = get_logger(__name__)


class ChainIdLookupError(RuntimeError):
    """A node could not be probed for the chain id it advertises."""


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


def get_chain_id_from_health(rpc_url: str, timeout: int = 5, *, strict: bool = False) -> str:
    """Auto-detect chain ID from the blockchain node.

    Public hubs proxy the root ``/health`` endpoint to the agent-coordinator,
    so the blockchain RPC ``/proposer`` endpoint is tried first. It reliably
    returns ``chain_id`` and ``supported_chains`` on every blockchain node.

    Args:
        rpc_url: The blockchain node RPC URL (e.g., http://localhost:8202)
        timeout: Request timeout in seconds
        strict: Raise :class:`ChainIdLookupError` naming the underlying
            failures instead of falling back to the environment default.
            Signing paths use this — a silently defaulted chain id produces
            a transaction no node serves.

    Returns:
        The detected chain ID, or default if detection fails
    """
    errors: list[str] = []
    try:
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=timeout, max_retries=0)
    except NetworkError as e:
        errors.append(str(e))
        logger.debug("Network error creating chain ID client for %s", rpc_url, exc_info=True)
    except Exception as e:
        errors.append(str(e))
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
                errors.append(f"{endpoint}: response carried no chain_id")
            except NetworkError as e:
                errors.append(f"{endpoint}: {e}")
                logger.debug("Network error detecting chain ID from %s", endpoint, exc_info=True)
            except Exception as e:
                errors.append(f"{endpoint}: {e}")
                logger.debug("Chain ID detection from %s failed", endpoint, exc_info=True)

    if strict:
        detail = "; ".join(errors) or "no chain_id advertised"
        raise ChainIdLookupError(f"{rpc_url}: {detail}")

    # Fallback to environment variable if detection fails
    import os

    chain_id = os.getenv("CHAIN_ID")
    if chain_id:
        return chain_id

    # Final fallback - empty string to indicate no chain detected
    return ""


def get_chain_id(rpc_url: str, override: str | None = None, timeout: int = 5, *, strict: bool = False) -> str:
    """Get chain ID with override support and auto-detection fallback.

    Args:
        rpc_url: The blockchain node RPC URL
        override: Optional chain ID override (e.g., from --chain-id flag)
        timeout: Request timeout in seconds
        strict: Raise :class:`ChainIdLookupError` when auto-detection fails
            instead of falling back to the environment default or "".

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
    return get_chain_id_from_health(rpc_url, timeout, strict=strict)


def resolve_chain_id(ctx, rpc_url: str, *, required: bool = True) -> str:
    """Resolve the chain id for the node this command actually talks to.

    An explicit ``--chain-id`` or ``CHAIN_ID`` wins; otherwise ``rpc_url`` is
    probed — never ``ctx.obj["chain_id"]``, which may have been resolved
    against a different URL than the one this call submits to.

    ``required=True`` (signing paths) probes strictly and aborts on failure:
    a silent default signs a transaction no node serves. ``required=False``
    (read paths) returns ``""`` on failure so the caller omits the parameter
    and the node's own ``chain_id=None`` default applies its chain — strictly
    more accurate than a client-side guess, and nothing is signed.
    """
    import os

    from .error_handling import abort

    explicit = (getattr(ctx, "obj", None) or {}).get("chain_id_explicit") or os.getenv("CHAIN_ID")
    if explicit:
        return explicit

    if not required:
        return get_chain_id(rpc_url, override=None, timeout=5)
    try:
        return get_chain_id(rpc_url, override=None, timeout=5, strict=True)
    except Exception as e:
        abort(
            ctx,
            f"Chain ID lookup via {rpc_url} failed: {e}. Set CHAIN_ID or point at a serving node",
            from_exception=e,
        )
        raise AssertionError("unreachable: abort always raises") from e
