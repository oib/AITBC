from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from aitbc import get_logger
from aitbc.rate_limiting import rate_limit

from ..ai.advanced_ai import ai_integration
from ..ai.realtime_learning import learning_system

logger = get_logger(__name__)
router = APIRouter()


@router.post("/ai/learning/experience")
@rate_limit(rate=50, per=60)
async def record_learning_experience(request: Request, experience_data: dict[str, Any]) -> dict[str, Any]:
    """Record a learning experience for the AI system"""
    try:
        result = await learning_system.record_experience(experience_data)
        return result
    except Exception as e:
        logger.error("Error recording learning experience: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/ai/learning/statistics")
@rate_limit(rate=200, per=60)
async def get_learning_statistics(request: Request) -> dict[str, Any]:
    """Get learning system statistics"""
    try:
        result = await learning_system.get_learning_statistics()
        return result
    except Exception as e:
        logger.error("Error getting learning statistics: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/ai/learning/predict")
@rate_limit(rate=100, per=60)
async def predict_performance(request: Request, context: dict[str, Any], action: str = Query(...)) -> dict[str, Any]:
    """Predict performance for a given action"""
    try:
        result = await learning_system.predict_performance(context, action)
        return result
    except Exception as e:
        logger.error("Error predicting performance: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/ai/learning/recommend")
@rate_limit(rate=100, per=60)
async def recommend_action(request: Request, context: dict[str, Any], available_actions: list[str]) -> dict[str, Any]:
    """Get AI-recommended action"""
    try:
        result = await learning_system.recommend_action(context, available_actions)
        return result
    except Exception as e:
        logger.error("Error recommending action: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/ai/neural-network/create")
@rate_limit(rate=50, per=60)
async def create_neural_network(request: Request, config: dict[str, Any]) -> dict[str, Any]:
    """Create a new neural network"""
    try:
        result = await ai_integration.create_neural_network(config)
        return result
    except Exception as e:
        logger.error("Error creating neural network: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/ai/neural-network/{network_id}/train")
@rate_limit(rate=50, per=60)
async def train_neural_network(
    request: Request, network_id: str, training_data: list[dict[str, Any]], epochs: int = 100
) -> dict[str, Any]:
    """Train a neural network"""
    try:
        result = await ai_integration.train_neural_network(network_id, training_data, epochs)
        return result
    except Exception as e:
        logger.error("Error training neural network: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/ai/neural-network/{network_id}/predict")
@rate_limit(rate=100, per=60)
async def predict_with_neural_network(request: Request, network_id: str, features: list[float]) -> dict[str, Any]:
    """Make prediction with neural network"""
    try:
        result = await ai_integration.predict_with_neural_network(network_id, features)
        return result
    except Exception as e:
        logger.error("Error predicting with neural network: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/ai/ml-model/create")
@rate_limit(rate=50, per=60)
async def create_ml_model(request: Request, config: dict[str, Any]) -> dict[str, Any]:
    """Create a new ML model"""
    try:
        result = await ai_integration.create_ml_model(config)
        return result
    except Exception as e:
        logger.error("Error creating ML model: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/ai/ml-model/{model_id}/train")
@rate_limit(rate=50, per=60)
async def train_ml_model(request: Request, model_id: str, training_data: list[dict[str, Any]]) -> dict[str, Any]:
    """Train an ML model"""
    try:
        result = await ai_integration.train_ml_model(model_id, training_data)
        return result
    except Exception as e:
        logger.error("Error training ML model: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/ai/ml-model/{model_id}/predict")
@rate_limit(rate=100, per=60)
async def predict_with_ml_model(request: Request, model_id: str, features: list[float]) -> dict[str, Any]:
    """Make prediction with ML model"""
    try:
        result = await ai_integration.predict_with_ml_model(model_id, features)
        return result
    except Exception as e:
        logger.error("Error predicting with ML model: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/ai/statistics")
@rate_limit(rate=200, per=60)
async def get_ai_statistics(request: Request) -> dict[str, Any]:
    """Get comprehensive AI/ML statistics"""
    try:
        result = await ai_integration.get_ai_statistics()
        return result
    except Exception as e:
        logger.error("Error getting AI statistics: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e
