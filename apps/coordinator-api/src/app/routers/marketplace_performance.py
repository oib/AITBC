"""
Marketplace Performance Optimization API Endpoints
REST API for managing distributed processing, GPU optimization, caching, and scaling
"""

import time
import os
import sys
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from aitbc import get_logger

logger = get_logger(__name__)

from app.services.marketplace_gpu_optimizer import MarketplaceGPUOptimizer
from app.services.distributed_framework import (
    DistributedProcessingCoordinator,
    DistributedTask,
)
from app.services.marketplace_cache_optimizer import MarketplaceDataOptimizer
from app.services.marketplace_monitor import monitor as marketplace_monitor
from app.services.marketplace_scaler import ResourceScaler

router = APIRouter(prefix="/v1/marketplace/performance", tags=["marketplace-performance"])

# Global instances (in a real app these might be injected or application state)
gpu_optimizer = MarketplaceGPUOptimizer()
distributed_coordinator = DistributedProcessingCoordinator()
cache_optimizer = MarketplaceDataOptimizer()
resource_scaler = ResourceScaler()


# Startup event handler for background tasks
@router.on_event("startup")
async def startup_event() -> None:
    await marketplace_monitor.start()
    await distributed_coordinator.start()
    await resource_scaler.start()
    await cache_optimizer.connect()


@router.on_event("shutdown")
async def shutdown_event() -> None:
    await marketplace_monitor.stop()
    await distributed_coordinator.stop()
    await resource_scaler.stop()
    await cache_optimizer.disconnect()


# Models
class GPUAllocationRequest(BaseModel):
    job_id: str | None = None
    memory_bytes: int = Field(1024 * 1024 * 1024, description="Memory needed in bytes")
    compute_units: float = Field(1.0, description="Relative compute requirement")
    max_latency_ms: int = Field(1000, description="Max acceptable latency")
    priority: int = Field(1, ge=1, le=10, description="Job priority 1-10")


class GPUReleaseRequest(BaseModel):
    job_id: str


class DistributedTaskRequest(BaseModel):
    agent_id: str
    payload: dict[str, Any]
    priority: int = Field(1, ge=1, le=100)
    requires_gpu: bool = Field(False)
    timeout_ms: int = Field(30000)


class WorkerRegistrationRequest(BaseModel):
    worker_id: str
    capabilities: list[str]
    has_gpu: bool = Field(False)
    max_concurrent_tasks: int = Field(4)


class ScalingPolicyUpdate(BaseModel):
    min_nodes: int | None = None
    max_nodes: int | None = None
    target_utilization: float | None = None
    scale_up_threshold: float | None = None
    predictive_scaling: bool | None = None


# Endpoints: GPU Optimization
@router.post("/gpu/allocate")
async def allocate_gpu_resources(request: GPUAllocationRequest) -> dict[str, Any]:
    """Request optimal GPU resource allocation for a marketplace task"""
    try:
        start_time = time.time()
        result = await gpu_optimizer.optimize_resource_allocation(request.dict())
        marketplace_monitor.record_api_call((time.time() - start_time) * 1000)

        if not result.get("success"):
            raise HTTPException(status_code=503, detail=result.get("reason", "Resources unavailable"))

        return result
    except HTTPException:
        raise
    except Exception as e:
        marketplace_monitor.record_api_call(0, is_error=True)
        logger.error(f"Error in GPU allocation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/gpu/release")
async def release_gpu_resources(request: GPUReleaseRequest) -> dict[str, str]:
    """Release previously allocated GPU resources"""
    success = gpu_optimizer.release_resources(request.job_id)
    if not success:
        raise HTTPException(status_code=404, detail="Job ID not found")
    return {"success": True, "message": f"Resources for {request.job_id} released"}


@router.get("/gpu/status")
async def get_gpu_status() -> dict[str, Any]:
    """Get overall GPU fleet status and optimization metrics"""
    return gpu_optimizer.get_system_status()


# Endpoints: Distributed Processing
@router.post("/distributed/task")
async def submit_distributed_task(request: DistributedTaskRequest) -> dict[str, str]:
    """Submit a task to the distributed processing framework"""
    task = DistributedTask(
        task_id=None,
        agent_id=request.agent_id,
        payload=request.payload,
        priority=request.priority,
        requires_gpu=request.requires_gpu,
        timeout_ms=request.timeout_ms,
    )

    task_id = await distributed_coordinator.submit_task(task)
    return {"task_id": task_id, "status": "submitted"}


@router.get("/distributed/task/{task_id}")
async def get_distributed_task_status(task_id: str) -> dict[str, Any]:
    """Check the status and get results of a distributed task"""
    status = await distributed_coordinator.get_task_status(task_id)
    if not status:
        raise HTTPException(status_code=404, detail="Task not found")
    return status


@router.post("/distributed/worker/register")
async def register_worker(request: WorkerRegistrationRequest) -> dict[str, str]:
    """Register a new worker node in the cluster"""
    distributed_coordinator.register_worker(
        worker_id=request.worker_id,
        capabilities=request.capabilities,
        has_gpu=request.has_gpu,
        max_tasks=request.max_concurrent_tasks,
    )
    return {"success": True, "message": f"Worker {request.worker_id} registered"}


@router.get("/distributed/status")
async def get_cluster_status() -> dict[str, Any]:
    """Get overall distributed cluster health and load"""
    return distributed_coordinator.get_cluster_status()


# Endpoints: Caching
@router.get("/cache/stats")
async def get_cache_stats() -> dict[str, Any]:
    """Get current caching performance statistics"""
    return {
        "status": "connected" if cache_optimizer.is_connected else "local_only",
        "l1_cache_size": len(cache_optimizer.l1_cache.cache),
        "namespaces_tracked": list(cache_optimizer.ttls.keys()),
    }


@router.post("/cache/invalidate/{namespace}")
async def invalidate_cache_namespace(namespace: str, background_tasks: BackgroundTasks) -> dict[str, str]:
    """Invalidate a specific cache namespace (e.g., 'order_book')"""
    background_tasks.add_task(cache_optimizer.invalidate_namespace, namespace)
    return {"success": True, "message": f"Invalidation for {namespace} queued"}


# Endpoints: Monitoring
@router.get("/monitor/dashboard")
async def get_monitoring_dashboard() -> dict[str, Any]:
    """Get real-time performance dashboard data"""
    return marketplace_monitor.get_realtime_dashboard_data()


# Endpoints: Auto-scaling
@router.get("/scaler/status")
async def get_scaler_status() -> dict[str, Any]:
    """Get current auto-scaler status and active rules"""
    return resource_scaler.get_status()


@router.post("/scaler/policy")
async def update_scaling_policy(policy_update: ScalingPolicyUpdate) -> dict[str, str]:
    """Update auto-scaling thresholds and parameters dynamically"""
    current_policy = resource_scaler.policy

    if policy_update.min_nodes is not None:
        current_policy.min_nodes = policy_update.min_nodes
    if policy_update.max_nodes is not None:
        current_policy.max_nodes = policy_update.max_nodes
    if policy_update.target_utilization is not None:
        current_policy.target_utilization = policy_update.target_utilization
    if policy_update.scale_up_threshold is not None:
        current_policy.scale_up_threshold = policy_update.scale_up_threshold
    if policy_update.predictive_scaling is not None:
        current_policy.predictive_scaling = policy_update.predictive_scaling

    return {"success": True, "message": "Scaling policy updated successfully"}
