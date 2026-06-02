"""Router for Hermes autonomous resource management API."""

from typing import Annotated, Optional, List

from sqlalchemy.orm import Session

from aitbc import get_logger

logger = get_logger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Request

from aitbc.rate_limiting import rate_limit

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
@rate_limit(rate=10, per=60)
async def register_resource(
    request: Request,
    resource: Resource,
    session: Session = Depends(Annotated[Session, Depends(get_session)]),  # type: ignore[arg-type]
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
@rate_limit(rate=20, per=60)
async def allocate_resource(
    request: Request,
    allocation_request: ResourceAllocationRequest,
    session: Session = Depends(Annotated[Session, Depends(get_session)]),  # type: ignore[arg-type]
    current_user: str = Depends(require_admin_key()),
) -> ResourceAllocationResponse:
    """Allocate resources based on strategy."""
    try:
        return resource_service.allocate_resource(allocation_request, session)
    except Exception as e:
        logger.error(f"Error allocating resource: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/release", response_model=ResourceReleaseResponse)
@rate_limit(rate=20, per=60)
async def release_resource(
    request: Request,
    release_request: ResourceReleaseRequest,
    session: Session = Depends(Annotated[Session, Depends(get_session)]),  # type: ignore[arg-type]
    current_user: str = Depends(require_admin_key()),
) -> ResourceReleaseResponse:
    """Release allocated resources."""
    try:
        return resource_service.release_resource(release_request, session)
    except Exception as e:
        logger.error(f"Error releasing resource: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pricing/adjust", response_model=Optional[PricingAdjustment])
@rate_limit(rate=5, per=60)
async def adjust_pricing(
    request: Request,
    resource_type: ResourceType,
    session: Session = Depends(Annotated[Session, Depends(get_session)]),  # type: ignore[arg-type]
    current_user: str = Depends(require_admin_key()),
) -> Optional[PricingAdjustment]:
    """Automatically adjust pricing based on utilization."""
    try:
        return resource_service.adjust_pricing(resource_type, session)
    except Exception as e:
        logger.error(f"Error adjusting pricing: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pools", response_model=List[ResourcePool])
@rate_limit(rate=30, per=60)
async def get_resource_pools(
    request: Request,
    session: Session = Depends(Annotated[Session, Depends(get_session)]),  # type: ignore[arg-type]
    current_user: str = Depends(require_admin_key()),
) -> List[ResourcePool]:
    """Get all resource pools."""
    try:
        return resource_service.get_resource_pools(session)
    except Exception as e:
        logger.error(f"Error getting resource pools: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/allocations")
@rate_limit(rate=30, per=60)
async def get_allocations(
    request: Request,
    agent_id: Optional[str] = None,
    session: Session = Depends(Annotated[Session, Depends(get_session)]),  # type: ignore[arg-type]
    current_user: str = Depends(require_admin_key()),
) -> List[dict]:
    """Get allocations with optional filtering."""
    try:
        return resource_service.get_allocations(agent_id, session)
    except Exception as e:
        logger.error(f"Error getting allocations: {e}")
        raise HTTPException(status_code=500, detail=str(e))
