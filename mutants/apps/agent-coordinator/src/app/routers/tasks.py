import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from aitbc import get_logger
from aitbc.rate_limiting import rate_limit

from .. import state
from ..models import TaskSubmission
from ..routing.load_balancer import TaskPriority

logger = get_logger(__name__)
router = APIRouter()


from mutmut.mutation.trampoline import wrap_in_trampoline as _mutmut_mutated, MutantDict


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
        await state.task_distributor.submit_task(request.task_data, priority, request.requirements)
        return {
            "status": "success",
            "message": "Task submitted successfully",
            "task_id": request.task_data.get("task_id", str(uuid.uuid4())),
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
