"""AI Services RPC endpoints for AITBC blockchain.

AI jobs are persisted in the on-chain database instead of in-memory storage.
No demo/seed jobs are created — the job list starts empty and is populated
by real submissions.
"""

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlmodel import func as sql_func
from sqlmodel import select

from aitbc.utils import ait_to_seconds

from ..base_models import Transaction, address_spellings
from ..database import session_scope
from ..logger import get_logger
from ..metrics import metrics_registry
from .router import router

_logger = get_logger(__name__)

# An AI job is a payment to the AI service account, so it is submitted as an
# ordinary chain transaction and the PoA proposer includes it in a block.
AI_SERVICE_RECIPIENT = "ai_service"

# The proposer upper-cases tx["type"] when it writes the confirmed Transaction
# row (see consensus/poa.py), so mined jobs are stored as "AI_JOB". Rows written
# before AI jobs reached the mempool carry the lowercase spelling; both are
# matched so pre-existing jobs stay visible.
AI_JOB_TX_TYPE = "AI_JOB"
AI_JOB_TX_TYPES = (AI_JOB_TX_TYPE, "ai_job")


class AIJobRequest(BaseModel):
    """AI job submission request"""

    wallet_address: str = Field(..., description="Client wallet address")
    job_type: str = Field(..., description="Type of AI job (text, image, training, etc.)")
    prompt: str = Field(..., description="AI prompt or task description")
    # not-money: wire format. This value goes into tx_data["payload"], which is
    # json.dumps'd and keccak-hashed for signature verification and for the tx hash.
    # Decimal is not JSON-serializable, and even with an encoder "0.5" != 0.5 would
    # invalidate every signature already issued. Changing it is a hard fork -- see
    # docs/architecture/money-types-and-the-signature-boundary.md.
    payment: float = Field(..., ge=0, description="Payment in AIT")
    parameters: dict[str, Any] | None = Field(default=None, description="Additional job parameters")
    nonce: int = Field(default=0, ge=0, description="Sender account nonce")
    fee: int = Field(default=36, ge=0, description="Transaction fee in compute-seconds (1 AIT = 3600)")
    signature: str = Field(..., description="secp256k1 signature over the job transaction, signed by wallet_address")


class AIJobResponse(BaseModel):
    """AI job response"""

    job_id: str
    status: str
    wallet_address: str
    job_type: str
    # not-money: echoes the request field above, whose wire type is fixed by the
    # transaction signature. Changing one without the other would be worse than either.
    payment: float
    created_at: datetime
    estimated_completion: datetime | None = None
    result: dict[str, Any] | None = None


def _job_from_tx(tx: Transaction) -> dict[str, Any]:
    """Convert a Transaction row with type='ai_job' to a job dict."""
    payload = tx.payload or {}
    return {
        "job_id": payload.get("job_id", tx.tx_hash),
        "wallet_address": tx.sender,
        "job_type": payload.get("job_type", "unknown"),
        "prompt": payload.get("prompt", ""),
        "payment": payload.get("payment", 0.0),
        "parameters": payload.get("parameters", {}),
        "status": tx.status,
        "created_at": tx.created_at.isoformat() if tx.created_at else None,
        "estimated_completion": payload.get("estimated_completion"),
        "result": payload.get("result"),
        "tx_hash": tx.tx_hash,
        "block_height": tx.block_height,
    }


@router.post("/ai/submit", summary="Submit AI job", tags=["ai"])
async def ai_submit_job(request: AIJobRequest) -> dict[str, Any]:
    """Submit a new AI job to the mempool.

    The job is an ordinary chain transaction paying ``AI_SERVICE_RECIPIENT``, so
    the PoA proposer includes it in a block like any other. It appears in the job
    endpoints once mined; until then it is pending in the mempool and visible via
    ``/mempool``. Its ``job_id`` is the transaction hash.
    """
    from ..mempool import get_mempool
    from .transactions import _validate_transaction_admission
    from .utils import get_chain_id, normalize_transaction_data, verify_transaction_signature

    try:
        metrics_registry.increment("rpc_ai_submit_total")

        chain_id = get_chain_id()
        mempool = get_mempool()

        # Every field here is client-supplied: the signature covers the whole
        # transaction, so nothing the server invents can be part of it. chain_id
        # is included so a job signed for one chain cannot be replayed on
        # another (same rule as submit_transaction).
        tx_data: dict[str, Any] = {
            "from": request.wallet_address,
            "to": AI_SERVICE_RECIPIENT,
            "amount": ait_to_seconds(request.payment),
            "fee": request.fee,
            "nonce": request.nonce,
            "type": AI_JOB_TX_TYPE,
            "payload": {
                "job_type": request.job_type,
                "prompt": request.prompt,
                "payment": request.payment,
                "parameters": request.parameters or {},
            },
            "chain_id": chain_id,
            "signature": request.signature,
        }

        # The job debits the sender's balance, so it has to be signed by them.
        if not verify_transaction_signature(tx_data, request.signature, request.wallet_address):
            raise HTTPException(status_code=403, detail="Invalid transaction signature")

        tx_data = normalize_transaction_data(tx_data, chain_id)
        _validate_transaction_admission(tx_data, mempool)

        tx_hash = mempool.add(tx_data, chain_id=chain_id)

        _logger.info("AI job submitted to mempool: tx %s by %s", tx_hash, request.wallet_address)

        return {
            "job_id": tx_hash,
            "status": "pending",
            "message": "AI job submitted to mempool, pending inclusion in a block",
            "wallet_address": request.wallet_address,
            "payment": request.payment,
            "job_type": request.job_type,
            "tx_hash": tx_hash,
        }

    except HTTPException:
        raise
    except ValueError as e:
        # Rejected before admission: malformed amount/fee/nonce, unknown sender,
        # insufficient balance, wrong nonce, or unsupported chain. These are
        # client errors, and failing here is the point — the previous version
        # accepted everything and dropped it silently.
        metrics_registry.increment("rpc_ai_submit_errors_total")
        _logger.warning("AI job rejected: %s", e)
        raise HTTPException(status_code=400, detail=f"Failed to submit AI job: {e}") from e
    except Exception as e:
        metrics_registry.increment("rpc_ai_submit_errors_total")
        logging.getLogger(__name__).exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/ai/jobs", summary="List AI jobs", tags=["ai"])
