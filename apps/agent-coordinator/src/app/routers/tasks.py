# mypy: ignore-errors
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from aitbc import get_logger
from aitbc.rate_limiting import rate_limit

from .. import state
from ..models import TaskSubmission
from ..routing.load_balancer import TaskPriority

logger = get_logger(__name__)
router = APIRouter()

# Submit task
@router.post("/tasks/submit")
@rate_limit(rate=50, per=60)
async def submit_task(
    request_http: Request, request: TaskSubmission, background_tasks: BackgroundTasks
):
    """Submit a task for distribution"""
    try:
        if not state.task_distributor:
            raise HTTPException(status_code=503, detail="Task distributor not available")

        # Convert priority string to enum
        try:
            priority = TaskPriority(request.priority.lower())
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid priority: {request.priority}")

        # Submit task
        await state.task_distributor.submit_task(
            request.task_data,
            priority,
            request.requirements
        )

        return {
            "status": "success",
            "message": "Task submitted successfully",
            "task_id": request.task_data.get("task_id", str(uuid.uuid4())),
            "priority": request.priority,
            "submitted_at": datetime.now(UTC).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error submitting task: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Get task status
@router.get("/tasks/status")
@rate_limit(rate=200, per=60)
async def get_task_status(
    request: Request
):
    """Get task distribution statistics"""
    try:
        if not state.task_distributor:
            raise HTTPException(status_code=503, detail="Task distributor not available")

        stats = state.task_distributor.get_distribution_stats()

        return {
            "status": "success",
            "stats": stats,
            "timestamp": datetime.now(UTC).isoformat()
        }

    except Exception as e:
        logger.error(f"Error getting task status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Task queue management
@router.get("/tasks/queues")
@rate_limit(rate=200, per=60)
async def get_queue_sizes(
    request: Request
):
    """Get task queue sizes"""
    try:
        if not state.task_distributor:
            raise HTTPException(status_code=503, detail="Task distributor not available")

        queue_sizes = state.task_distributor.get_queue_sizes()

        return {
            "status": "success",
            "queue_sizes": queue_sizes,
            "timestamp": datetime.now(UTC).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting queue sizes: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/tasks/queues/{priority}/clear")
@rate_limit(rate=50, per=60)
async def clear_queue(
    request: Request, priority: str
):
    """Clear a priority queue"""
    try:
        if not state.task_distributor:
            raise HTTPException(status_code=503, detail="Task distributor not available")

        from ..routing.load_balancer import TaskPriority

        try:
            priority_enum = TaskPriority(priority)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid priority: {priority}")

        cleared_count = await state.task_distributor.clear_queue(priority_enum)

        return {
            "status": "success",
            "message": f"Cleared {cleared_count} tasks from {priority} queue",
            "priority": priority,
            "cleared_count": cleared_count,
            "timestamp": datetime.now(UTC).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error clearing queue: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/tasks/queues/stats")
@rate_limit(rate=200, per=60)
async def get_queue_stats(
    request: Request
):
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
            "timestamp": datetime.now(UTC).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting queue stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))
