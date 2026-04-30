from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..domain.gpu_marketplace import ConsumerGPUProfile, EdgeGPUMetrics, GPUArchitecture
from ..services.edge_gpu_service import EdgeGPUService
from ..storage import get_session

router = APIRouter(prefix="/v1/marketplace/edge-gpu", tags=["edge-gpu"])


def get_edge_service(session: Annotated[Session, Depends(get_session)]) -> EdgeGPUService:
    return EdgeGPUService(session)


@router.get("/profiles", response_model=list[ConsumerGPUProfile])
async def get_consumer_gpu_profiles(
    architecture: GPUArchitecture | None = Query(default=None),
    edge_optimized: bool | None = Query(default=None),
    min_memory_gb: int | None = Query(default=None),
    svc: EdgeGPUService = Depends(get_edge_service),
) -> list[ConsumerGPUProfile]:
    return svc.list_profiles(architecture=architecture, edge_optimized=edge_optimized, min_memory_gb=min_memory_gb)


@router.get("/metrics/{gpu_id}", response_model=list[EdgeGPUMetrics])
async def get_edge_gpu_metrics(
    gpu_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    svc: EdgeGPUService = Depends(get_edge_service),
) -> list[EdgeGPUMetrics]:
    return svc.list_metrics(gpu_id=gpu_id, limit=limit)


@router.post("/scan/{miner_id}")
async def scan_edge_gpus(miner_id: str, svc: EdgeGPUService = Depends(get_edge_service)) -> dict[str, Any]:
    """Scan and register edge GPUs for a miner"""
    try:
        result = await svc.discover_and_register_edge_gpus(miner_id)
        return {
            "miner_id": miner_id,
            "gpus_discovered": len(result["gpus"]),
            "gpus_registered": result["registered"],
            "edge_optimized": result["edge_optimized"],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/optimize/inference/{gpu_id}")
async def optimize_inference(
    gpu_id: str, model_name: str, request_data: dict, svc: EdgeGPUService = Depends(get_edge_service)
) -> dict[str, Any]:
    """Optimize ML inference request for edge GPU"""
    try:
        optimized = await svc.optimize_inference_for_edge(gpu_id, model_name, request_data)
        return optimized
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
