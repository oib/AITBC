from datetime import datetime, timezone
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

# Advanced AI/ML endpoints
@router.post("/ai/learning/experience")
async def record_learning_experience(experience_data: Dict[str, Any]):
    """Record a learning experience for the AI system"""
    try:
        result = await learning_system.record_experience(experience_data)
        return result
    except Exception as e:
        logger.error(f"Error recording learning experience: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/ai/learning/statistics")
async def get_learning_statistics():
    """Get learning system statistics"""
    try:
        result = await learning_system.get_learning_statistics()
        return result
    except Exception as e:
        logger.error(f"Error getting learning statistics: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/ai/learning/predict")
async def predict_performance(context: Dict[str, Any], action: str = Query(...)):
    """Predict performance for a given action"""
    try:
        result = await learning_system.predict_performance(context, action)
        return result
    except Exception as e:
        logger.error(f"Error predicting performance: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/ai/learning/recommend")
async def recommend_action(context: Dict[str, Any], available_actions: List[str]):
    """Get AI-recommended action"""
    try:
        result = await learning_system.recommend_action(context, available_actions)
        return result
    except Exception as e:
        logger.error(f"Error recommending action: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/ai/neural-network/create")
async def create_neural_network(config: Dict[str, Any]):
    """Create a new neural network"""
    try:
        result = await ai_integration.create_neural_network(config)
        return result
    except Exception as e:
        logger.error(f"Error creating neural network: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/ai/neural-network/{network_id}/train")
async def train_neural_network(network_id: str, training_data: List[Dict[str, Any]], epochs: int = 100):
    """Train a neural network"""
    try:
        result = await ai_integration.train_neural_network(network_id, training_data, epochs)
        return result
    except Exception as e:
        logger.error(f"Error training neural network: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/ai/neural-network/{network_id}/predict")
async def predict_with_neural_network(network_id: str, features: List[float]):
    """Make prediction with neural network"""
    try:
        result = await ai_integration.predict_with_neural_network(network_id, features)
        return result
    except Exception as e:
        logger.error(f"Error predicting with neural network: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/ai/ml-model/create")
async def create_ml_model(config: Dict[str, Any]):
    """Create a new ML model"""
    try:
        result = await ai_integration.create_ml_model(config)
        return result
    except Exception as e:
        logger.error(f"Error creating ML model: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/ai/ml-model/{model_id}/train")
async def train_ml_model(model_id: str, training_data: List[Dict[str, Any]]):
    """Train an ML model"""
    try:
        result = await ai_integration.train_ml_model(model_id, training_data)
        return result
    except Exception as e:
        logger.error(f"Error training ML model: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/ai/ml-model/{model_id}/predict")
async def predict_with_ml_model(model_id: str, features: List[float]):
    """Make prediction with ML model"""
    try:
        result = await ai_integration.predict_with_ml_model(model_id, features)
        return result
    except Exception as e:
        logger.error(f"Error predicting with ML model: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/ai/statistics")
async def get_ai_statistics():
    """Get comprehensive AI/ML statistics"""
    try:
        result = await ai_integration.get_ai_statistics()
        return result
    except Exception as e:
        logger.error(f"Error getting AI statistics: {e}")
        raise HTTPException(status_code=500, detail=str(e))
