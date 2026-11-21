"""
Settlement router.

#2385: the inter-chain HTLC settlement rail is retired. Every transaction
the lifecycle would emit is unsigned at the top level (the protocol escrow
is keyless) and ``v9_signature_verdict`` exempts only ``BRIDGE_*`` — HTLC
emissions carry no ``payload.auth`` at all, so unlike the v17-revived
staking/bounty surfaces there is no unarmed-then-live path; a revival
would need a new consensus version. Every mutating endpoint therefore
answers HTTP 410 Gone up front instead of writing bookkeeping rows or
queueing transactions that can never seal.

The read endpoints (``GET /{escrow_id}``, ``/{escrow_id}/status``,
``/{escrow_id}/proofs``) stay live so existing escrow records remain
inspectable.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from aitbc.rate_limiting import rate_limit

from ...config import settings
from ...database import ChainDbMissingError
from ...logger import get_logger
from ..escrow_routes import verify_rpc_api_key
from ..retired import raise_for_retired_settlement

_logger = get_logger(__name__)

# The perimeter only allowlists /rpc/escrow/ — so the whole router requires
# X-API-Key, the same control escrow_routes applies. Fail-closed: when
# BLOCKCHAIN_RPC_API_KEY is unset every route returns 503.
router = APIRouter(prefix="/bridge/settlement", tags=["settlement"], dependencies=[Depends(verify_rpc_api_key)])


@router.post("/create", summary="Create cross-chain escrow (retired, #2385)")
@rate_limit(rate=10, per=60)
def create_escrow_route(request: Request, escrow_data: dict[str, Any]) -> dict[str, Any]:  # noqa: ARG001
    """Retired: inter-chain HTLC escrow creation cannot seal at block v9 (#2385)."""
    raise_for_retired_settlement()


@router.post("/{escrow_id}/lock", summary="Lock escrow funds (retired, #2385)")
@rate_limit(rate=10, per=60)
def lock_escrow_route(request: Request, escrow_id: str) -> dict[str, Any]:  # noqa: ARG001
    """Retired: inter-chain HTLC escrow lock cannot seal at block v9 (#2385)."""
    raise_for_retired_settlement()


@router.post("/{escrow_id}/verify", summary="Verify lock proof (retired, #2385)")
@rate_limit(rate=10, per=60)
def verify_lock_route(request: Request, escrow_id: str) -> dict[str, Any]:  # noqa: ARG001
    """Retired: the lock it would verify can never exist (#2385)."""
    raise_for_retired_settlement()


@router.post("/{escrow_id}/execute", summary="Execute trade on destination (retired, #2385)")
@rate_limit(rate=10, per=60)
def execute_trade_route(request: Request, escrow_id: str) -> dict[str, Any]:  # noqa: ARG001
    """Retired: the verified state it requires is unreachable (#2385)."""
    raise_for_retired_settlement()


@router.post("/{escrow_id}/settle", summary="Settle escrow with secret (retired, #2385)")
@rate_limit(rate=10, per=60)
def settle_escrow_route(request: Request, escrow_id: str, body: dict[str, Any]) -> dict[str, Any]:  # noqa: ARG001
    """Retired: HTLC complete_swap emits no payload.auth and cannot seal (#2385)."""
    raise_for_retired_settlement()


@router.post("/{escrow_id}/refund", summary="Refund escrow (retired, #2385)")
@rate_limit(rate=10, per=60)
def refund_escrow_route(request: Request, escrow_id: str) -> dict[str, Any]:  # noqa: ARG001
    """Retired: HTLC refund_swap emits no payload.auth and cannot seal (#2385)."""
    raise_for_retired_settlement()


@router.post("/{escrow_id}/extend-timeout", summary="Extend escrow timeout (retired, #2385)")
@rate_limit(rate=10, per=60)
def extend_timeout_route(request: Request, escrow_id: str, body: dict[str, Any]) -> dict[str, Any]:  # noqa: ARG001
    """Retired: extending a timeout on a rail that cannot settle is meaningless (#2385)."""
    raise_for_retired_settlement()


@router.post("/{escrow_id}/dispute", summary="File a dispute for an escrow (retired, #2385)")
@rate_limit(rate=10, per=60)
def file_escrow_dispute_route(request: Request, escrow_id: str, body: dict[str, Any]) -> dict[str, Any]:  # noqa: ARG001
    """Retired: no new escrow can be created, so no new dispute can arise (#2385)."""
    raise_for_retired_settlement()


@router.post("/{escrow_id}/resolve", summary="Resolve a dispute (retired, #2385)")
@rate_limit(rate=10, per=60)
def resolve_escrow_dispute_route(request: Request, escrow_id: str, body: dict[str, Any]) -> dict[str, Any]:  # noqa: ARG001
    """Retired: dispute resolution on the dead HTLC rail is meaningless (#2385)."""
    raise_for_retired_settlement()


@router.get("/{escrow_id}", summary="Get escrow details")
@rate_limit(rate=100, per=60)
async def get_escrow_route(request: Request, escrow_id: str) -> dict[str, Any]:  # noqa: ARG001
    """Get escrow details."""
    if not settings.escrow_enabled:
        raise HTTPException(status_code=503, detail="Settlement not enabled")
    try:
        from ...cross_chain.settlement import CrossChainSettlementService

        service = CrossChainSettlementService(chain_id=settings.chain_id)
        result = await service.get_escrow(escrow_id)
        if not result:
            raise HTTPException(status_code=404, detail="Escrow not found")
        return result
    except HTTPException:
        raise
    except ChainDbMissingError as e:
        # #2269: an unprovisioned source/dest chain.db is a client-input
        # problem, not a server fault — name the chain, don't 500.
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        _logger.error("Get escrow failed: %s", e)
        _logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/{escrow_id}/status", summary="Get escrow status")
@rate_limit(rate=100, per=60)
async def get_escrow_status_route(request: Request, escrow_id: str) -> dict[str, Any]:  # noqa: ARG001
    """Get escrow status."""
    if not settings.escrow_enabled:
        raise HTTPException(status_code=503, detail="Settlement not enabled")
    try:
        from ...cross_chain.settlement import CrossChainSettlementService

        service = CrossChainSettlementService(chain_id=settings.chain_id)
        status = await service.get_escrow_status(escrow_id)
        return {"escrow_id": escrow_id, "status": status}
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ChainDbMissingError as e:
        # #2269: an unprovisioned source/dest chain.db is a client-input
        # problem, not a server fault — name the chain, don't 500.
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        _logger.error("Get escrow status failed: %s", e)
        _logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/{escrow_id}/proofs", summary="Get proof chain")
@rate_limit(rate=100, per=60)
async def get_proof_chain_route(request: Request, escrow_id: str) -> dict[str, Any]:  # noqa: ARG001
    """Get all proofs for an escrow."""
    if not settings.escrow_enabled:
        raise HTTPException(status_code=503, detail="Settlement not enabled")
    try:
        from ...cross_chain.settlement import CrossChainSettlementService

        service = CrossChainSettlementService(chain_id=settings.chain_id)
        proofs = await service.get_proof_chain(escrow_id)
        return {"escrow_id": escrow_id, "proofs": proofs}
    except HTTPException:
        raise
    except ChainDbMissingError as e:
        # #2269: an unprovisioned source/dest chain.db is a client-input
        # problem, not a server fault — name the chain, don't 500.
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        _logger.error("Get proof chain failed: %s", e)
        _logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e
