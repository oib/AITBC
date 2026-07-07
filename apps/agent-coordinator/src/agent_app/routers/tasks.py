import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from aitbc.aitbc_logging import get_logger
from aitbc.rate_limiting import rate_limit

from .. import state
from ..config import settings
from ..models import TaskSubmission
from ..routing.load_balancer import TaskPriority

logger = get_logger(__name__)
router = APIRouter()


@router.post("/tasks/submit")
@rate_limit(rate=50, per=60)
async def submit_task(request_http: Request, request: TaskSubmission, background_tasks: BackgroundTasks) -> dict[str, Any]:
    """Submit a task for distribution"""
    try:
        if not state.task_distributor:
            raise HTTPException(status_code=503, detail="Task distributor not available")
        try:
            priority = TaskPriority(request.priority.lower())
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid priority: {request.priority}") from None

        # v0.6.5: resolve chain_id (defaults to DEFAULT_CHAIN_ID)
        chain_id = request.chain_id or settings.default_chain_id

        task_id = request.task_data.get("task_id", str(uuid.uuid4()))

        # v0.6.5: create payment escrow if payment provided and escrow enabled
        escrow_id: str | None = None
        if request.payment and settings.task_payment_escrow_enabled and state.payment_escrow:
            try:
                escrow = state.payment_escrow.create_escrow(
                    task_id=task_id,
                    chain_id=chain_id,
                    requester=request.payment.requester,
                    agent=request.payment.agent,
                    amount=request.payment.amount,
                    fee=request.payment.fee,
                    timeout=request.payment.timeout_seconds,
                )
                state.payment_escrow.lock(escrow.escrow_id)
                escrow_id = escrow.escrow_id
            except ValueError as e:
                raise HTTPException(status_code=400, detail=f"Escrow error: {e}") from None

        await state.task_distributor.submit_task(
            request.task_data,
            priority,
            request.requirements,
            chain_id=chain_id,
        )
        return {
            "status": "success",
            "message": "Task submitted successfully",
            "task_id": task_id,
            "chain_id": chain_id,
            "escrow_id": escrow_id,
            "priority": request.priority,
            "submitted_at": datetime.now(UTC).isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error submitting task: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/tasks/status")
@rate_limit(rate=200, per=60)
async def get_task_status(request: Request) -> dict[str, Any]:
    """Get task distribution statistics"""
    try:
        if not state.task_distributor:
            raise HTTPException(status_code=503, detail="Task distributor not available")
        stats = state.task_distributor.get_distribution_stats()
        return {"status": "success", "stats": stats, "timestamp": datetime.now(UTC).isoformat()}
    except Exception as e:
        logger.error("Error getting task status: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/tasks/queues")
@rate_limit(rate=200, per=60)
async def get_queue_sizes(request: Request) -> dict[str, Any]:
    """Get task queue sizes"""
    try:
        if not state.task_distributor:
            raise HTTPException(status_code=503, detail="Task distributor not available")
        queue_sizes = state.task_distributor.get_queue_sizes()
        return {"status": "success", "queue_sizes": queue_sizes, "timestamp": datetime.now(UTC).isoformat()}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting queue sizes: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/tasks/queues/{priority}/clear")
@rate_limit(rate=50, per=60)
async def clear_queue(request: Request, priority: str) -> dict[str, Any]:
    """Clear a priority queue"""
    try:
        if not state.task_distributor:
            raise HTTPException(status_code=503, detail="Task distributor not available")
        from ..routing.load_balancer import TaskPriority

        try:
            priority_enum = TaskPriority(priority)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid priority: {priority}") from None
        cleared_count = await state.task_distributor.clear_queue(priority_enum)
        return {
            "status": "success",
            "message": f"Cleared {cleared_count} tasks from {priority} queue",
            "priority": priority,
            "cleared_count": cleared_count,
            "timestamp": datetime.now(UTC).isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error clearing queue: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/tasks/queues/stats")
@rate_limit(rate=200, per=60)
async def get_queue_stats(request: Request) -> dict[str, Any]:
    """Get detailed queue statistics"""
    try:
        if not state.task_distributor:
            raise HTTPException(status_code=503, detail="Task distributor not available")
        queue_sizes = state.task_distributor.get_queue_sizes()
        distribution_stats = state.task_distributor.get_distribution_stats()
        return {
            "status": "success",
            "queue_sizes": queue_sizes,
            "distribution_stats": distribution_stats,
            "timestamp": datetime.now(UTC).isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting queue stats: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


# ---------------------------------------------------------------------------
# v0.6.5: Payment escrow endpoints
# ---------------------------------------------------------------------------


@router.get("/tasks/escrow/{escrow_id}")
@rate_limit(rate=200, per=60)
async def get_escrow_status(request: Request, escrow_id: str) -> dict[str, Any]:
    """Get payment escrow status by escrow ID."""
    if not state.payment_escrow:
        raise HTTPException(status_code=503, detail="Payment escrow not available")
    entry = state.payment_escrow.get_escrow(escrow_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Escrow not found")
    return {
        "status": "success",
        "escrow": {
            "escrow_id": entry.escrow_id,
            "task_id": entry.task_id,
            "chain_id": entry.chain_id,
            "requester": entry.requester,
            "agent": entry.agent,
            "amount": entry.amount,
            "fee": entry.fee,
            "escrow_status": entry.status.value,
            "tx_hash_lock": entry.tx_hash_lock,
            "tx_hash_release": entry.tx_hash_release,
            "tx_hash_refund": entry.tx_hash_refund,
            "created_at": entry.created_at,
            "locked_at": entry.locked_at,
            "released_at": entry.released_at,
            "expires_at": entry.expires_at,
        },
        "timestamp": datetime.now(UTC).isoformat(),
    }


@router.post("/tasks/{task_id}/complete")
@rate_limit(rate=50, per=60)
async def complete_task(request: Request, task_id: str) -> dict[str, Any]:
    """Mark a task as complete — releases escrow payment to agent (v0.6.5)."""
    if not state.payment_escrow:
        raise HTTPException(status_code=503, detail="Payment escrow not available")
    entry = state.payment_escrow.get_escrow_for_task(task_id)
    if not entry:
        raise HTTPException(status_code=404, detail="No escrow found for task")
    try:
        state.payment_escrow.release(entry.escrow_id)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from None
    return {
        "status": "success",
        "message": f"Task {task_id} completed, payment released",
        "task_id": task_id,
        "escrow_id": entry.escrow_id,
        "released_at": datetime.now(UTC).isoformat(),
    }


@router.post("/tasks/{task_id}/fail")
@rate_limit(rate=50, per=60)
async def fail_task(request: Request, task_id: str) -> dict[str, Any]:
    """Mark a task as failed — refunds escrow payment to requester (v0.6.5)."""
    if not state.payment_escrow:
        raise HTTPException(status_code=503, detail="Payment escrow not available")
    entry = state.payment_escrow.get_escrow_for_task(task_id)
    if not entry:
        raise HTTPException(status_code=404, detail="No escrow found for task")
    try:
        state.payment_escrow.refund(entry.escrow_id)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from None
    return {
        "status": "success",
        "message": f"Task {task_id} failed, payment refunded",
        "task_id": task_id,
        "escrow_id": entry.escrow_id,
        "refunded_at": datetime.now(UTC).isoformat(),
    }


@router.post("/tasks/escrow/expire-stale")
@rate_limit(rate=10, per=60)
async def expire_stale_escrows(request: Request) -> dict[str, Any]:
    """Expire and refund all stale escrows that have passed their timeout (v0.6.5)."""
    if not state.payment_escrow:
        raise HTTPException(status_code=503, detail="Payment escrow not available")
    expired = state.payment_escrow.expire_stale()
    return {
        "status": "success",
        "expired_count": len(expired),
        "escrow_ids": [e.escrow_id for e in expired],
        "timestamp": datetime.now(UTC).isoformat(),
    }
