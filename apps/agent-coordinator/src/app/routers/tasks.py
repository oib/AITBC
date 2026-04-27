from datetime import datetime
import uuid
from typing import Any, Dict, List, Optional

from aitbc import get_logger
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response
from fastapi.responses import JSONResponse

from .. import state
from ..auth.jwt_handler import api_key_manager, jwt_handler
from ..auth.middleware import get_current_user, require_role
from ..auth.permissions import Permission, Role, permission_manager
from ..ai.advanced_ai import ai_integration
from ..ai.realtime_learning import learning_system
from ..consensus.distributed_consensus import distributed_consensus
from ..models import AgentRegistrationRequest, AgentStatusUpdate, MessageRequest, TaskSubmission
from ..monitoring.alerting import alert_manager
from ..monitoring.prometheus_metrics import metrics_registry, performance_monitor
from ..protocols.communication import MessageType, create_protocol
from ..protocols.message_types import create_task_message
from ..routing.agent_discovery import create_agent_info
from ..routing.load_balancer import LoadBalancingStrategy, TaskPriority

logger = get_logger(__name__)
router = APIRouter()

# Submit task
@router.post("/tasks/submit")
async def submit_task(request: TaskSubmission, background_tasks: BackgroundTasks):
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
            "submitted_at": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error submitting task: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Get task status
@router.get("/tasks/status")
async def get_task_status():
    """Get task distribution statistics"""
    try:
        if not state.task_distributor:
            raise HTTPException(status_code=503, detail="Task distributor not available")
        
        stats = state.task_distributor.get_distribution_stats()
        
        return {
            "status": "success",
            "stats": stats,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting task status: {e}")
        raise HTTPException(status_code=500, detail=str(e))
