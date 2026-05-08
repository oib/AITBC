"""Monitor router for AITBC Agent Coordinator."""

from fastapi import APIRouter
from typing import List, Dict

router = APIRouter(tags=["Monitor"])


@router.get("/api/v1/dashboard", response_model=dict)
async def get_dashboard():
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
async def get_status():
    """Get coordinator status."""
    return {
        "status": "online",
        "version": "1.0.0",
        "uptime": 3600,
        "timestamp": "2026-05-08T12:00:00Z"
    }


@router.get("/miners", response_model=List[Dict])
async def get_miners():
    """Get miners list."""
    return []


@router.get("/dashboard", response_model=List[Dict])
async def get_history_dashboard():
    """Get historical dashboard data."""
    return []
