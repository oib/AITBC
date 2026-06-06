"""Monitor router for AITBC Agent Coordinator."""


from fastapi import APIRouter, Request

from aitbc.rate_limiting import rate_limit

router = APIRouter(tags=["Monitor"])


@router.get("/api/v1/dashboard", response_model=dict)
@rate_limit(rate=1000, per=60)
async def get_dashboard(request: Request):
    """Get monitoring dashboard data."""
    return {
        "overall_status": "operational",
        "services": {
            "coordinator": "online",
            "exchange": "online",
            "blockchain": "online"
        },
        "metrics": {
            "active_agents": 0,
            "active_jobs": 0,
            "total_jobs": 0
        },
        "alerts": []
    }


@router.get("/status", response_model=dict)
@rate_limit(rate=1000, per=60)
async def get_status(request: Request):
    """Get coordinator status."""
    return {
        "status": "online",
        "version": "1.0.0",
        "uptime": 3600,
        "timestamp": "2026-05-08T12:00:00Z"
    }


@router.get("/miners", response_model=list[dict])
@rate_limit(rate=500, per=60)
async def get_miners(request: Request):
    """Get miners list."""
    return []


@router.get("/dashboard", response_model=list[dict])
@rate_limit(rate=500, per=60)
async def get_history_dashboard(request: Request):
    """Get historical dashboard data."""
    return []


@router.get("/jobs", response_model=list[dict])
@rate_limit(rate=500, per=60)
async def get_jobs(request: Request):
    """Get jobs list for history and metrics commands."""
    return []
