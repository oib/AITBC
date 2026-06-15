"""Router for Hermes autonomous resource management API."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from aitbc import get_logger

from ....deps import require_admin_key
from ....schemas.hermes_resource import (
    PricingAdjustment,
    Resource,
    ResourceAllocationRequest,
    ResourceAllocationResponse,
    ResourcePool,
    ResourceReleaseRequest,
    ResourceReleaseResponse,
    ResourceType,
)
from ....storage import get_session
from ..services.resource_service_db import resource_service

logger = get_logger(__name__)

router = APIRouter(prefix="/hermes/resource", tags=["hermes Resource Management"])


@router.post("/register")
async def register_resource(
    resource: Resource, session: Annotated[Session, Depends(get_session)], current_user: str = Depends(require_admin_key())
) -> dict[str, Any]:
    """Register a new resource for autonomous management."""
    try:
        resource_id = resource_service.register_resource(resource, session)
        return {"status": "success", "resource_id": resource_id}
    except Exception as e:
        logger.error("Error registering resource: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/allocate", response_model=ResourceAllocationResponse)
async def allocate_resource(
    allocation_request: ResourceAllocationRequest,
    session: Annotated[Session, Depends(get_session)],
    current_user: str = Depends(require_admin_key()),
) -> ResourceAllocationResponse:
    """Allocate resources based on strategy."""
    try:
        return resource_service.allocate_resource(allocation_request, session)
    except Exception as e:
        logger.error("Error allocating resource: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/release", response_model=ResourceReleaseResponse)
async def release_resource(
    release_request: ResourceReleaseRequest,
    session: Annotated[Session, Depends(get_session)],
    current_user: str = Depends(require_admin_key()),
) -> ResourceReleaseResponse:
    """Release allocated resources."""
    try:
        return resource_service.release_resource(release_request, session)
    except Exception as e:
        logger.error("Error releasing resource: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/pricing/adjust", response_model=PricingAdjustment | None)
async def adjust_pricing(
    session: Annotated[Session, Depends(get_session)], current_user: str = Depends(require_admin_key())
) -> PricingAdjustment | None:
    """Automatically adjust pricing based on utilization."""
    try:
        return resource_service.adjust_pricing(ResourceType.GPU, session)
    except Exception as e:
        logger.error("Error adjusting pricing: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/pools", response_model=list[ResourcePool])
async def get_resource_pools(
    session: Annotated[Session, Depends(get_session)], current_user: str = Depends(require_admin_key())
) -> list[ResourcePool]:
    """Get all resource pools."""
    try:
        return resource_service.get_resource_pools(session)
    except Exception as e:
        logger.error("Error getting resource pools: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/allocations")
async def get_allocations(
    session: Annotated[Session, Depends(get_session)],
    current_user: str = Depends(require_admin_key()),
    agent_id: str | None = None,
) -> list[dict[str, Any]]:
    """Get allocations with optional filtering."""
    try:
        return resource_service.get_allocations(agent_id, session)
    except Exception as e:
        logger.error("Error getting allocations: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e
