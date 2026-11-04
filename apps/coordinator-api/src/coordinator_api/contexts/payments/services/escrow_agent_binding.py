"""Resolve and validate agent_id ↔ payment address for escrow lock (AGENT-SPEND-D-1)."""

from __future__ import annotations

import os

from fastapi import HTTPException, status
from sqlmodel import Session

from aitbc.crypto.signature_recovery import canonical_address

from coordinator_api.agent_identity.registry import CrossChainRegistry

from ....config import settings


def default_resolve_chain_id() -> int:
    """Chain id used by CrossChainMapping for native AIT payment addresses."""
    raw = (settings.native_chain_id or os.getenv("CHAIN_ID") or "1").strip()
    try:
        return int(raw)
    except ValueError:
        return 1


async def resolve_agent_payment_address(session: Session, agent_id: str, chain_id: int | None = None) -> str:
    cid = chain_id if chain_id is not None else default_resolve_chain_id()
    registry = CrossChainRegistry(session)
    address = await registry.resolve_agent_identity(agent_id, cid)
    if not address:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no payment address for agent {agent_id} on chain {cid}",
        )
    return canonical_address(address)


async def assert_agent_address_binding(
    session: Session,
    agent_id: str,
    payment_address: str,
    *,
    role: str,
    chain_id: int | None = None,
) -> None:
    resolved = await resolve_agent_payment_address(session, agent_id, chain_id)
    if resolved != canonical_address(payment_address):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{role} address does not match resolved address for agent {agent_id}",
        )
