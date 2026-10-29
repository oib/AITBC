"""Shared transfer-ledger routes — ``/bridge/ledger/*`` (issue #696, decision A).

The ledger is an HTTP surface hosted inside the designated host's
``aitbc-blockchain-rpc`` process — a router mount, not a new unit. It
stores ``cross_chain_transfer`` rows in this host's own chain store for
BOTH chain-pair directions; sharing happens over this surface, not the
database. Remote rpcs keep their local row as a write-through cache and
poll ``GET /pending`` for the relayer worklist.

Auth: the existing rpc API key (``BLOCKCHAIN_RPC_API_KEY``, ``X-API-Key``)
via ``verify_rpc_api_key`` — the same dependency the escrow routes use.
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from aitbc.rate_limiting import rate_limit

from ...logger import get_logger
from ..escrow_routes import verify_rpc_api_key

_logger = get_logger(__name__)

router = APIRouter(prefix="/bridge/ledger", tags=["bridge-ledger"], dependencies=[Depends(verify_rpc_api_key)])

# Monotonic lifecycle ranks. pending/locked are interchangeable intake
# states; confirmed is relayed; completed/failed/refunded are terminal.
# A different-status writeback must strictly increase the rank — the same
# status is an idempotent no-op, anything else 400s.
_STATUS_RANK = {
    "pending": 0,
    "locked": 0,
    "confirmed": 1,
    "completed": 2,
    "failed": 2,
    "refunded": 2,
}


class LedgerRegisterRequest(BaseModel):
    """Intake upsert — the CrossChainTransfer record fields."""

    transfer_id: str = Field(..., min_length=1)
    source_chain: str = Field(..., min_length=1)
    target_chain: str = Field(..., min_length=1)
    sender: str = Field(..., min_length=1)
    recipient: str = Field(..., min_length=1)
    amount: int = Field(..., ge=0)
    asset: str = Field(default="native")
    status: str = Field(default="pending")
    source_tx_hash: str | None = None
    lock_time: datetime | None = None
    release_amount: int | None = None


class LedgerStatusRequest(BaseModel):
    """Relayer writeback — monotonic status plus proof/release anchors."""

    status: str = Field(..., min_length=1)
    target_tx_hash: str | None = None
    proof_hash: str | None = None
    confirm_time: datetime | None = None


def _row(record: Any) -> dict[str, Any]:
    return {
        "transfer_id": record.transfer_id,
        "source_chain": record.source_chain,
        "target_chain": record.target_chain,
        "sender": record.sender,
        "recipient": record.recipient,
        "amount": record.amount,
        "release_amount": record.release_amount,
        "asset": record.asset,
        "status": record.status,
        "source_tx_hash": record.source_tx_hash,
        "target_tx_hash": record.target_tx_hash,
        "proof_hash": record.proof_hash,
        "lock_time": record.lock_time.isoformat() if record.lock_time else None,
        "confirm_time": record.confirm_time.isoformat() if record.confirm_time else None,
    }


@router.post("/register", summary="Register a pending transfer (idempotent upsert)")
@rate_limit(rate=60, per=60)
async def ledger_register_route(request: Request, body: LedgerRegisterRequest) -> dict[str, Any]:
    """Upsert the intake transfer row keyed on ``transfer_id``.

    A re-register of an existing row returns it unchanged — the service
    never regresses a status the relayer already advanced.
    """
    try:
        from ...base_models import CrossChainTransfer
        from ...database import session_scope

        with session_scope() as session:
            record = session.get(CrossChainTransfer, body.transfer_id)
            created = False
            if record is None:
                record = CrossChainTransfer(
                    transfer_id=body.transfer_id,
                    source_chain=body.source_chain,
                    target_chain=body.target_chain,
                    sender=body.sender,
                    recipient=body.recipient,
                    amount=body.amount,
                    asset=body.asset,
                    status=body.status if body.status in _STATUS_RANK else "pending",
                    source_tx_hash=body.source_tx_hash,
                    lock_time=body.lock_time,
                    release_amount=body.release_amount,
                )
                session.add(record)
                session.commit()
                session.refresh(record)
                created = True
            return {"transfer": _row(record), "created": created}
    except HTTPException:
        raise
    except Exception as e:
        _logger.exception("Ledger register failed for %s: %s", body.transfer_id, e)
        raise HTTPException(status_code=503, detail="Ledger store unavailable") from e


@router.get("/pending", summary="Relayer worklist for a target chain")
@rate_limit(rate=120, per=60)
async def ledger_pending_route(request: Request, target_chain: str) -> dict[str, Any]:
    """Rows whose ``target_chain`` matches and status is ``pending``.

    This replaces the relayer's local ``status='pending'`` scan.
    """
    try:
        from sqlmodel import select

        from ...base_models import CrossChainTransfer
        from ...database import session_scope

        with session_scope() as session:
            rows = session.exec(
                select(CrossChainTransfer).where(
                    CrossChainTransfer.target_chain == target_chain,
                    CrossChainTransfer.status == "pending",
                )
            ).all()
        transfers = [_row(r) for r in rows]
        return {"transfers": transfers, "count": len(transfers)}
    except HTTPException:
        raise
    except Exception as e:
        _logger.exception("Ledger pending poll failed for target %s: %s", target_chain, e)
        raise HTTPException(status_code=503, detail="Ledger store unavailable") from e


@router.post("/{transfer_id}/status", summary="Monotonic status writeback")
@rate_limit(rate=60, per=60)
async def ledger_status_route(request: Request, transfer_id: str, body: LedgerStatusRequest) -> dict[str, Any]:
    """Advance a row's status — pending→confirmed→completed (or terminal).

    Same-status writebacks are idempotent no-ops; any transition that is
    not strictly monotonic is rejected with 400.
    """
    new_status = body.status
    if new_status not in _STATUS_RANK:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status '{new_status}' (allowed: {sorted(_STATUS_RANK)})",
        )
    try:
        from ...base_models import CrossChainTransfer
        from ...database import session_scope

        with session_scope() as session:
            record = session.get(CrossChainTransfer, transfer_id)
            if record is None:
                raise HTTPException(status_code=404, detail=f"Transfer not found: {transfer_id}")
            if record.status != new_status and _STATUS_RANK[new_status] <= _STATUS_RANK.get(record.status, 0):
                raise HTTPException(
                    status_code=400,
                    detail=(f"Out-of-order status transition: {record.status} -> {new_status} (writeback is monotonic only)"),
                )
            record.status = new_status
            if body.target_tx_hash is not None:
                record.target_tx_hash = body.target_tx_hash
            if body.proof_hash is not None:
                record.proof_hash = body.proof_hash
            if body.confirm_time is not None:
                record.confirm_time = body.confirm_time
            session.add(record)
            session.commit()
            session.refresh(record)
            return {"transfer": _row(record)}
    except HTTPException:
        raise
    except Exception as e:
        _logger.exception("Ledger status writeback failed for %s: %s", transfer_id, e)
        raise HTTPException(status_code=503, detail="Ledger store unavailable") from e


@router.get("/{transfer_id}", summary="Read a single transfer row")
@rate_limit(rate=120, per=60)
async def ledger_read_route(request: Request, transfer_id: str) -> dict[str, Any]:
    """Single-row read — the transplant-script replacement."""
    try:
        from ...base_models import CrossChainTransfer
        from ...database import session_scope

        with session_scope() as session:
            record = session.get(CrossChainTransfer, transfer_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"Transfer not found: {transfer_id}")
        return {"transfer": _row(record)}
    except HTTPException:
        raise
    except Exception as e:
        _logger.exception("Ledger read failed for %s: %s", transfer_id, e)
        raise HTTPException(status_code=503, detail="Ledger store unavailable") from e
