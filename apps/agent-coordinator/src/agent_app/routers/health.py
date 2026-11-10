from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response

from aitbc.aitbc_logging import get_logger
from aitbc.health_checks import HealthStatus, create_basic_health_check
from aitbc.rate_limiting import rate_limit

from .. import state
from ..services.agent_auth import AgentPrincipal, optional_agent

logger = get_logger(__name__)
router = APIRouter()

# Resolves the caller's principal if credentials are present, ``None``
# otherwise — anonymous callers get a status-only response.
OptionalAgent = Annotated[AgentPrincipal | None, Depends(optional_agent)]

# Build a health checker with basic system checks (memory, disk)
_health_checker = create_basic_health_check("agent-coordinator")


# Health check endpoint — HEAD registered too (FastAPI does not auto-add it)
# so uptime monitors can probe without a body; kept out of the OpenAPI schema.
@router.head("/health", include_in_schema=False)
@router.get("/health")
@rate_limit(rate=1000, per=60)
async def health_check(request: Request, response: Response, principal: OptionalAgent) -> dict[str, Any]:
    """Health check endpoint.

    Anonymous callers get ``{status, service, timestamp}`` only — version,
    memory and disk detail go only to a resolved principal (any mode:
    the credential merely has to resolve, not satisfy a scope).

    Redis carries the agent registry: every register/unregister/identity
    mutator persists through it, so a dead Redis breaks the service's core
    writes while the process stays up. The probe goes through the live
    registry client; an app built without the lifespan (tests) has no
    client and the check is skipped. An unhealthy result answers 503 —
    uptime monitors key on the status code, not the body.
    """
    result = _health_checker.get_health_dict()
    # Preserve the version field expected by callers
    result["version"] = "1.0.0"

    registry = state.agent_registry
    redis_client = getattr(registry, "redis_client", None) if registry is not None else None
    if redis_client is not None:
        try:
            await redis_client.ping()
        except Exception:
            logger.warning("Health check: agent registry Redis ping failed")
            result["status"] = HealthStatus.UNHEALTHY
            result["message"] = "Unhealthy: redis"
            details = dict(result.get("details") or {})
            details["redis"] = {
                "status": HealthStatus.UNHEALTHY.value,
                "message": "Redis ping failed",
                "details": None,
            }
            result["details"] = details

    if result.get("status") == HealthStatus.UNHEALTHY:
        response.status_code = 503

    if principal is None:
        return {
            "service": result.get("service"),
            "status": result.get("status"),
            "timestamp": result.get("timestamp"),
        }
    return result


# Root endpoint
@router.get("/")
@rate_limit(rate=1000, per=60)
def root(request: Request) -> dict[str, Any]:
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
