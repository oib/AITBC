"""Escrow refund relay router (ESCROW-REFUND-1).

``POST /v1/escrow/refund`` accepts ``{job_id, reason?}`` and forwards the
refund to the settlement-capable chain RPC's
``/rpc/escrow/{job_id}/refund`` from the coordinator's position inside
the nginx allowlist. The chain route itself is unauthenticated — the node
signs the refund with its settlement key — so the JWT boundary here, plus
the buyer↔credential binding check against the on-chain escrow row and
the coordinator job-state gate, is the auth and audit layer.

Phase-1 scope (director ruling on #471): coordinator-minted job_ids only.
Market-minted escrows have no ``job`` row and are refused structurally;
they stay settlement-node refunds.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlmodel import Session

from aitbc.rate_limiting import rate_limit

from ....auth import AdminOrClientDep
from ....storage import get_session
from ..operations import begin_operation, complete_operation, fail_operation, record_rejection
from ..services.escrow_refund_relay import EscrowRefundRelayService

router = APIRouter(tags=["escrow"])


class EscrowRefundRelayRequest(BaseModel):
    """The relayed refund payload — no amount: the chain refunds the
    escrow's locked amount minus already-released legs, clamped to the
    sealed lock."""

    job_id: str = Field(..., min_length=1, max_length=128)
    reason: Literal["buyer_requested", "job_failed", "timeout", "expired"] = "buyer_requested"


class EscrowRefundRelayResponse(BaseModel):
    """The chain's refund result (``duplicate`` marks a replayed relay)."""

    success: bool = True
    contract_id: str | None = None
    tx_hash: str | None = None
    refund_tx_hash: str | None = None
    refunded_amount: str | None = None
    message: str | None = None
    duplicate: bool = False


def _client_rate_key(request: Request) -> str:
    """Rate-limit per client credential, not per source IP."""
    return request.headers.get("authorization") or "unknown"


@router.post(
    "/escrow/refund",
    response_model=EscrowRefundRelayResponse,
    summary="Relay an escrow refund to the settlement node",
)
@rate_limit(rate=30, per=60, key_func=_client_rate_key)
@rate_limit(rate=10, per=3600, key_func=_client_rate_key)
async def relay_escrow_refund(
    relay_data: EscrowRefundRelayRequest,
    session: Annotated[Session, Depends(get_session)],
    user: AdminOrClientDep,
    request: Request,
) -> Any:
    """Relay an escrow refund to the chain RPC.

    Auth: the on-chain escrow's ``buyer`` must equal the wallet bound to
    the JWT subject (admin may refund any buyer's escrow — the chain
    still owns settlement validation). The coordinator ``job`` row must
    exist and be terminal-unpaid (FAILED/CANCELED/EXPIRED, or past
    ``expires_at``); COMPLETED is never refundable. Replays of the same
    job — a stored relay row or an already-refunded escrow — return the
    stored ``refund_tx_hash`` without a second chain call. The per-client
    hourly cap keeps a stolen JWT from sweeping a client's locks.
    """
    client_id = user["sub"]
    is_admin = user.get("role") == "admin"
    body = relay_data.model_dump(mode="python")

    key, attempt, early = await begin_operation(
        request,
        "escrow_refund_relay",
        {"client_id": client_id, "body": body},
    )
    if early is not None:
        return early

    service = EscrowRefundRelayService(session)
    try:
        result = await service.refund(client_id, is_admin, body)
        await complete_operation(
            key,
            attempt,
            EscrowRefundRelayResponse.model_validate(result).model_dump(mode="json"),
            response_status=200,
        )
        return result
    except HTTPException as e:
        await record_rejection(key, attempt, e.status_code, {"detail": e.detail})
        raise
    except Exception as e:
        await fail_operation(key, attempt, type(e).__name__)
        raise
