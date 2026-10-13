from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from aitbc.aitbc_logging import get_logger
from aitbc.rate_limiting import rate_limit

from ..ai.advanced_ai import ai_integration
from ..ai.realtime_learning import learning_system
from ..services.agent_auth import (
    AgentPrincipal,
    authorize_admin_scope,
    authorize_any_principal,
    optional_agent,
)

logger = get_logger(__name__)
router = APIRouter()

# Resolves the caller's principal if credentials are present, ``None``
# otherwise — the mode-gated gates decide what ``None`` means per endpoint.
OptionalAgent = Annotated[AgentPrincipal | None, Depends(optional_agent)]


@router.post("/ai/learning/experience")
@rate_limit(rate=50, per=60)
async def record_learning_experience(
    request: Request, experience_data: dict[str, Any], principal: OptionalAgent
) -> dict[str, Any]:
    """Record a learning experience for the AI system (Phase C
    admin/operator-only — writes shared training state)."""
    authorize_admin_scope(principal, "ai_learning_experience")
    try:
        result = await learning_system.record_experience(experience_data)
        return result
    except Exception as e:
        logger.error("Error recording learning experience: %s", e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/ai/learning/statistics")
@rate_limit(rate=200, per=60)
async def get_learning_statistics(request: Request, principal: OptionalAgent) -> dict[str, Any]:
    """Get learning system statistics (Phase C: any resolved principal)."""
    authorize_any_principal(principal, "ai_learning_statistics")
    try:
        result = await learning_system.get_learning_statistics()
        return result
    except Exception as e:
        logger.error("Error getting learning statistics: %s", e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/ai/learning/predict")
@rate_limit(rate=100, per=60)
async def predict_performance(
    request: Request, context: dict[str, Any], principal: OptionalAgent, action: str = Query(...)
) -> dict[str, Any]:
    """Predict performance for a given action (Phase C: any resolved
    principal)."""
    authorize_any_principal(principal, "ai_learning_predict")
    try:
        result = await learning_system.predict_performance(context, action)
        return result
    except Exception as e:
        logger.error("Error predicting performance: %s", e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/ai/learning/recommend")
@rate_limit(rate=100, per=60)
async def recommend_action(
    request: Request, context: dict[str, Any], available_actions: list[str], principal: OptionalAgent
) -> dict[str, Any]:
    """Get AI-recommended action (Phase C: any resolved principal)."""
    authorize_any_principal(principal, "ai_learning_recommend")
    try:
        result = await learning_system.recommend_action(context, available_actions)
        return result
    except Exception as e:
        logger.error("Error recommending action: %s", e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/ai/neural-network/create")
@rate_limit(rate=50, per=60)
async def create_neural_network(request: Request, config: dict[str, Any], principal: OptionalAgent) -> dict[str, Any]:
    """Create a new neural network (Phase C admin/operator-only)."""
    authorize_admin_scope(principal, "ai_nn_create")
    try:
        result = await ai_integration.create_neural_network(config)
        return result
    except Exception as e:
        logger.error("Error creating neural network: %s", e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/ai/neural-network/{network_id}/train")
@rate_limit(rate=50, per=60)
async def train_neural_network(
    request: Request,
    network_id: str,
    training_data: list[dict[str, Any]],
    principal: OptionalAgent,
    epochs: int = 100,
) -> dict[str, Any]:
    """Train a neural network (Phase C admin/operator-only —
    compute-heavy)."""
    authorize_admin_scope(principal, "ai_nn_train")
    try:
        result = await ai_integration.train_neural_network(network_id, training_data, epochs)
        return result
    except Exception as e:
        logger.error("Error training neural network: %s", e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/ai/neural-network/{network_id}/predict")
@rate_limit(rate=100, per=60)
async def predict_with_neural_network(
    request: Request, network_id: str, features: list[float], principal: OptionalAgent
) -> dict[str, Any]:
    """Make prediction with neural network (Phase C: any resolved
    principal — read-only inference an agent may legitimately call)."""
    authorize_any_principal(principal, "ai_nn_predict")
    try:
        result = await ai_integration.predict_with_neural_network(network_id, features)
        return result
    except Exception as e:
        logger.error("Error predicting with neural network: %s", e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/ai/ml-model/create")
@rate_limit(rate=50, per=60)
async def create_ml_model(request: Request, config: dict[str, Any], principal: OptionalAgent) -> dict[str, Any]:
    """Create a new ML model (Phase C admin/operator-only)."""
    authorize_admin_scope(principal, "ai_ml_create")
    try:
        result = await ai_integration.create_ml_model(config)
        return result
    except Exception as e:
        logger.error("Error creating ML model: %s", e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/ai/ml-model/{model_id}/train")
@rate_limit(rate=50, per=60)
async def train_ml_model(
    request: Request, model_id: str, training_data: list[dict[str, Any]], principal: OptionalAgent
) -> dict[str, Any]:
    """Train an ML model (Phase C admin/operator-only — compute-heavy)."""
    authorize_admin_scope(principal, "ai_ml_train")
    try:
        result = await ai_integration.train_ml_model(model_id, training_data)
        return result
    except Exception as e:
        logger.error("Error training ML model: %s", e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/ai/ml-model/{model_id}/predict")
@rate_limit(rate=100, per=60)
async def predict_with_ml_model(
    request: Request, model_id: str, features: list[float], principal: OptionalAgent
) -> dict[str, Any]:
    """Make prediction with ML model (Phase C: any resolved principal)."""
    authorize_any_principal(principal, "ai_ml_predict")
    try:
        result = await ai_integration.predict_with_ml_model(model_id, features)
        return result
    except Exception as e:
        logger.error("Error predicting with ML model: %s", e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/ai/statistics")
@rate_limit(rate=200, per=60)
async def get_ai_statistics(request: Request, principal: OptionalAgent) -> dict[str, Any]:
    """Get comprehensive AI/ML statistics (Phase C: any resolved
    principal)."""
    authorize_any_principal(principal, "ai_statistics")
    try:
        result = await ai_integration.get_ai_statistics()
        return result
    except Exception as e:
        logger.error("Error getting AI statistics: %s", e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e
