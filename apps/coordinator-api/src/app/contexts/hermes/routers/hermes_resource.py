"""Router for Hermes autonomous resource management API."""

from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from aitbc import get_logger

logger = get_logger(__name__)

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

router = APIRouter(prefix="/hermes/resource", tags=["hermes Resource Management"])


@router.post("/register")
async def register_resource(
    resource: Resource,
    session: Annotated[Session, Depends(get_session)],
    current_user: str = Depends(require_admin_key()),
) -> dict:
    """Register a new resource for autonomous management."""
    try:
        resource_id = resource_service.register_resource(resource, session)
        return {"status": "success", "resource_id": resource_id}
    except Exception as e:
        logger.error(f"Error registering resource: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
        logger.error(f"Error allocating resource: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
        logger.error(f"Error releasing resource: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pricing/adjust", response_model=Optional[PricingAdjustment])
async def adjust_pricing(
    session: Annotated[Session, Depends(get_session)],
    current_user: str = Depends(require_admin_key()),
) -> Optional[PricingAdjustment]:
    """Automatically adjust pricing based on utilization."""
    try:
        # For now, adjust GPU pricing (can be extended to accept resource_type in body)
        return resource_service.adjust_pricing(ResourceType.GPU, session)
    except Exception as e:
        logger.error(f"Error adjusting pricing: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pools", response_model=List[ResourcePool])
async def get_resource_pools(
    session: Annotated[Session, Depends(get_session)],
    current_user: str = Depends(require_admin_key()),
) -> List[ResourcePool]:
    """Get all resource pools."""
    try:
        return resource_service.get_resource_pools(session)
    except Exception as e:
        logger.error(f"Error getting resource pools: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/allocations")
async def get_allocations(
    session: Annotated[Session, Depends(get_session)],
    current_user: str = Depends(require_admin_key()),
    agent_id: Optional[str] = None,
) -> List[dict]:
    """Get allocations with optional filtering."""
    try:
        return resource_service.get_allocations(agent_id, session)
    except Exception as e:
        logger.error(f"Error getting allocations: {e}")
        raise HTTPException(status_code=500, detail=str(e))
