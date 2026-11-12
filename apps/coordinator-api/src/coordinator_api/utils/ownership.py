"""Object→principal ownership checks for coordinator-api routers (#1881).

The route security matrix authenticates the caller but says nothing about
*which* objects they may touch. These helpers resolve the JWT principal to
the identities it controls — its ``sub`` plus every wallet address registered
to the user — and bind agent-scoped ids through ``AgentIdentity``
(agent_id -> owner_address -> caller wallets), the same model
``agent_performance``/``agent_identity`` established for #1070. Admin
role bypasses; everything else fails closed.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlmodel import select

from ..contexts.agent_identity.domain.agent_identity import AgentIdentity
from ..contexts.infrastructure.domain.user import Wallet


def is_admin(user: dict[str, Any]) -> bool:
    return user.get("role") == "admin"


def caller_wallets(session: Session, user: dict[str, Any]) -> set[str]:
    """Wallet addresses the authenticated caller controls (users.id -> wallets)."""
    sub = str(user.get("sub") or "")
    if not sub:
        return set()
    return {
        str(w.address).lower()
        for w in session.execute(select(Wallet).where(Wallet.user_id == sub)).scalars().all()
        if w.address
    }


def caller_identities(session: Session, user: dict[str, Any]) -> set[str]:
    """Every lowercase identity string the caller may act as: sub + wallets."""
    sub = str(user.get("sub") or "")
    identities = {sub.lower()} if sub else set()
    return identities | caller_wallets(session, user)


def agent_owner_addresses(session: Session, agent_id: str) -> set[str]:
    """Owner wallet addresses registered for an agent identity, if any."""
    identity = session.execute(select(AgentIdentity).where(AgentIdentity.agent_id == agent_id)).scalars().first()
    if identity is None or not identity.owner_address:
        return set()
    return {str(identity.owner_address).lower()}


def require_agent_access(session: Session, user: dict[str, Any], agent_id: str) -> None:
    """Caller must be admin or control the wallet owning this agent.

    Fails closed: an agent with no AgentIdentity row has no provable owner
    and cannot be acted on by non-admin callers (#1881).
    """
    if is_admin(user):
        return
    if agent_owner_addresses(session, agent_id) & caller_wallets(session, user):
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not the agent owner")


def require_identity_access(session: Session, user: dict[str, Any], identity_value: str) -> None:
    """Caller must be admin or control ``identity_value`` (sub or wallet)."""
    if is_admin(user):
        return
    if str(identity_value or "").lower() in caller_identities(session, user):
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not the resource owner")
