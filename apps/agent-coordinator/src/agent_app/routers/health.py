from typing import Any

from fastapi import APIRouter, Request

from aitbc.aitbc_logging import get_logger
from aitbc.health_checks import create_basic_health_check
from aitbc.rate_limiting import rate_limit

logger = get_logger(__name__)
router = APIRouter()

# Build a health checker with basic system checks (memory, disk)
_health_checker = create_basic_health_check("agent-coordinator")


# Health check endpoint
@router.get("/health")
@rate_limit(rate=1000, per=60)
async def health_check(request: Request) -> dict[str, Any]:
    """Health check endpoint"""
    result = _health_checker.get_health_dict()
    # Preserve the version field expected by callers
    result["version"] = "1.0.0"
    return result


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
