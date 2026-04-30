from datetime import datetime, UTC
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

# Distributed consensus endpoints
@router.post("/consensus/node/register")
async def register_consensus_node(node_data: Dict[str, Any]):
    """Register a node in the consensus network"""
    try:
        result = await distributed_consensus.register_node(node_data)
        return result
    except Exception as e:
        logger.error(f"Error registering consensus node: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/consensus/proposal/create")
async def create_consensus_proposal(proposal_data: Dict[str, Any]):
    """Create a new consensus proposal"""
    try:
        result = await distributed_consensus.create_proposal(proposal_data)
        return result
    except Exception as e:
        logger.error(f"Error creating consensus proposal: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/consensus/proposal/{proposal_id}/vote")
async def cast_consensus_vote(proposal_id: str, node_id: str, vote: bool):
    """Cast a vote for a proposal"""
    try:
        result = await distributed_consensus.cast_vote(proposal_id, node_id, vote)
        return result
    except Exception as e:
        logger.error(f"Error casting consensus vote: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/consensus/proposal/{proposal_id}")
async def get_proposal_status(proposal_id: str):
    """Get proposal status"""
    try:
        result = await distributed_consensus.get_proposal_status(proposal_id)
        return result
    except Exception as e:
        logger.error(f"Error getting proposal status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/consensus/algorithm")
async def set_consensus_algorithm(algorithm: str = Query(..., description="Consensus algorithm")):
    """Set the consensus algorithm"""
    try:
        result = await distributed_consensus.set_consensus_algorithm(algorithm)
        return result
    except Exception as e:
        logger.error(f"Error setting consensus algorithm: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/consensus/statistics")
async def get_consensus_statistics():
    """Get consensus statistics"""
    try:
        result = await distributed_consensus.get_consensus_statistics()
        return result
    except Exception as e:
        logger.error(f"Error getting consensus statistics: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/consensus/node/{node_id}/status")
async def update_node_status(node_id: str, is_active: bool):
    """Update node status"""
    try:
        result = await distributed_consensus.update_node_status(node_id, is_active)
        return result
    except Exception as e:
        logger.error(f"Error updating node status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Advanced features status endpoint
@router.get("/advanced-features/status")
async def get_advanced_features_status():
    """Get status of all advanced features"""
    try:
        learning_stats = await learning_system.get_learning_statistics()
        ai_stats = await ai_integration.get_ai_statistics()
        consensus_stats = await distributed_consensus.get_consensus_statistics()
        
        return {
            "status": "success",
            "timestamp": datetime.now(datetime.UTC).isoformat(),
            "features": {
                "realtime_learning": {
                    "status": "active",
                    "experiences": learning_stats.get("total_experiences", 0),
                    "learning_rate": learning_stats.get("learning_rate", 0.01),
                    "models": learning_stats.get("models_count", 0)
                },
                "advanced_ai": {
                    "status": "active",
                    "models": ai_stats.get("total_models", 0),
                    "neural_networks": ai_stats.get("total_neural_networks", 0),
                    "predictions": ai_stats.get("total_predictions", 0)
                },
                "distributed_consensus": {
                    "status": "active",
                    "nodes": consensus_stats.get("active_nodes", 0),
                    "proposals": consensus_stats.get("total_proposals", 0),
                    "success_rate": consensus_stats.get("success_rate", 0.0),
                    "algorithm": consensus_stats.get("current_algorithm", "majority_vote")
                }
            }
        }
    except Exception as e:
        logger.error(f"Error getting advanced features status: {e}")
        raise HTTPException(status_code=500, detail=str(e))
