"""Agent principal resolution for HTTP and WebSocket callers (Phase B1).

A *principal* is who the coordinator believes is on the other end of a
request. Three credential types resolve to one:

* **Agent JWT** — minted by ``POST /api/v1/agent/auth/login`` in exchange for
  a wallet signature; carries ``agent_id`` and ``wallet`` claims. The bound
  registry identity is re-checked on every resolution so a JWT for an agent
  whose binding was later removed stops resolving.
* **Signed-request headers** — ``X-Agent-Id`` / ``X-Agent-Signature`` /
  ``X-Agent-Timestamp`` / ``X-Agent-Nonce``, where the signature is over the
  canonical ``{"agent_id","timestamp","nonce"}`` claim in the
  ``aitbc-agent-req-v1`` domain. The coordinator enforces the timestamp skew
  window (``agent_msg_max_skew_seconds``) and one-time nonce dedup itself.
* **Shared operator key** — ``COORDINATOR_API_KEY`` / ``SECRET_KEY`` resolves
  to the fixed operator identity ``hub-coordinator`` with ``is_admin``, for
  hub tooling that pre-dates per-agent credentials. Admin/operator-role JWTs
  without an ``agent_id`` claim resolve to the same identity.

``optional_agent`` returns ``None`` whenever no usable credential is present —
including presented-but-invalid credentials, which are logged — so advisory
mode keeps pre-auth behaviour byte-for-byte. ``require_agent`` raises 401
instead, for endpoints that are authenticated in every mode. Per-endpoint
scoping (agent_id ↔ principal matching) lives in :func:`authorize_agent_scope`,
which is a no-op under ``AGENT_MSG_SIGNATURE_MODE=disabled``, logs mismatches
under ``advisory``, and rejects under ``enforce``.
"""

from __future__ import annotations

import hmac
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, Request, status

from aitbc.aitbc_logging import get_logger
from aitbc.crypto.agent_envelope import request_claim, verify_request_claim

from .. import state
from ..config import settings
from .nonce_store import get_nonce_store

logger = get_logger(__name__)

#: Fixed operator identity for the shared key and admin/operator JWTs that
#: carry no ``agent_id`` claim (spec: "hub-coordinator only").
OPERATOR_AGENT_ID = "hub-coordinator"

#: Header names for the signed-request credential.
HEADER_AGENT_ID = "X-Agent-Id"
HEADER_AGENT_SIGNATURE = "X-Agent-Signature"
HEADER_AGENT_TIMESTAMP = "X-Agent-Timestamp"
HEADER_AGENT_NONCE = "X-Agent-Nonce"

#: JWT roles that resolve to the operator identity when no agent_id is claimed.
_OPERATOR_ROLES = frozenset({"admin", "operator"})


@dataclass(frozen=True)
class AgentPrincipal:
    """An authenticated caller.

    ``agent_id`` is the identity the caller may act as; ``wallet`` is the
    registry-bound identity address for agent principals (``None`` for
    operator/user principals); ``is_admin`` marks principals that may cross
    agent boundaries on HTTP endpoints.
    """

    agent_id: str
    wallet: str | None = None
    auth_type: str = "unknown"  # "jwt" | "signed_headers" | "api_key"
    is_admin: bool = False


def _shared_key_value() -> str | None:
    """The shared coordinator credential, if one is configured."""
    return os.getenv("COORDINATOR_API_KEY") or os.getenv("SECRET_KEY")


def shared_key_principal(token: str | None) -> AgentPrincipal | None:
    """Resolve the shared coordinator key to the fixed operator principal."""
    expected = _shared_key_value()
    if expected and token and hmac.compare_digest(str(token), expected):
        return AgentPrincipal(agent_id=OPERATOR_AGENT_ID, auth_type="api_key", is_admin=True)
    return None


async def _bound_identity(agent_id: str) -> str | None:
    """The registry-bound identity address for ``agent_id``, or ``None``.

    A missing registry, an unregistered agent, or an agent with no bound
    identity all resolve to ``None`` — an agent credential without a binding
    is unverifiable and must not produce a principal.
    """
    registry = state.agent_registry
    if registry is None:
        return None
    try:
        agent = await registry.get_agent_by_id(agent_id)
    except Exception as e:
        logger.warning("Registry lookup for %s failed: %s", agent_id, e)
        return None
    if agent is None or not agent.identity_address:
        return None
    return agent.identity_address


