"""Escrow release relay router (ESCROW-RELEASE-1).

``POST /v1/escrow/release`` accepts ``{job_id, amount, job_tx_hash}`` and
forwards the release to the settlement-capable chain RPC's
``/rpc/escrow/{job_id}/release`` from the coordinator's position inside
the nginx allowlist. The chain route itself is unauthenticated — the node
signs the release with its settlement key — so the JWT boundary here, plus
the buyer↔credential binding check against the on-chain escrow row, is the
auth and audit layer for market escrow releases.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlmodel import Session

from aitbc.rate_limiting import rate_limit

from ....auth import AdminOrClientDep
from ....storage import get_session
from ..operations import begin_operation, complete_operation, fail_operation, record_rejection
from ..services.escrow_release_relay import EscrowReleaseRelayService

router = APIRouter(tags=["escrow"])


class EscrowReleaseRelayRequest(BaseModel):
    """The relayed release payload — ``job_tx_hash`` is the optional
    proof-of-work reference the chain route accepts."""

    job_id: str = Field(..., min_length=1, max_length=128)
    amount: str | int | Decimal = Field(...)
    job_tx_hash: str | None = Field(default=None, max_length=128)


class EscrowReleaseRelayResponse(BaseModel):
    """The chain's release result (``duplicate`` marks a replayed relay)."""

    success: bool = True
    contract_id: str | None = None
    tx_hash: str | None = None
    duplicate: bool = False
    released_amount: str | None = None
    refunded_amount: str | None = None
    refund_tx_hash: str | None = None
    message: str | None = None


def _client_rate_key(request: Request) -> str:
    """Rate-limit per client credential, not per source IP."""
    return request.headers.get("authorization") or "unknown"


@router.post(
    "/escrow/release",
    response_model=EscrowReleaseRelayResponse,
    summary="Relay an escrow release to the settlement node",
)
@rate_limit(rate=30, per=60, key_func=_client_rate_key)
async def relay_escrow_release(
    relay_data: EscrowReleaseRelayRequest,
    session: Annotated[Session, Depends(get_session)],
    user: AdminOrClientDep,
    request: Request,
) -> Any:
    """Relay an escrow release to the chain RPC.

    Auth: the on-chain escrow's ``buyer`` must equal the wallet bound to
    the JWT subject (admin may release any buyer's escrow — the chain
    still owns settlement validation). The release amount is bounded by
    the escrow's locked amount for non-admin callers. Replays of the same
    job — a stored relay row or an already-released escrow — return the
    stored ``tx_hash`` without a second chain call.
    """
    client_id = user["sub"]
    is_admin = user.get("role") == "admin"
    body = relay_data.model_dump(mode="python")

    key, attempt, early = await begin_operation(
        request,
        "escrow_release_relay",
        {"client_id": client_id, "body": body},
    )
    if early is not None:
        return early

    service = EscrowReleaseRelayService(session)
    try:
        result = await service.release(client_id, is_admin, body)
        await complete_operation(
            key,
            attempt,
            EscrowReleaseRelayResponse.model_validate(result).model_dump(mode="json"),
            response_status=200,
        )
        return result
    except HTTPException as e:
        await record_rejection(key, attempt, e.status_code, {"detail": e.detail})
        raise
    except Exception as e:
        await fail_operation(key, attempt, type(e).__name__)
        raise
