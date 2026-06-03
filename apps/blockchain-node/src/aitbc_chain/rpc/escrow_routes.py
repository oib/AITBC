"""
Escrow RPC endpoints for the blockchain node.
Provides create/release/refund/get endpoints backed by EscrowManager and Escrow DB model.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException

from ..contracts.escrow import get_escrow_manager
from ..database import session_scope
from ..logger import get_logger
from ..models import Escrow

_logger = get_logger(__name__)

router = APIRouter(tags=["escrow"])


@router.post("/escrow/create", summary="Create escrow for a job")
async def create_escrow(body: dict[str, Any]) -> dict[str, Any]:
    """Create a new escrow contract locking buyer funds until job completion."""
    job_id = body.get("job_id")
    buyer = body.get("buyer")
    provider = body.get("provider")
    amount = body.get("amount")

    if not all([job_id, buyer, provider, amount is not None]):
        raise HTTPException(status_code=400, detail="job_id, buyer, provider, and amount are required")

    mgr = get_escrow_manager()
    if mgr is None:
        raise HTTPException(status_code=503, detail="EscrowManager not initialised")

    try:
        amount_dec = Decimal(str(amount))
    except Exception:
        raise HTTPException(status_code=400, detail=f"Invalid amount: {amount}")

    success, message, contract_id = await mgr.create_contract(
        job_id=job_id,
        client_address=buyer,
        agent_address=provider,
        amount=amount_dec,
    )

    if not success:
        raise HTTPException(status_code=400, detail=message)

    # Persist to Escrow DB table
    try:
        with session_scope() as session:
            escrow_record = Escrow(
                job_id=job_id,
                buyer=buyer,
                provider=provider,
                amount=int(amount_dec),
            )
            session.add(escrow_record)
            session.commit()
    except Exception as e:
        _logger.warning(f"Failed to persist escrow to DB (in-memory only): {e}")

    _logger.info(f"Escrow created: contract_id={contract_id} job_id={job_id} amount={amount}")
    return {
        "success": True,
        "contract_id": contract_id,
        "job_id": job_id,
        "buyer": buyer,
        "provider": provider,
        "amount": str(amount_dec),
        "message": message,
    }


@router.post("/escrow/{job_id}/release", summary="Release escrow to provider")
async def release_escrow(job_id: str) -> dict[str, Any]:
    """Release locked funds to the provider after job completion."""
    mgr = get_escrow_manager()
    if mgr is None:
        raise HTTPException(status_code=503, detail="EscrowManager not initialised")

    # Find contract by job_id
    contract_id = _find_contract_id(mgr, job_id)
    if contract_id is None:
        raise HTTPException(status_code=404, detail=f"No escrow contract found for job_id={job_id}")

    # Mark job completed first
    contract = mgr.escrow_contracts.get(contract_id)
    if contract:
        for ms in contract.milestones:
            ms["completed"] = True
            ms["verified"] = True
        from ..contracts.escrow import EscrowState
        contract.state = EscrowState.JOB_COMPLETED

    success, message = await mgr.release_full_payment(contract_id)
    if not success:
        raise HTTPException(status_code=400, detail=message)

    # Update released_at in DB
    try:
        with session_scope() as session:
            record = session.get(Escrow, job_id)
            if record:
                record.released_at = datetime.now(UTC)
                session.commit()
    except Exception as e:
        _logger.warning(f"Failed to update released_at in DB: {e}")

    _logger.info(f"Escrow released: contract_id={contract_id} job_id={job_id}")
    return {
        "success": True,
        "contract_id": contract_id,
        "job_id": job_id,
        "message": message,
        "released_at": datetime.now(UTC).isoformat(),
    }


@router.post("/escrow/{job_id}/refund", summary="Refund escrow to buyer")
async def refund_escrow(job_id: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    """Refund locked funds back to the buyer."""
    mgr = get_escrow_manager()
    if mgr is None:
        raise HTTPException(status_code=503, detail="EscrowManager not initialised")

    contract_id = _find_contract_id(mgr, job_id)
    if contract_id is None:
        raise HTTPException(status_code=404, detail=f"No escrow contract found for job_id={job_id}")

    reason = (body or {}).get("reason", "buyer_requested")
    success, message = await mgr.refund_contract(contract_id, reason)
    if not success:
        raise HTTPException(status_code=400, detail=message)

    _logger.info(f"Escrow refunded: contract_id={contract_id} job_id={job_id}")
    return {
        "success": True,
        "contract_id": contract_id,
        "job_id": job_id,
        "message": message,
    }


@router.get("/escrow/{job_id}", summary="Get escrow state")
async def get_escrow(job_id: str) -> dict[str, Any]:
    """Get current escrow state for a job."""
    mgr = get_escrow_manager()

    # Try DB first
    db_record: Escrow | None = None
    try:
        with session_scope() as session:
            db_record = session.get(Escrow, job_id)
    except Exception as e:
        _logger.warning(f"Failed to query Escrow DB: {e}")

    if mgr is not None:
        contract_id = _find_contract_id(mgr, job_id)
        if contract_id:
            contract = mgr.escrow_contracts.get(contract_id)
            if contract:
                return {
                    "job_id": job_id,
                    "contract_id": contract_id,
                    "state": contract.state.value,
                    "buyer": contract.client_address,
                    "provider": contract.agent_address,
                    "amount": str(contract.amount),
                    "released_amount": str(contract.released_amount),
                    "refunded_amount": str(contract.refunded_amount),
                    "created_at": db_record.created_at.isoformat() if db_record else None,
                    "released_at": db_record.released_at.isoformat() if db_record and db_record.released_at else None,
                }

    if db_record:
        return {
            "job_id": job_id,
            "contract_id": None,
            "state": "released" if db_record.released_at else "funded",
            "buyer": db_record.buyer,
            "provider": db_record.provider,
            "amount": str(db_record.amount),
            "released_amount": str(db_record.amount) if db_record.released_at else "0",
            "refunded_amount": "0",
            "created_at": db_record.created_at.isoformat(),
            "released_at": db_record.released_at.isoformat() if db_record.released_at else None,
        }

    raise HTTPException(status_code=404, detail=f"No escrow found for job_id={job_id}")


def _find_contract_id(mgr: Any, job_id: str) -> str | None:
    """Find contract_id by job_id in EscrowManager."""
    for cid, contract in mgr.escrow_contracts.items():
        if contract.job_id == job_id:
            return cid
    return None
