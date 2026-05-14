"""GPU operations router for Edge API Service"""

from fastapi import APIRouter

router = APIRouter()


@router.post("/listings")
async def list_gpu():
    """List GPU on island - TODO: Implement in Phase 3"""
    return {"message": "GPU listing endpoint - to be implemented in Phase 3"}


@router.get("/listings")
async def get_gpu_listings():
    """Get GPU listings on island - TODO: Implement in Phase 3"""
    return {"message": "Get GPU listings endpoint - to be implemented in Phase 3"}


@router.delete("/listings/{listing_id}")
async def remove_gpu_listing(listing_id: str):
    """Remove GPU listing - TODO: Implement in Phase 3"""
    return {"message": f"Remove GPU listing {listing_id} - to be implemented in Phase 3"}


@router.get("/scan")
async def scan_gpus():
    """Scan GPUs on island - TODO: Implement in Phase 3"""
    return {"message": "GPU scan endpoint - to be implemented in Phase 3"}
