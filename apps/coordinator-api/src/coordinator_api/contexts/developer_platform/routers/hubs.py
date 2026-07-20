"""Regional hub management endpoints for the Developer Platform."""

from typing import Annotated, Any

from aitbc.rate_limiting import rate_limit
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import Session

from ....storage.db import get_session
from ..services.developer_platform_service import DeveloperPlatformService
from .common import get_developer_platform_service

router = APIRouter(tags=["Developer Platform"])


@router.post("/hubs", response_model=dict[str, Any])
@rate_limit(rate=20, per=60)
async def create_regional_hub(
    request: Request,
    name: str,
    region: str,
    description: str,
    manager_address: str,
    session: Annotated[Session, Depends(get_session)],
    dev_service: Annotated[DeveloperPlatformService, Depends(get_developer_platform_service)],
) -> dict[str, Any]:
    """Create a regional developer hub."""

    try:
        hub = await dev_service.create_regional_hub(name, region, description, manager_address)

        return {
            "success": True,
            "hub_id": hub.id,
            "name": hub.name,
            "region": hub.region_code,
            "description": hub.description,
            "manager_address": hub.lead_wallet_address,
            "is_active": True,
            "created_at": hub.created_at.isoformat(),
            "message": "Regional hub created successfully",
        }

    except Exception:
        raise HTTPException(status_code=500, detail="Error creating regional hub") from None


@router.get("/hubs", response_model=list[dict[str, Any]])
@rate_limit(rate=200, per=60)
async def get_regional_hubs(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    dev_service: Annotated[DeveloperPlatformService, Depends(get_developer_platform_service)],
) -> list[dict[str, Any]]:
    """Get all regional developer hubs."""

    try:
        hubs = await dev_service.get_regional_hubs()

        return [
            {
                "id": hub.id,
                "name": hub.name,
                "region": hub.region_code,
                "description": hub.description,
                "manager_address": hub.lead_wallet_address,
                "developer_count": 0,  # Would be calculated from hub membership
                "is_active": True,
                "created_at": hub.created_at.isoformat(),
            }
            for hub in hubs
        ]

    except Exception:
        raise HTTPException(status_code=500, detail="Error getting regional hubs") from None


@router.get("/hubs/{hub_id}/developers", response_model=list[dict[str, Any]])
@rate_limit(rate=200, per=60)
async def get_hub_developers(
    request: Request,
    hub_id: str,
    limit: int | None,
    session: Annotated[Session, Depends(get_session)],
    dev_service: Annotated[DeveloperPlatformService, Depends(get_developer_platform_service)],
) -> list[dict[str, Any]]:
    """Get developers in a regional hub."""

    try:
        developers = await dev_service.get_hub_developers(hub_id)

        return [
            {
                "id": dev.id,
                "wallet_address": dev.wallet_address,
                "github_handle": dev.github_handle,
                "reputation_score": dev.reputation_score,
                "skills": dev.skills,
                "joined_at": dev.created_at.isoformat(),
            }
            for dev in developers[:limit]
        ]

    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Error getting hub developers") from None
