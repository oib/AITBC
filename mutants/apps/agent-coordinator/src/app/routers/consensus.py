from datetime import UTC, datetime
from typing import Any

from aitbc import get_logger
from aitbc.rate_limiting import rate_limit
from fastapi import APIRouter, HTTPException, Query, Request

from ..ai.advanced_ai import ai_integration
from ..ai.realtime_learning import learning_system
from ..consensus.distributed_consensus import distributed_consensus

logger = get_logger(__name__)
router = APIRouter()


@router.post("/consensus/node/register")
@rate_limit(rate=50, per=60)
async def register_consensus_node(request: Request, node_data: dict[str, Any]) -> dict[str, Any]:
    """Register a node in the consensus network"""
    try:
        result = await distributed_consensus.register_node(node_data)
        return result
    except Exception as e:
        logger.error("Error registering consensus node: %s", e)
        raise HTTPException(status_code=500, detail="Failed to register consensus node") from e


@router.post("/consensus/proposal/create")
@rate_limit(rate=50, per=60)
async def create_consensus_proposal(request: Request, proposal_data: dict[str, Any]) -> dict[str, Any]:
    """Create a new consensus proposal"""
    try:
        result = await distributed_consensus.create_proposal(proposal_data)
        return result
    except Exception as e:
        logger.error("Error creating consensus proposal: %s", e)
        raise HTTPException(status_code=500, detail="Failed to create consensus proposal") from e


@router.post("/consensus/proposal/{proposal_id}/vote")
@rate_limit(rate=50, per=60)
async def cast_consensus_vote(request: Request, proposal_id: str, node_id: str, vote: bool) -> dict[str, Any]:
    """Cast a vote for a proposal"""
    try:
        result = await distributed_consensus.cast_vote(proposal_id, node_id, vote)
        return result
    except Exception as e:
        logger.error("Error casting consensus vote: %s", e)
        raise HTTPException(status_code=500, detail="Failed to cast consensus vote") from e


@router.get("/consensus/proposal/{proposal_id}")
@rate_limit(rate=200, per=60)
async def get_proposal_status(request: Request, proposal_id: str) -> dict[str, Any]:
    """Get proposal status"""
    try:
        result = await distributed_consensus.get_proposal_status(proposal_id)
        return result
    except Exception as e:
        logger.error("Error getting proposal status: %s", e)
        raise HTTPException(status_code=500, detail="Failed to get proposal status") from e


@router.put("/consensus/algorithm")
@rate_limit(rate=50, per=60)
async def set_consensus_algorithm(
    request: Request, algorithm: str = Query(..., description="Consensus algorithm")
) -> dict[str, Any]:
    """Set the consensus algorithm"""
    try:
        result = await distributed_consensus.set_consensus_algorithm(algorithm)
        return result
    except Exception as e:
        logger.error("Error setting consensus algorithm: %s", e)
        raise HTTPException(status_code=500, detail="Failed to set consensus algorithm") from e


@router.get("/consensus/statistics")
@rate_limit(rate=200, per=60)
async def get_consensus_statistics(request: Request) -> dict[str, Any]:
    """Get consensus statistics"""
    try:
        result = await distributed_consensus.get_consensus_statistics()
        return result
    except Exception as e:
        logger.error("Error getting consensus statistics: %s", e)
        raise HTTPException(status_code=500, detail="Failed to get consensus statistics") from e


@router.put("/consensus/node/{node_id}/status")
@rate_limit(rate=50, per=60)
async def update_node_status(request: Request, node_id: str, is_active: bool) -> dict[str, Any]:
    """Update node status"""
    try:
        result = await distributed_consensus.update_node_status(node_id, is_active)
        return result
    except Exception as e:
        logger.error("Error updating node status: %s", e)
        raise HTTPException(status_code=500, detail="Failed to update node status") from e


@router.get("/advanced-features/status")
@rate_limit(rate=200, per=60)
async def get_advanced_features_status(request: Request) -> dict[str, Any]:
    """Get status of all advanced features"""
    try:
        learning_stats = await learning_system.get_learning_statistics()
        ai_stats = await ai_integration.get_ai_statistics()
        consensus_stats = await distributed_consensus.get_consensus_statistics()
        return {
            "status": "success",
            "timestamp": datetime.now(UTC).isoformat(),
            "features": {
                "realtime_learning": {
                    "status": "active",
                    "experiences": learning_stats.get("total_experiences", 0),
                    "learning_rate": learning_stats.get("learning_rate", 0.01),
                    "models": learning_stats.get("models_count", 0),
                },
                "advanced_ai": {
                    "status": "active",
                    "models": ai_stats.get("total_models", 0),
                    "neural_networks": ai_stats.get("total_neural_networks", 0),
                    "predictions": ai_stats.get("total_predictions", 0),
                },
                "distributed_consensus": {
                    "status": "active",
                    "nodes": consensus_stats.get("active_nodes", 0),
                    "proposals": consensus_stats.get("total_proposals", 0),
                    "success_rate": consensus_stats.get("success_rate", 0.0),
                    "algorithm": consensus_stats.get("current_algorithm", "majority_vote"),
                },
            },
        }
    except Exception as e:
        logger.error("Error getting advanced features status: %s", e)
        raise HTTPException(status_code=500, detail="Failed to get advanced features status") from e
