"""Resolve agent_id to payment address via coordinator agent-identity API."""

from __future__ import annotations

from typing import Any

from aitbc.config.hub import normalize_hub_base
from aitbc.crypto.signature_recovery import canonical_address

from ..config import get_config
from .error_handling import abort
from .http_client import AITBCHTTPClient, get_logger

logger = get_logger(__name__)


def _coordinator_base_url() -> str:
    config = get_config()
    raw = getattr(config, "hub_discovery_url", None) or getattr(config, "coordinator_url", None) or "hub.aitbc.invalid"
    return normalize_hub_base(str(raw)) or str(raw)


def resolve_agent_payment_address(ctx, agent_id: str, chain_id: int = 1) -> str:
    """Return the chain payment address for ``agent_id`` (raises via abort on failure)."""
    base = _coordinator_base_url()
    path = f"/v1/agent-identity/identities/{agent_id}/resolve/{chain_id}"
    try:
        client = AITBCHTTPClient(base_url=base, timeout=15)
        data: dict[str, Any] = client.get(path)
    except Exception as exc:
        logger.warning("agent identity resolve failed for %s: %s", agent_id, exc)
        abort(ctx, f"Could not resolve payment address for agent {agent_id!r} ({exc})")
    address = data.get("address") if isinstance(data, dict) else None
    if not address:
        abort(ctx, f"No payment address mapped for agent {agent_id!r} on chain {chain_id}")
    return canonical_address(str(address))