async def jwt_principal(token: str | None) -> AgentPrincipal | None:
    """Resolve a JWT bearer token to a principal, or ``None`` if invalid."""
    if not token:
        return None
    try:
        from aitbc.auth import get_jwt_handler

        validation = get_jwt_handler().validate_token(token)
    except Exception as e:
        logger.warning("agent_auth=fail reason=jwt_error error=%s", e)
        return None
    if not validation.get("valid"):
        logger.warning("agent_auth=fail reason=invalid_jwt")
        return None
    payload: dict[str, Any] = validation.get("payload") or {}
    role = payload.get("role")
    agent_id = payload.get("agent_id")
    if agent_id:
        # An agent JWT only resolves while the agent stays registered+bound;
        # the claim's wallet is informational — the registry is authoritative.
        wallet = await _bound_identity(agent_id)
        if wallet is None:
            logger.warning("agent_auth=fail reason=agent_not_bound agent_id=%s", agent_id)
            return None
        return AgentPrincipal(agent_id=agent_id, wallet=wallet, auth_type="jwt", is_admin=role == "admin")
    if role in _OPERATOR_ROLES:
        return AgentPrincipal(agent_id=OPERATOR_AGENT_ID, auth_type="jwt", is_admin=True)
    subject = payload.get("sub") or payload.get("user_id")
    if subject:
        # A valid non-agent token is still *a* principal (enough for
        # /ws/status); it binds to its subject and matches no agent_id.
        return AgentPrincipal(agent_id=str(subject), auth_type="jwt", is_admin=False)
    return None


async def signed_headers_principal(request: Request) -> AgentPrincipal | None:
    """Resolve ``X-Agent-*`` signed-request headers to a principal.

    Returns ``None`` when no such headers are present, and — after logging
    ``agent_auth=fail`` — when a present credential is incomplete, badly
    signed, stale, unbound, or replayed.
    """
    agent_id = request.headers.get(HEADER_AGENT_ID)
    signature = request.headers.get(HEADER_AGENT_SIGNATURE)
    timestamp = request.headers.get(HEADER_AGENT_TIMESTAMP)
    nonce = request.headers.get(HEADER_AGENT_NONCE)
    presented = (agent_id, signature, timestamp, nonce)
    if not any(presented):
        return None
    if agent_id is None or signature is None or timestamp is None or nonce is None:
        logger.warning("agent_auth=fail reason=incomplete_headers agent_id=%s", agent_id)
        return None

    identity = await _bound_identity(agent_id)
    if identity is None:
        logger.warning("agent_auth=fail reason=agent_not_bound agent_id=%s", agent_id)
        return None
    claim = request_claim(agent_id=agent_id, timestamp=timestamp, nonce=nonce)
    if not verify_request_claim(claim, signature, identity):
        logger.warning("agent_auth=fail reason=invalid_signature agent_id=%s", agent_id)
        return None
    try:
        signed_at = datetime.fromisoformat(timestamp)
        if signed_at.tzinfo is None:
            signed_at = signed_at.replace(tzinfo=UTC)
    except ValueError:
        logger.warning("agent_auth=fail reason=stale_timestamp agent_id=%s", agent_id)
        return None
    if abs((datetime.now(UTC) - signed_at).total_seconds()) > settings.agent_msg_max_skew_seconds:
        logger.warning("agent_auth=fail reason=stale_timestamp agent_id=%s", agent_id)
        return None
    if not await get_nonce_store().check_request_nonce(agent_id, nonce, settings.agent_msg_max_skew_seconds):
        logger.warning("agent_auth=fail reason=nonce_replayed agent_id=%s", agent_id)
        return None
    return AgentPrincipal(agent_id=agent_id, wallet=identity, auth_type="signed_headers")


def _bearer_token(request: Request) -> str | None:
    authorization = request.headers.get("Authorization", "")
    if authorization.startswith("Bearer "):
        return authorization[7:]
    return None


async def resolve_request_principal(request: Request) -> AgentPrincipal | None:
    """Resolve any credential on the request to a principal, or ``None``.

    Order: signed headers → shared key (``X-Api-Key``, ``?token=``, or a
    Bearer carrying the key itself) → Bearer JWT. A credential that fails to
    resolve falls through to the next kind rather than poisoning the request.
    """
    principal = await signed_headers_principal(request)
    if principal is not None:
        return principal
    for candidate in (
        request.headers.get("X-Api-Key"),
        request.query_params.get("token"),
        _bearer_token(request),
    ):
        principal = shared_key_principal(candidate)
        if principal is not None:
            return principal
    return await jwt_principal(_bearer_token(request))


