from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from ..storage import SessionDep, get_session
from ..domain.gpu_marketplace import ConsumerGPUProfile, GPUArchitecture, EdgeGPUMetrics
from ..services.edge_gpu_service import EdgeGPUService

router = APIRouter(prefix="/v1/marketplace/edge-gpu", tags=["edge-gpu"])


def get_edge_service(session: SessionDep) -> EdgeGPUService:
    return EdgeGPUService(session)


@router.get("/profiles", response_model=List[ConsumerGPUProfile])
async def get_consumer_gpu_profiles(
    architecture: Optional[GPUArchitecture] = Query(default=None),
    edge_optimized: Optional[bool] = Query(default=None),
    min_memory_gb: Optional[int] = Query(default=None),
    svc: EdgeGPUService = Depends(get_edge_service),
):
    return svc.list_profiles(architecture=architecture, edge_optimized=edge_optimized, min_memory_gb=min_memory_gb)


@router.get("/metrics/{gpu_id}", response_model=List[EdgeGPUMetrics])
async def get_edge_gpu_metrics(
    gpu_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    svc: EdgeGPUService = Depends(get_edge_service),
):
    return svc.list_metrics(gpu_id=gpu_id, limit=limit)


@router.post("/scan/{miner_id}")
async def scan_edge_gpus(miner_id: str, svc: EdgeGPUService = Depends(get_edge_service)):
    """Scan and register edge GPUs for a miner"""
    try:
        result = await svc.discover_and_register_edge_gpus(miner_id)
        return {
            "miner_id": miner_id,
            "gpus_discovered": len(result["gpus"]),
            "gpus_registered": result["registered"],
            "edge_optimized": result["edge_optimized"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/optimize/inference/{gpu_id}")
async def optimize_inference(
    gpu_id: str,
    model_name: str,
    request_data: dict,
    svc: EdgeGPUService = Depends(get_edge_service)
):
    """Optimize ML inference request for edge GPU"""
    try:
        optimized = await svc.optimize_inference_for_edge(
            gpu_id, model_name, request_data
        )
        return optimized
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
