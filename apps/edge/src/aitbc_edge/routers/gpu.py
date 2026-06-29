"""GPU operations router for Edge API Service"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..services.gpu_service import GPUService

router = APIRouter()


class ScanGPUsRequest(BaseModel):
    """Request model for scanning GPUs"""

    miner_id: str


def get_gpu_service() -> GPUService:
    """Dependency injection for GPU service"""
    return GPUService()


@router.get("/")
async def list_gpus(
    architecture: str | None,
    edge_optimized: bool | None,
    min_memory_gb: int | None,
    svc: Annotated[GPUService, Depends(get_gpu_service)],
) -> dict[str, Any]:
    """List all GPUs"""
    gpus = await svc.list_gpus(architecture=architecture, edge_optimized=edge_optimized, min_memory_gb=min_memory_gb)
    return {"gpus": gpus, "total": len(gpus)}


@router.get("/{gpu_id}")
async def get_gpu_listing(gpu_id: str, svc: Annotated[GPUService, Depends(get_gpu_service)]) -> Any:
    """Get GPU listing details"""
    gpu = await svc.get_gpu_listing(gpu_id)
    if gpu is None:
        raise HTTPException(status_code=404, detail=f"GPU {gpu_id} not found")
    return gpu


@router.delete("/{gpu_id}")
async def remove_gpu_listing(gpu_id: str, svc: Annotated[GPUService, Depends(get_gpu_service)]) -> dict[str, str]:
    """Remove GPU listing"""
    success = await svc.remove_gpu_listing(gpu_id)
    if success:
        return {"message": f"GPU {gpu_id} removed"}
    else:
        raise HTTPException(status_code=404, detail=f"GPU {gpu_id} not found")


@router.post("/scan")
async def scan_gpus(request: ScanGPUsRequest, svc: Annotated[GPUService, Depends(get_gpu_service)]) -> Any:
    """Scan GPUs for a miner"""
    result = await svc.scan_gpus(request.miner_id)
    return result


@router.get("/{gpu_id}/metrics")
async def get_gpu_metrics(
    gpu_id: str, limit: int | None, svc: Annotated[GPUService, Depends(get_gpu_service)]
) -> dict[str, Any]:
    """Get GPU metrics"""
    metrics = await svc.get_gpu_metrics(gpu_id, limit)
    return {"gpu_id": gpu_id, "metrics": metrics, "total": len(metrics)}


@router.post("/advertise")
async def advertise_to_marketplace(svc: Annotated[GPUService, Depends(get_gpu_service)]) -> Any:
    """Advertise this edge node's GPU capabilities to the marketplace (v0.6.6)."""
    result = await svc.advertise_to_marketplace()
    return result
