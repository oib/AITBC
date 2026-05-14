"""Edge metrics router for Edge API Service"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def get_edge_metrics():
    """Get edge metrics for island - TODO: Implement in Phase 6"""
    return {"message": "Get edge metrics endpoint - to be implemented in Phase 6"}


@router.get("/gpu")
async def get_gpu_metrics():
    """Get GPU metrics - TODO: Implement in Phase 6"""
    return {"message": "Get GPU metrics endpoint - to be implemented in Phase 6"}


@router.get("/database")
async def get_database_metrics():
    """Get database metrics - TODO: Implement in Phase 6"""
    return {"message": "Get database metrics endpoint - to be implemented in Phase 6"}