async def resolve_ws_principal(token: str | None) -> AgentPrincipal | None:
    """Resolve the WS ``?token=`` credential to a principal, or ``None``.

    Shared key → the fixed ``hub-coordinator`` operator identity; JWT → the
    ``agent_id`` claim (verified against the registry binding), or the
    operator identity for admin/operator tokens without one.
    """
    principal = shared_key_principal(token)
    if principal is not None:
        return principal
    return await jwt_principal(token)


async def optional_agent(request: Request) -> AgentPrincipal | None:
    """FastAPI dependency: the request's principal, or ``None``.

    Never raises — advisory/disabled modes must keep unauthenticated traffic
    working, and presented-but-invalid credentials degrade to anonymous (with
    a log line) rather than changing status codes.
    """
    return await resolve_request_principal(request)


async def require_agent(request: Request) -> AgentPrincipal:
    """FastAPI dependency: any valid principal, else 401.

    Accepts agent JWTs, signed headers, the shared operator key, and
    admin/operator/user JWTs — "any valid principal" for endpoints like
    ``GET /ws/status`` that are authenticated in every mode.
    """
    principal = await resolve_request_principal(request)
    if principal is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return principal


def authorize_agent_scope(principal: AgentPrincipal | None, agent_id: str, action: str) -> None:
    """Enforce that ``principal`` may act on ``agent_id``'s resources.

    * ``disabled`` — no-op (deployed default stays byte-for-byte compatible).
    * ``advisory`` — mismatches log ``agent_authz_mismatch`` and are allowed.
    * ``enforce`` — no principal → 401; non-admin principal acting on another
      agent_id → 403. ``is_admin`` principals (operator key, admin JWT) bypass
      the match so hub tooling keeps working.

    Advisory mode also logs ``admin_auth_missing`` when no principal resolved —
    the Phase C operator signal for "this call would 401 under enforce".
    """
    mode = settings.agent_msg_signature_mode
    if mode == "disabled":
        return
    if principal is None:
        if mode == "enforce":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="agent authentication required",
                headers={"WWW-Authenticate": "Bearer"},
            )
        logger.warning("admin_auth_missing action=%s agent_id=%s mode=%s — enforce would 401", action, agent_id, mode)
        return
    if principal.is_admin or principal.agent_id == agent_id:
        return
    if mode == "enforce":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="agent_mismatch")
    logger.warning(
        "agent_authz_mismatch action=%s agent_id=%s principal=%s auth_type=%s mode=%s",
        action,
        agent_id,
        principal.agent_id,
        principal.auth_type,
        mode,
    )


def authorize_any_principal(principal: AgentPrincipal | None, action: str) -> None:
    """Mode-gated "authenticated callers only" check for unscoped endpoints.

    For routes that own no per-agent resource but must stop serving anonymous
    callers once auth is switched on (``POST /v1/tasks/submit`` — a buyer agent
    JWT, signed headers or the operator key all satisfy it).

    * ``disabled`` — no-op (deployed default stays byte-for-byte compatible).
    * ``advisory`` — a missing principal logs ``admin_auth_missing`` and passes.
    * ``enforce`` — no principal → 401; any resolved principal passes.
    """
    mode = settings.agent_msg_signature_mode
    if mode == "disabled" or principal is not None:
        return
    if mode == "enforce":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="agent authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    logger.warning("admin_auth_missing action=%s mode=%s — enforce would 401", action, mode)


def authorize_admin_scope(principal: AgentPrincipal | None, action: str) -> None:
    """Admin/operator-only gate for hub-control endpoints (Phase C).

    Covers the coordinator's operator surface — broadcast, load-balancer
    strategy/stats, peer add/remove/read, registry stats, escrow expiry sweep,
    queue clear — which shipped unauthenticated.

    * ``disabled`` — no-op (deployed default stays byte-for-byte compatible).
    * ``advisory`` — a missing principal logs ``admin_auth_missing``; a
      present-but-non-admin principal logs ``scope_mismatch``; both pass.
    * ``enforce`` — no principal → 401; non-``is_admin`` principal → 403.
      ``is_admin`` is held by the shared operator key and admin/operator JWTs
      (and agent JWTs minted with role=admin); a regular agent principal does
      not reach these routes.
    """
    mode = settings.agent_msg_signature_mode
    if mode == "disabled":
        return
    if principal is None:
        if mode == "enforce":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="admin authentication required",
                headers={"WWW-Authenticate": "Bearer"},
            )
        logger.warning("admin_auth_missing action=%s mode=%s — enforce would 401", action, mode)
        return
    if principal.is_admin:
        return
    if mode == "enforce":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin_required")
    logger.warning(
        "scope_mismatch action=%s principal=%s auth_type=%s mode=%s — enforce would 403",
        action,
        principal.agent_id,
        principal.auth_type,
        mode,
    )
