"""Developer registry API endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlmodel import Session

from aitbc.rate_limiting import rate_limit

from ....storage.db import get_session
from ..domain.developer import Developer
from ..schemas.developer import DeveloperCreate, DeveloperResponse, DeveloperUpdate
from ..services.developer_service import DeveloperService

router = APIRouter(prefix="/developers", tags=["developer"])


def get_service(session: Annotated[Session, Depends(get_session)]) -> DeveloperService:
    """Inject the developer registry service."""
    return DeveloperService(session)


@router.post("", response_model=DeveloperResponse, status_code=201)
@rate_limit(rate=20, per=60)
async def register_developer(
    request: Request,
    body: DeveloperCreate,
    service: Annotated[DeveloperService, Depends(get_service)],
) -> Developer:
    """Register a developer for the DAO grant program."""
    try:
        return await service.register(body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error registering developer: {e}") from e


@router.get("", response_model=list[DeveloperResponse])
@rate_limit(rate=200, per=60)
async def list_developers(
    request: Request,
    service: Annotated[DeveloperService, Depends(get_service)],
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    active_only: Annotated[bool, Query()] = True,
) -> list[Developer]:
    """List registered developers."""
    try:
        return await service.list(limit=limit, offset=offset, active_only=active_only)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing developers: {e}") from e


@router.get("/{wallet_address}", response_model=DeveloperResponse)
@rate_limit(rate=200, per=60)
async def get_developer(
    request: Request,
    wallet_address: str,
    service: Annotated[DeveloperService, Depends(get_service)],
) -> Developer:
    """Get a developer by wallet address."""
    try:
        developer = await service.get_by_wallet(wallet_address)
        if not developer:
            raise HTTPException(status_code=404, detail="Developer not found")
        return developer
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting developer: {e}") from e


@router.put("/{wallet_address}", response_model=DeveloperResponse)
@rate_limit(rate=50, per=60)
async def update_developer(
    request: Request,
    wallet_address: str,
    body: DeveloperUpdate,
    service: Annotated[DeveloperService, Depends(get_service)],
) -> Developer:
    """Update a developer profile."""
    try:
        return await service.update(wallet_address, body)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating developer: {e}") from e
