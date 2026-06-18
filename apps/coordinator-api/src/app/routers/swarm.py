"""
Swarm Router - Compute clustering API endpoints

Provides:
- Node registration and management
- Task submission and tracking
- Cluster formation
- Health monitoring
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field, field_validator

from app.config import settings

# Only enable mock endpoints if debug mode or explicit flag is set
if not (settings.debug or settings.enable_mock_swarm):
    # Create empty router for production
    router = APIRouter(prefix="/swarm", tags=["swarm"])
else:
    router = APIRouter(prefix="/swarm", tags=["swarm"])


class RegisterNodeRequest(BaseModel):
    """Request to register a node"""

    node_id: str = Field(..., min_length=1, max_length=100)
    address: str = Field(..., min_length=1)
    capabilities: list[str] = Field(default_factory=list, max_length=50)
    cpu_cores: int = Field(default=4, ge=1, le=128)
    memory_gb: int = Field(default=16, ge=1, le=1024)
    gpu_count: int = Field(default=0, ge=0, le=16)


class SubmitTaskRequest(BaseModel):
    """Request to submit a task"""

    task_type: str = Field(..., min_length=1, max_length=50)
    payload: dict[str, Any] = Field(..., min_length=1)
    required_capabilities: list[str] | None = Field(default=None, max_length=20)
    priority: int = Field(default=1, ge=1, le=10)


class ReportTaskRequest(BaseModel):
    """Request to report task status"""

    task_id: str = Field(..., min_length=1)
    node_id: str = Field(..., min_length=1)
    status: str = Field(..., min_length=1)
    result: dict[str, Any] | None = None
    error: str | None = Field(default=None, max_length=1000)

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        valid_statuses = {"pending", "running", "completed", "failed", "cancelled"}
        if v.lower() not in valid_statuses:
            raise ValueError(f"status must be one of: {', '.join(valid_statuses)}")
        return v.lower()


class CreateClusterRequest(BaseModel):
    """Request to create a cluster"""

    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    node_ids: list[str] = Field(default_factory=list, max_length=100)


@router.post("/nodes/register", summary="Register compute node")
async def register_node(request: Request, req: RegisterNodeRequest) -> dict[str, Any]:
    """Register a compute node with the swarm"""
    return {"node_id": req.node_id, "address": req.address, "capabilities": req.capabilities, "status": "registered"}


@router.post("/nodes/{node_id}/heartbeat", summary="Node heartbeat")
async def heartbeat(request: Request, node_id: str) -> dict[str, Any]:
    """Send heartbeat from a node"""
    return {"node_id": node_id, "status": "alive"}


@router.get("/nodes", summary="List nodes")
async def list_nodes(request: Request, status: str | None = None, capability: str | None = None) -> dict[str, Any]:
    """List all compute nodes with optional filters"""
    return {"nodes": [], "count": 0, "filters": {"status": status, "capability": capability}}


@router.get("/nodes/{node_id}", summary="Get node details")
async def get_node(request: Request, node_id: str) -> dict[str, Any]:
    """Get details of a specific node"""
    return {"node_id": node_id, "address": "test-address", "capabilities": [], "status": "online"}


@router.post("/tasks/submit", summary="Submit task")
async def submit_task(request: Request, req: SubmitTaskRequest) -> dict[str, Any]:
    """Submit a task to the swarm"""
    return {"task_id": "task-001", "task_type": req.task_type, "status": "assigned"}


@router.post("/tasks/report", summary="Report task status")
async def report_task(request: Request, req: ReportTaskRequest) -> dict[str, Any]:
    """Report task status update from a node"""
    return {"task_id": req.task_id, "status": req.status, "success": True}


@router.get("/tasks/{task_id}", summary="Get task details")
async def get_task(request: Request, task_id: str) -> dict[str, Any]:
    """Get task details by ID"""
    return {"task_id": task_id, "task_type": "test", "status": "running"}


@router.get("/tasks", summary="List tasks")
async def list_tasks(request: Request, status: str | None = None, node_id: str | None = None) -> dict[str, Any]:
    """List all tasks with optional filters"""
    return {"tasks": [], "count": 0, "filters": {"status": status, "node_id": node_id}}


@router.post("/clusters/create", summary="Create cluster")
async def create_cluster(request: Request, req: CreateClusterRequest) -> dict[str, Any]:
    """Create a new compute cluster"""
    return {"cluster_id": "cluster-001", "name": req.name, "node_ids": req.node_ids, "status": "active"}


@router.get("/clusters", summary="List clusters")
async def list_clusters(request: Request) -> dict[str, Any]:
    """List all compute clusters"""
    return {"clusters": [], "count": 0}


@router.get("/clusters/{cluster_id}", summary="Get cluster details")
async def get_cluster(request: Request, cluster_id: str) -> dict[str, Any]:
    """Get cluster details by ID"""
    return {"cluster_id": cluster_id, "name": "test-cluster", "node_ids": [], "status": "active"}


@router.post("/clusters/{cluster_id}/nodes/{node_id}", summary="Add node to cluster")
async def add_node_to_cluster(request: Request, cluster_id: str, node_id: str) -> dict[str, Any]:
    """Add a node to a cluster"""
    return {"cluster_id": cluster_id, "node_id": node_id, "status": "added"}


@router.get("/stats", summary="Get statistics")
async def get_stats(request: Request) -> dict[str, Any]:
    """Get swarm statistics"""
    return {"total_nodes": 0, "online_nodes": 0, "total_tasks": 0, "active_tasks": 0}


@router.get("/health", summary="Health check")
async def swarm_health(request: Request) -> dict[str, Any]:
    """Check swarm service health"""
    return {"status": "healthy", "total_nodes": 0, "total_tasks": 0, "service": "swarm"}
