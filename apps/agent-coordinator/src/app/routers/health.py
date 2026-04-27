from datetime import datetime
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

# Health check endpoint
@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "agent-coordinator",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0"
    }

# Root endpoint
@router.get("/")
async def root():
    """Root endpoint with service information"""
    return {
        "service": "AITBC Agent Coordinator",
        "description": "Advanced multi-agent coordination and management system",
        "version": "1.0.0",
        "endpoints": [
            "/health",
            "/agents/register",
            "/agents/discover",
            "/agents/{agent_id}",
            "/agents/{agent_id}/status",
            "/tasks/submit",
            "/tasks/status",
            "/messages/send",
            "/load-balancer/stats",
            "/registry/stats"
        ]
    }
