from datetime import UTC, datetime
from typing import Any

from aitbc.aitbc_logging import get_logger
from aitbc.rate_limiting import rate_limit
from fastapi import APIRouter, Request

logger = get_logger(__name__)
router = APIRouter()


# Health check endpoint
@router.get("/health")
@rate_limit(rate=1000, per=60)
async def health_check(request: Request) -> dict[str, Any]:
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "agent-coordinator",
        "timestamp": datetime.now(UTC).isoformat(),
        "version": "1.0.0",
    }


# Root endpoint
@router.get("/")
@rate_limit(rate=1000, per=60)
async def root(request: Request) -> dict[str, Any]:
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
            "/registry/stats",
        ],
    }
