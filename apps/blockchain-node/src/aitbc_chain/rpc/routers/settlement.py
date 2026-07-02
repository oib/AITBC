"""
Settlement router.
"""

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from aitbc.rate_limiting import rate_limit

from ...config import settings
from ...logger import get_logger

_logger = get_logger(__name__)

router = APIRouter(prefix="/bridge/settlement", tags=["settlement"])


@router.post("/create", summary="Create cross-chain escrow")
@rate_limit(rate=10, per=60)
async def create_escrow_route(request: Request, escrow_data: dict[str, Any]) -> dict[str, Any]:
    """Create a cross-chain escrow for atomic settlement."""
    if not settings.escrow_enabled:
        raise HTTPException(status_code=503, detail="Settlement not enabled (escrow_enabled=false)")
    try:
        from ...cross_chain.settlement import CrossChainSettlementService

        service = CrossChainSettlementService(chain_id=settings.chain_id)
        result = await service.create_escrow(
            trade_id=escrow_data["trade_id"],
            source_chain=escrow_data["source_chain"],
            dest_chain=escrow_data["dest_chain"],
            sender=escrow_data["sender"],
            recipient=escrow_data["recipient"],
            amount=escrow_data["amount"],
            timeout_seconds=escrow_data.get("timeout_seconds"),
        )
        return result
    except KeyError as e:
        raise HTTPException(status_code=400, detail=f"Missing required field: {e.args[0]}") from e
    except HTTPException:
        raise
    except Exception as e:
        _logger.error("Create escrow failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Create escrow failed: {e}") from e


@router.post("/{escrow_id}/lock", summary="Lock escrow funds")
@rate_limit(rate=10, per=60)
async def lock_escrow_route(escrow_id: str) -> dict[str, Any]:
    """Lock funds on source chain for an escrow."""
    if not settings.escrow_enabled:
        raise HTTPException(status_code=503, detail="Settlement not enabled")
    try:
        from ...cross_chain.settlement import CrossChainSettlementService

        service = CrossChainSettlementService(chain_id=settings.chain_id)
        return await service.lock_escrow(escrow_id)
    except HTTPException:
        raise
    except Exception as e:
        _logger.error("Lock escrow failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Lock escrow failed: {e}") from e


@router.post("/{escrow_id}/verify", summary="Verify lock proof")
@rate_limit(rate=10, per=60)
async def verify_lock_route(escrow_id: str) -> dict[str, Any]:
    """Verify lock proof on destination chain."""
    if not settings.escrow_enabled:
        raise HTTPException(status_code=503, detail="Settlement not enabled")
    try:
        from ...cross_chain.settlement import CrossChainSettlementService

        service = CrossChainSettlementService(chain_id=settings.chain_id)
        return await service.verify_lock(escrow_id)
    except HTTPException:
        raise
    except Exception as e:
        _logger.error("Verify lock failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Verify lock failed: {e}") from e


@router.post("/{escrow_id}/execute", summary="Execute trade on destination")
@rate_limit(rate=10, per=60)
async def execute_trade_route(escrow_id: str) -> dict[str, Any]:
    """Execute trade on destination chain."""
    if not settings.escrow_enabled:
        raise HTTPException(status_code=503, detail="Settlement not enabled")
    try:
        from ...cross_chain.settlement import CrossChainSettlementService

        service = CrossChainSettlementService(chain_id=settings.chain_id)
        return await service.execute_trade(escrow_id)
    except HTTPException:
        raise
    except Exception as e:
        _logger.error("Execute trade failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Execute trade failed: {e}") from e


