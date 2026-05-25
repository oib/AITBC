"""Monitor router for AITBC Coordinator API."""

from fastapi import APIRouter, Request
from typing import List, Dict

from aitbc.rate_limiting import rate_limit

router = APIRouter(tags=["Monitor"])


@router.get("/api/v1/dashboard", response_model=dict)
@rate_limit(rate=100, per=60)
async def get_dashboard(request: Request) -> None:
    """Get monitoring dashboard data."""
    return {  # type: ignore[return-value]
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
@rate_limit(rate=100, per=60)
async def get_status(request: Request) -> None:
    """Get coordinator status."""
    return {  # type: ignore[return-value]
        "status": "online",
        "version": "1.0.0",
        "uptime": 3600,
        "timestamp": "2026-05-08T12:00:00Z"
    }


@router.get("/miners", response_model=List[Dict])
@rate_limit(rate=50, per=60)
async def get_miners(request: Request) -> None:
    """Get miners list."""
    return []  # type: ignore[return-value]


@router.get("/dashboard", response_model=List[Dict])
@rate_limit(rate=50, per=60)
async def get_history_dashboard(request: Request) -> None:
    """Get historical dashboard data."""
    return []  # type: ignore[return-value]


@router.get("/jobs", response_model=List[Dict])
@rate_limit(rate=50, per=60)
async def get_jobs(request: Request) -> None:
    """Get jobs list for history and metrics commands."""
    return []  # type: ignore[return-value]
