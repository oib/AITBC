"""Developer profile management endpoints for the Developer Platform."""

from typing import Annotated, Any

from aitbc.rate_limiting import rate_limit
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import Session

from ....storage.db import get_session
from ..schemas.developer_platform import DeveloperCreate
from ..services.developer_platform_service import DeveloperPlatformService
from .common import get_developer_platform_service

router = APIRouter(tags=["Developer Platform"])


@router.post("/register", response_model=dict[str, Any])
@rate_limit(rate=10, per=60)
async def register_developer(
    request: DeveloperCreate,
    request_http: Request,
    session: Annotated[Session, Depends(get_session)],
    dev_service: Annotated[DeveloperPlatformService, Depends(get_developer_platform_service)],
) -> dict[str, Any]:
    """Register a new developer profile."""

    try:
        profile = await dev_service.register_developer(request)

        return {
            "success": True,
            "profile_id": profile.id,
            "wallet_address": profile.wallet_address,
            "reputation_score": profile.reputation_score,
            "created_at": profile.created_at.isoformat(),
            "message": "Developer profile registered successfully",
        }

    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Error registering developer") from None


@router.get("/profile/{wallet_address}", response_model=dict[str, Any])
@rate_limit(rate=200, per=60)
async def get_developer_profile(
    wallet_address: str,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    dev_service: Annotated[DeveloperPlatformService, Depends(get_developer_platform_service)],
) -> dict[str, Any]:
    """Get developer profile by wallet address."""

    try:
        profile = await dev_service.get_developer_profile(wallet_address)
        if not profile:
            raise HTTPException(status_code=404, detail="Developer profile not found")

        return {
            "id": profile.id,
            "wallet_address": profile.wallet_address,
            "github_handle": profile.github_handle,
            "email": profile.email,
            "reputation_score": profile.reputation_score,
            "total_earned_aitbc": profile.total_earned_aitbc,
            "skills": profile.skills,
            "is_active": profile.is_active,
            "created_at": profile.created_at.isoformat(),
            "updated_at": profile.updated_at.isoformat(),
        }

    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Error getting developer profile") from None


@router.put("/profile/{wallet_address}", response_model=dict[str, Any])
@rate_limit(rate=50, per=60)
async def update_developer_profile(
    wallet_address: str,
    updates: dict[str, Any],
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    dev_service: Annotated[DeveloperPlatformService, Depends(get_developer_platform_service)],
) -> dict[str, Any]:
    """Update developer profile."""

    try:
        profile = await dev_service.update_developer_profile(wallet_address, updates)

        return {
            "success": True,
            "profile_id": profile.id,
            "wallet_address": profile.wallet_address,
            "updated_at": profile.updated_at.isoformat(),
            "message": "Developer profile updated successfully",
        }

    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Error updating developer profile") from None


@router.get("/leaderboard", response_model=list[dict[str, Any]])
@rate_limit(rate=200, per=60)
async def get_leaderboard(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    dev_service: Annotated[DeveloperPlatformService, Depends(get_developer_platform_service)],
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Get developer leaderboard sorted by reputation score."""

    try:
        developers = await dev_service.get_leaderboard(limit or 100, offset or 0)

        return [
            {
                "rank": (offset or 0) + i + 1,
                "id": dev.id,
                "wallet_address": dev.wallet_address,
                "github_handle": dev.github_handle,
                "reputation_score": dev.reputation_score,
                "total_earned_aitbc": dev.total_earned_aitbc,
                "skills_count": len(dev.skills),
                "created_at": dev.created_at.isoformat(),
            }
            for i, dev in enumerate(developers)
        ]

    except Exception:
        raise HTTPException(status_code=500, detail="Error getting leaderboard") from None


@router.get("/stats/{wallet_address}", response_model=dict[str, Any])
@rate_limit(rate=200, per=60)
async def get_developer_stats(
    wallet_address: str,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    dev_service: Annotated[DeveloperPlatformService, Depends(get_developer_platform_service)],
) -> dict[str, Any]:
    """Get comprehensive developer statistics."""

    try:
        stats = await dev_service.get_developer_stats(wallet_address)
        return stats

    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Error getting developer stats") from None