@router.post("/{escrow_id}/settle", summary="Settle escrow with secret")
@rate_limit(rate=10, per=60)
async def settle_escrow_route(escrow_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """Reveal secret and settle escrow on both chains.

    Accepts JSON body ``{"secret": "<hex_secret>"}`` matching SettlementClient.
    """
    if not settings.escrow_enabled:
        raise HTTPException(status_code=503, detail="Settlement not enabled")
    try:
        from ...cross_chain.settlement import CrossChainSettlementService

        secret = body.get("secret", "")
        if not secret:
            raise HTTPException(status_code=400, detail="Missing required field: secret")
        service = CrossChainSettlementService(chain_id=settings.chain_id)
        return await service.settle(escrow_id, secret)
    except HTTPException:
        raise
    except Exception as e:
        _logger.error("Settle escrow failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Settle escrow failed: {e}") from e


@router.post("/{escrow_id}/refund", summary="Refund escrow")
@rate_limit(rate=10, per=60)
async def refund_escrow_route(escrow_id: str) -> dict[str, Any]:
    """Refund escrow after timeout."""
    if not settings.escrow_enabled:
        raise HTTPException(status_code=503, detail="Settlement not enabled")
    try:
        from ...cross_chain.settlement import CrossChainSettlementService

        service = CrossChainSettlementService(chain_id=settings.chain_id)
        return await service.refund(escrow_id)
    except HTTPException:
        raise
    except Exception as e:
        _logger.error("Refund escrow failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Refund escrow failed: {e}") from e


@router.get("/{escrow_id}", summary="Get escrow details")
@rate_limit(rate=100, per=60)
async def get_escrow_route(escrow_id: str) -> dict[str, Any]:
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
    except Exception as e:
        _logger.error("Get escrow failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Get escrow failed: {e}") from e


@router.get("/{escrow_id}/status", summary="Get escrow status")
@rate_limit(rate=100, per=60)
async def get_escrow_status_route(escrow_id: str) -> dict[str, Any]:
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
    except Exception as e:
        _logger.error("Get escrow status failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Get escrow status failed: {e}") from e


@router.get("/{escrow_id}/proofs", summary="Get proof chain")
@rate_limit(rate=100, per=60)
async def get_proof_chain_route(escrow_id: str) -> dict[str, Any]:
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
    except Exception as e:
        _logger.error("Get proof chain failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Get proof chain failed: {e}") from e


@router.post("/{escrow_id}/extend-timeout", summary="Extend escrow timeout")
@rate_limit(rate=10, per=60)
async def extend_timeout_route(escrow_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """Extend escrow timeout.

    Accepts JSON body ``{"extension_seconds": <int>}`` matching SettlementClient.
    """
    if not settings.escrow_enabled:
        raise HTTPException(status_code=503, detail="Settlement not enabled")
    try:
        from ...cross_chain.settlement import CrossChainSettlementService

        extension_seconds = body.get("extension_seconds", 0)
        if extension_seconds <= 0:
            raise HTTPException(status_code=400, detail="extension_seconds must be positive")
        service = CrossChainSettlementService(chain_id=settings.chain_id)
        return await service.extend_timeout(escrow_id, int(extension_seconds))
    except HTTPException:
        raise
    except Exception as e:
        _logger.error("Extend timeout failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Extend timeout failed: {e}") from e


@router.post("/{escrow_id}/dispute", summary="File a dispute for an escrow")
@rate_limit(rate=10, per=60)
async def file_escrow_dispute_route(escrow_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """File a dispute for an escrow, halting automatic timeout/refund."""
    if not settings.escrow_enabled:
        raise HTTPException(status_code=503, detail="Settlement not enabled")
    try:
        from sqlmodel import select

        from ...base_models import CrossChainEscrowRecord
        from ...database import session_scope

        reason = body.get("reason", "")
        evidence = body.get("evidence", "")
        with session_scope(settings.chain_id) as session:
            stmt = select(CrossChainEscrowRecord).where(CrossChainEscrowRecord.escrow_id == escrow_id)
            record = session.execute(stmt).scalars().first()
            if not record:
                raise HTTPException(status_code=404, detail="Escrow not found")
            record.status = "disputed"
            session.add(record)
            session.commit()
        return {"escrow_id": escrow_id, "status": "disputed", "reason": reason, "evidence": evidence}
    except HTTPException:
        raise
    except Exception as e:
        _logger.error("File dispute failed: %s", e)
        raise HTTPException(status_code=500, detail=f"File dispute failed: {e}") from e


@router.post("/{escrow_id}/resolve", summary="Resolve a dispute")
@rate_limit(rate=10, per=60)
async def resolve_escrow_dispute_route(escrow_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """Resolve a dispute for an escrow.

    Resolution is "complete" (release to seller) or "refund" (refund buyer).
    """
    if not settings.escrow_enabled:
        raise HTTPException(status_code=503, detail="Settlement not enabled")
    try:
        from sqlmodel import select

        from ...base_models import CrossChainEscrowRecord
        from ...database import session_scope

        resolution = body.get("resolution", "")
        if resolution not in ("complete", "refund"):
            raise HTTPException(status_code=400, detail="resolution must be 'complete' or 'refund'")
        final_status = "completed" if resolution == "complete" else "refunded"
        with session_scope(settings.chain_id) as session:
            stmt = select(CrossChainEscrowRecord).where(CrossChainEscrowRecord.escrow_id == escrow_id)
            record = session.execute(stmt).scalars().first()
            if not record:
                raise HTTPException(status_code=404, detail="Escrow not found")
            record.status = final_status
            session.add(record)
            session.commit()
        return {"escrow_id": escrow_id, "status": final_status, "resolution": resolution}
    except HTTPException:
        raise
    except Exception as e:
        _logger.error("Resolve dispute failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Resolve dispute failed: {e}") from e
