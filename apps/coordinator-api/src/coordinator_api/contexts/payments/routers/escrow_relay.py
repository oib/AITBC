"""Escrow relay router (ESCROW-ROUTE-1).

``POST /v1/escrow/relay`` accepts the exact ``/rpc/escrow/create`` payload —
buyer-signed ``lock_tx`` included — and submits it to the settlement-capable
chain RPC from the coordinator's position inside the nginx allowlist. Customer
nodes cannot reach that endpoint directly (no token auth exists at the rpc
edge, only source-IP gating), so the JWT boundary here is the auth and audit
layer for market escrow creates.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session

from aitbc.rate_limiting import rate_limit

from ....auth import AdminOrClientDep
from ....storage import get_session
from ..operations import begin_operation, complete_operation, fail_operation, record_rejection
from ..services.escrow_relay import EscrowRelayService

router = APIRouter(tags=["escrow"])


class EscrowRelayRequest(BaseModel):
    """The ``/rpc/escrow/create`` payload, forwarded verbatim to the chain.

    Extra keys (``lock_signature``, ``energy_quote``, ``energy_quote_digest``)
    are allowed and passed through unchanged — the chain route owns their
    validation.
    """

    model_config = ConfigDict(extra="allow")

    job_id: str = Field(..., min_length=1, max_length=128)
    buyer: str = Field(..., min_length=1, max_length=128)
    provider: str = Field(..., min_length=1, max_length=128)
    amount: str | int | Decimal = Field(...)
    lock_tx: dict[str, Any]


class EscrowRelayResponse(BaseModel):
    """The chain's contract id (``duplicate`` marks a replayed relay)."""

    contract_id: str | None = None
    duplicate: bool = False


def _client_rate_key(request: Request) -> str:
    """Rate-limit per client credential, not per source IP."""
    return request.headers.get("authorization") or "unknown"


@router.post(
    "/escrow/relay",
    response_model=EscrowRelayResponse,
    summary="Relay a buyer-signed escrow create to the settlement node",
)
@rate_limit(rate=30, per=60, key_func=_client_rate_key)
async def relay_escrow(
    relay_data: EscrowRelayRequest,
    session: Annotated[Session, Depends(get_session)],
    user: AdminOrClientDep,
    request: Request,
) -> Any:
    """Relay a buyer-signed escrow lock to the chain RPC.

    Auth: the JWT subject's bound wallet must equal ``buyer`` (admin may relay
    any buyer — the chain still validates the lock signature). Amounts are
    capped at ``ESCROW_RELAY_MAX_UNITS`` compute units for non-admin callers.
    Replays of the same lock return the stored ``contract_id`` without a
    second chain call.
    """
    client_id = user["sub"]
    is_admin = user.get("role") == "admin"
    body = relay_data.model_dump(mode="python")

    key, attempt, early = await begin_operation(
        request,
        "escrow_relay",
        {"client_id": client_id, "body": body},
    )
    if early is not None:
        return early

    service = EscrowRelayService(session)
    try:
        result = await service.relay(client_id, is_admin, body)
        await complete_operation(
            key, attempt, EscrowRelayResponse.model_validate(result).model_dump(mode="json"), response_status=200
        )
        return result
    except HTTPException as e:
        await record_rejection(key, attempt, e.status_code, {"detail": e.detail})
        raise
    except Exception as e:
        await fail_operation(key, attempt, type(e).__name__)
        raise
