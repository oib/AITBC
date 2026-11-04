"""Resolve agent_id to payment address via coordinator agent-identity API."""

from __future__ import annotations

from typing import Any

from aitbc.config.hub import hub_coordinator_url
from aitbc.crypto.signature_recovery import canonical_address

from ..config import get_config
from .error_handling import abort
from .http_client import AITBCHTTPClient, auth_client_kwargs, get_logger, service_root_url

logger = get_logger(__name__)


def _coordinator_base_url() -> str:
    config = get_config()
    raw = config.coordinator_api_url or hub_coordinator_url() or config.hub_discovery_url or "http://localhost:8203"
    return service_root_url(str(raw), "http://localhost:8203")


def resolve_agent_payment_address(ctx, agent_id: str, chain_id: int = 1) -> str:
    """Return the chain payment address for ``agent_id`` (raises via abort on failure)."""
    config = get_config()
    base = _coordinator_base_url()
    path = f"/v1/agent-identity/identities/{agent_id}/resolve/{chain_id}"
    auth = auth_client_kwargs(config_key=config.coordinator_api_key)
    try:
        client = AITBCHTTPClient(base_url=base, timeout=15, **auth)
        data: dict[str, Any] = client.get(path)
    except Exception as exc:
        logger.warning("agent identity resolve failed for %s: %s", agent_id, exc)
        abort(ctx, f"Could not resolve payment address for agent {agent_id!r} ({exc})")
    address = data.get("address") if isinstance(data, dict) else None
    if not address:
        abort(ctx, f"No payment address mapped for agent {agent_id!r} on chain {chain_id}")
    return canonical_address(str(address))


def resolve_escrow_parties(
    ctx,
    *,
    buyer: str | None,
    provider: str | None,
    buyer_agent_id: str | None = None,
    provider_agent_id: str | None = None,
    chain_id: int = 1,
) -> tuple[str, str, str | None, str | None]:
    """Resolve optional agent ids to payment addresses; verify explicit addresses match."""
    if buyer_agent_id:
        resolved_buyer = resolve_agent_payment_address(ctx, buyer_agent_id, chain_id)
        if buyer and canonical_address(buyer) != resolved_buyer:
            abort(ctx, f"buyer address does not match resolved address for agent {buyer_agent_id!r}")
        buyer = buyer or resolved_buyer
    if provider_agent_id:
        resolved_provider = resolve_agent_payment_address(ctx, provider_agent_id, chain_id)
        if provider and canonical_address(provider) != resolved_provider:
            abort(ctx, f"provider address does not match resolved address for agent {provider_agent_id!r}")
        provider = provider or resolved_provider
    if not buyer or not provider:
        abort(
            ctx,
            "Escrow requires buyer and provider payment addresses "
            "(--buyer-address / --provider-address and/or --buyer-agent-id / --provider-agent-id)",
        )
    return str(buyer), str(provider), buyer_agent_id, provider_agent_id
