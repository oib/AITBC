"""AI Services RPC endpoints for AITBC blockchain.

AI jobs are persisted in the on-chain database instead of in-memory storage.
No demo/seed jobs are created — the job list starts empty and is populated
by real submissions.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlmodel import select

from ..base_models import Transaction
from ..database import session_scope
from ..logger import get_logger
from ..metrics import metrics_registry
from .router import router

_logger = get_logger(__name__)


class AIJobRequest(BaseModel):
    """AI job submission request"""

    wallet_address: str = Field(..., description="Client wallet address")
    job_type: str = Field(..., description="Type of AI job (text, image, training, etc.)")
    prompt: str = Field(..., description="AI prompt or task description")
    payment: float = Field(..., ge=0, description="Payment in AIT")
    parameters: dict[str, Any] | None = Field(default=None, description="Additional job parameters")


class AIJobResponse(BaseModel):
    """AI job response"""

    job_id: str
    status: str
    wallet_address: str
    job_type: str
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
    """Submit a new AI job for processing"""
    try:
        metrics_registry.increment("rpc_ai_submit_total")

        # Generate unique job ID
        job_id = f"job_{uuid.uuid4().hex[:8]}"

        # Calculate estimated completion time
        estimated_completion = datetime.now(UTC) + timedelta(minutes=30)

        # Store as a transaction in the database
        tx_hash = "0x" + uuid.uuid4().hex
        chain_id = ""  # default chain

        with session_scope(chain_id) as session:
            tx = Transaction(
                chain_id=chain_id,
                tx_hash=tx_hash,
                sender=request.wallet_address,
                recipient="ai_service",
                payload={
                    "job_id": job_id,
                    "job_type": request.job_type,
                    "prompt": request.prompt,
                    "payment": request.payment,
                    "parameters": request.parameters or {},
                    "estimated_completion": estimated_completion.isoformat(),
                },
                type="ai_job",
                status="queued",
            )
            session.add(tx)
            session.commit()

        _logger.info("AI job submitted: %s by %s", job_id, request.wallet_address)

        return {
            "job_id": job_id,
            "status": "queued",
            "message": "AI job submitted successfully",
            "estimated_completion": estimated_completion.isoformat(),
            "wallet_address": request.wallet_address,
            "payment": request.payment,
            "job_type": request.job_type,
            "tx_hash": tx_hash,
        }

    except Exception as e:
        metrics_registry.increment("rpc_ai_submit_errors_total")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/ai/jobs", summary="List AI jobs", tags=["ai"])
async def ai_list_jobs(wallet_address: str | None = None, status: str | None = None) -> dict[str, Any]:
    """Get list of AI jobs, optionally filtered by wallet address or status"""
    try:
        metrics_registry.increment("rpc_ai_list_total")

        with session_scope("") as session:
            stmt = select(Transaction).where(Transaction.type == "ai_job")
            if wallet_address:
                stmt = stmt.where(Transaction.sender == wallet_address)
            if status:
                stmt = stmt.where(Transaction.status == status)
            stmt = stmt.order_by(Transaction.created_at.desc())
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
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/ai/job/{job_id}", summary="Get AI job by ID", tags=["ai"])
async def ai_get_job(job_id: str) -> dict[str, Any]:
    """Get a specific AI job by ID"""
    try:
        metrics_registry.increment("rpc_ai_get_total")

        with session_scope("") as session:
            # Search by job_id in payload — since job_id is stored in JSON payload,
            # we filter in Python after fetching ai_job transactions
            stmt = select(Transaction).where(Transaction.type == "ai_job")
            txs = session.exec(stmt).all()

            for tx in txs:
                payload = tx.payload or {}
                if payload.get("job_id") == job_id:
                    return {"job": _job_from_tx(tx), "found": True}

        raise HTTPException(status_code=404, detail="Job not found")

    except HTTPException:
        raise
    except Exception as e:
        metrics_registry.increment("rpc_ai_get_errors_total")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/ai/job/{job_id}/cancel", summary="Cancel AI job", tags=["ai"])
async def ai_cancel_job(job_id: str) -> dict[str, Any]:
    """Cancel an AI job"""
    try:
        metrics_registry.increment("rpc_ai_cancel_total")

        with session_scope("") as session:
            stmt = select(Transaction).where(Transaction.type == "ai_job")
            txs = session.exec(stmt).all()

            for tx in txs:
                payload = tx.payload or {}
                if payload.get("job_id") == job_id:
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
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/ai/stats", summary="AI service statistics", tags=["ai"])
async def ai_stats() -> dict[str, Any]:
    """Get AI service statistics"""
    try:
        metrics_registry.increment("rpc_ai_stats_total")

        with session_scope("") as session:
            stmt = select(Transaction).where(Transaction.type == "ai_job")
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
        raise HTTPException(status_code=500, detail=str(e)) from e
