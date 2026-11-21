"""Object→principal ownership checks for coordinator-api routers (#1881).

The route security matrix authenticates the caller but says nothing about
*which* objects they may touch. These helpers resolve the JWT principal to
the identities it controls — its ``sub`` plus every wallet address registered
to the user — and bind agent-scoped ids through ``AgentIdentity``
(agent_id -> owner_address -> caller wallets), the same model
``agent_performance``/``agent_identity`` established for #1070. Admin
role bypasses; everything else fails closed.

#2418: agents registered through the agent-coordinator (``POST
/v1/agents/register``) never get an ``AgentIdentity`` row — that table is a
separate subsystem whose ids are server-generated ``agent_<hex>`` values.
Their ownership proof lives in the agent-coordinator registry as the
``identity_address`` binding, and the bridge to this service is the agent
session JWT: ``POST /api/v1/agent/auth/login`` mints a token carrying an
``agent_id`` claim only after a wallet signature proves control of the bound
identity. The fleet shares the JWT secret, so that claim verifies here — a
caller whose token ``agent_id`` equals the target agent id is authenticated
*as* that agent and passes the same fail-closed check.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlmodel import func, select

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


def jwt_agent_id(user: dict[str, Any]) -> str:
    """The ``agent_id`` claim on an agent-session JWT, or ``""``.

    Only the agent-coordinator login endpoint mints tokens with this claim,
    and only after proving control of the agent's bound ``identity_address``
    — so a matching claim is a verified agent identity, not a user assertion
    (#2418). User/admin JWTs never carry it.
    """
    return str(user.get("agent_id") or "")


def caller_agent_ids(session: Session, user: dict[str, Any]) -> set[str]:
    """Every agent_id the caller may act for.

    Wallet-owned ``AgentIdentity`` rows plus the caller's own agent-session
    JWT ``agent_id`` claim (#2418). Used for party-scoped reads and list
    filtering where "owns any party" is the rule rather than a single
    agent_id (#1876).
    """
    wallets = caller_wallets(session, user)
    owned = (
        {
            str(row.agent_id)
            for row in session.execute(select(AgentIdentity).where(func.lower(AgentIdentity.owner_address).in_(wallets)))
            .scalars()
            .all()
        }
        if wallets
        else set()
    )
    agent = jwt_agent_id(user)
    if agent:
        owned.add(agent)
    return owned


def agent_access_granted(session: Session, user: dict[str, Any], agent_id: str) -> bool:
    """True when the caller may act on ``agent_id``.

    Admin, a caller wallet matching the agent's ``AgentIdentity.owner_address``,
    or the caller's own agent-session JWT ``agent_id`` claim (#2418).
    """
    if is_admin(user):
        return True
    agent = jwt_agent_id(user)
    if agent and agent == agent_id:
        return True
    return bool(agent_owner_addresses(session, agent_id) & caller_wallets(session, user))


def agent_denied_detail(session: Session, agent_id: str) -> str:
    """403 detail naming which ownership check failed and the expected owner (#2418).

    Distinguishes "no such agent identity" from "owned by someone else", and
    points at the agent-session JWT path for agent-coordinator-registered
    agents that can never have an ``AgentIdentity`` row.
    """
    owners = agent_owner_addresses(session, agent_id)
    if not owners:
        return (
            f"no agent identity registered for agent_id '{agent_id}' — "
            "authenticate as the agent (agent login JWT) or control an owner wallet"
        )
    return (
        f"agent '{agent_id}' is owned by a different wallet ({', '.join(sorted(owners))}) — "
        "authenticate as the agent (agent login JWT) or control its owner wallet"
    )


def require_agent_access(session: Session, user: dict[str, Any], agent_id: str) -> None:
    """Caller must be admin, control the wallet owning this agent, or be the
    agent itself (agent-session JWT, #2418).

    Fails closed: an agent with no AgentIdentity row and no matching agent
    JWT cannot be acted on by non-admin callers (#1881).
    """
    if agent_access_granted(session, user, agent_id):
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=agent_denied_detail(session, agent_id))


def require_identity_access(session: Session, user: dict[str, Any], identity_value: str) -> None:
    """Caller must be admin or control ``identity_value`` (sub or wallet)."""
    if is_admin(user):
        return
    if str(identity_value or "").lower() in caller_identities(session, user):
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not the resource owner")
