"""Router for Hermes autonomous resource management API."""

from typing import Annotated, Optional, List

from sqlalchemy.orm import Session

from aitbc import get_logger

logger = get_logger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Request

from ....deps import require_admin_key
from ....schemas.hermes_resource import (
    Resource,
    ResourceType,
    ResourceStatus,
    AllocationStrategy,
    ResourceAllocationRequest,
    ResourceAllocationResponse,
    ResourceReleaseRequest,
    ResourceReleaseResponse,
    PricingAdjustment,
    ResourcePool,
)
from ....storage import get_session
from ..services.resource_service import resource_service

router = APIRouter(prefix="/hermes/resource", tags=["hermes Resource Management"])


@router.post("/register")
async def register_resource(
    resource: Resource,
    current_user: str = Depends(require_admin_key()),
) -> dict:
    """Register a new resource for autonomous management."""
    try:
        resource_id = resource_service.register_resource(resource, None)
        return {"status": "success", "resource_id": resource_id}
    except Exception as e:
        logger.error(f"Error registering resource: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/allocate", response_model=ResourceAllocationResponse)
async def allocate_resource(
    allocation_request: ResourceAllocationRequest,
    current_user: str = Depends(require_admin_key()),
) -> ResourceAllocationResponse:
    """Allocate resources based on strategy."""
    try:
        return resource_service.allocate_resource(allocation_request, None)
    except Exception as e:
        logger.error(f"Error allocating resource: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/release", response_model=ResourceReleaseResponse)
async def release_resource(
    release_request: ResourceReleaseRequest,
    current_user: str = Depends(require_admin_key()),
) -> ResourceReleaseResponse:
    """Release allocated resources."""
    try:
        return resource_service.release_resource(release_request, None)
    except Exception as e:
        logger.error(f"Error releasing resource: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pricing/adjust", response_model=Optional[PricingAdjustment])
async def adjust_pricing(
    current_user: str = Depends(require_admin_key()),
) -> Optional[PricingAdjustment]:
    """Automatically adjust pricing based on utilization."""
    try:
        # For now, adjust GPU pricing (can be extended to accept resource_type in body)
        return resource_service.adjust_pricing(ResourceType.GPU, None)
    except Exception as e:
        logger.error(f"Error adjusting pricing: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pools", response_model=List[ResourcePool])
async def get_resource_pools(
    current_user: str = Depends(require_admin_key()),
) -> List[ResourcePool]:
    """Get all resource pools."""
    try:
        return resource_service.get_resource_pools(None)
    except Exception as e:
        logger.error(f"Error getting resource pools: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/allocations")
async def get_allocations(
    agent_id: Optional[str] = None,
    current_user: str = Depends(require_admin_key()),
) -> List[dict]:
    """Get allocations with optional filtering."""
    try:
        return resource_service.get_allocations(agent_id, None)
    except Exception as e:
        logger.error(f"Error getting allocations: {e}")
        raise HTTPException(status_code=500, detail=str(e))