async def ai_list_jobs(wallet_address: str | None = None, status: str | None = None) -> dict[str, Any]:
    """Get list of AI jobs, optionally filtered by wallet address or status"""
    try:
        metrics_registry.increment("rpc_ai_list_total")

        with session_scope("") as session:
            stmt = select(Transaction).where(Transaction.type.in_(AI_JOB_TX_TYPES))  # type: ignore[attr-defined]
            if wallet_address:
                # Verbatim column, so match every spelling of the account (V23-65).
                stmt = stmt.where(sql_func.lower(Transaction.sender).in_(address_spellings(wallet_address)))
            if status:
                stmt = stmt.where(Transaction.status == status)
            stmt = stmt.order_by(Transaction.created_at.desc())  # type: ignore[attr-defined]
            txs = session.exec(stmt).all()

            jobs = [_job_from_tx(tx) for tx in txs]

        return {
            "jobs": jobs,
            "total": len(jobs),
            "filters": {"wallet_address": wallet_address, "status": status},
            "timestamp": datetime.now(UTC).isoformat(),
        }

    except Exception as e:
        metrics_registry.increment("rpc_ai_list_errors_total")
        logging.getLogger(__name__).exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/ai/job/{job_id}", summary="Get AI job by ID", tags=["ai"])
async def ai_get_job(job_id: str) -> dict[str, Any]:
    """Get a specific AI job by ID"""
    try:
        metrics_registry.increment("rpc_ai_get_total")

        with session_scope("") as session:
            # Search by job_id in payload — since job_id is stored in JSON payload,
            # we filter in Python after fetching ai_job transactions
            stmt = select(Transaction).where(Transaction.type.in_(AI_JOB_TX_TYPES))  # type: ignore[attr-defined]
            txs = session.exec(stmt).all()

            for tx in txs:
                payload = tx.payload or {}
                # Jobs submitted through the mempool are identified by their tx
                # hash; older rows carry an explicit job_id in the payload. Match
                # the same identity _job_from_tx reports.
                if payload.get("job_id", tx.tx_hash) == job_id:
                    return {"job": _job_from_tx(tx), "found": True}

        raise HTTPException(status_code=404, detail="Job not found")

    except HTTPException:
        raise
    except Exception as e:
        metrics_registry.increment("rpc_ai_get_errors_total")
        logging.getLogger(__name__).exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/ai/job/{job_id}/cancel", summary="Cancel AI job", tags=["ai"])
async def ai_cancel_job(job_id: str) -> dict[str, Any]:
    """Cancel an AI job"""
    try:
        metrics_registry.increment("rpc_ai_cancel_total")

        with session_scope("") as session:
            stmt = select(Transaction).where(Transaction.type.in_(AI_JOB_TX_TYPES))  # type: ignore[attr-defined]
            txs = session.exec(stmt).all()

            for tx in txs:
                payload = tx.payload or {}
                # Jobs submitted through the mempool are identified by their tx
                # hash; older rows carry an explicit job_id in the payload. Match
                # the same identity _job_from_tx reports.
                if payload.get("job_id", tx.tx_hash) == job_id:
                    current_status = tx.status
                    if current_status in ["completed", "cancelled"]:
                        raise HTTPException(status_code=400, detail=f"Cannot cancel job with status: {current_status}")

                    tx.status = "cancelled"
                    tx.payload = {**payload, "cancelled_at": datetime.now(UTC).isoformat()}
                    session.add(tx)
                    session.commit()

                    return {"job_id": job_id, "status": "cancelled", "message": "AI job cancelled successfully"}

        raise HTTPException(status_code=404, detail="Job not found")

    except HTTPException:
        raise
    except Exception as e:
        metrics_registry.increment("rpc_ai_cancel_errors_total")
        logging.getLogger(__name__).exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/ai/stats", summary="AI service statistics", tags=["ai"])
async def ai_stats() -> dict[str, Any]:
    """Get AI service statistics"""
    try:
        metrics_registry.increment("rpc_ai_stats_total")

        with session_scope("") as session:
            stmt = select(Transaction).where(Transaction.type.in_(AI_JOB_TX_TYPES))  # type: ignore[attr-defined]
            txs = session.exec(stmt).all()

            total_jobs = len(txs)
            status_counts: dict[str, int] = {}
            type_counts: dict[str, int] = {}
            total_revenue = 0.0

            for tx in txs:
                payload = tx.payload or {}
                # Count by status
                status = tx.status or "unknown"
                status_counts[status] = status_counts.get(status, 0) + 1

                # Count by type
                job_type = payload.get("job_type", "unknown")
                type_counts[job_type] = type_counts.get(job_type, 0) + 1

                # Sum revenue for completed jobs
                if status == "completed":
                    total_revenue += payload.get("payment", 0.0)

        return {
            "total_jobs": total_jobs,
            "status_breakdown": status_counts,
            "type_breakdown": type_counts,
            "total_revenue": total_revenue,
            "average_payment": total_revenue / max(1, status_counts.get("completed", 0)),
            "timestamp": datetime.now(UTC).isoformat(),
        }

    except Exception as e:
        metrics_registry.increment("rpc_ai_stats_errors_total")
        logging.getLogger(__name__).exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e
