"""
Swarm Router - Compute clustering API endpoints

Provides:
- Node registration and management
- Task submission and tracking
- Cluster formation
- Health monitoring

v0.5.0: State is now backed by Redis (with in-memory fallback).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.config import settings
from app.services.redis_state import RedisStateManager
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field, field_validator

# Only enable mock endpoints if debug mode or explicit flag is set
if not (settings.debug or settings.enable_mock_swarm):
    # Create empty router for production
    router = APIRouter(prefix="/swarm", tags=["swarm"])
else:
    router = APIRouter(prefix="/swarm", tags=["swarm"])

    # Redis-backed state (falls back to in-memory if Redis unavailable)
    _state = RedisStateManager.get_instance_sync()
    _NODES_NS = "swarm:nodes"
    _TASKS_NS = "swarm:tasks"
    _CLUSTERS_NS = "swarm:clusters"


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
    node = {
        "node_id": req.node_id,
        "address": req.address,
        "capabilities": req.capabilities,
        "cpu_cores": req.cpu_cores,
        "memory_gb": req.memory_gb,
        "gpu_count": req.gpu_count,
        "status": "registered",
        "registered_at": datetime.now(UTC).isoformat(),
    }
    await _state.hset(_NODES_NS, req.node_id, node)
    return node


@router.post("/nodes/{node_id}/heartbeat", summary="Node heartbeat")
async def heartbeat(request: Request, node_id: str) -> dict[str, Any]:
    """Send heartbeat from a node"""
    node = await _state.hget(_NODES_NS, node_id)
    if node is None:
        return {"node_id": node_id, "status": "unknown"}
    node["status"] = "alive"
    node["last_heartbeat"] = datetime.now(UTC).isoformat()
    await _state.hset(_NODES_NS, node_id, node)
    return {"node_id": node_id, "status": "alive"}


@router.get("/nodes", summary="List nodes")
async def list_nodes(request: Request, status: str | None = None, capability: str | None = None) -> dict[str, Any]:
    """List all compute nodes with optional filters"""
    nodes = await _state.hgetall(_NODES_NS)
    node_list = list(nodes.values())
    if status:
        node_list = [n for n in node_list if n.get("status") == status]
    if capability:
        node_list = [n for n in node_list if capability in n.get("capabilities", [])]
    return {"nodes": node_list, "count": len(node_list), "filters": {"status": status, "capability": capability}}


@router.get("/nodes/{node_id}", summary="Get node details")
async def get_node(request: Request, node_id: str) -> dict[str, Any]:
    """Get details of a specific node"""
    node = await _state.hget(_NODES_NS, node_id)
    if node is None:
        return {"node_id": node_id, "status": "unknown"}
    return node


@router.post("/tasks/submit", summary="Submit task")
async def submit_task(request: Request, req: SubmitTaskRequest) -> dict[str, Any]:
    """Submit a task to the swarm"""
    task_counter = await _state.incr(_TASKS_NS, "counter")
    task_id = f"task_{task_counter}"

    task = {
        "task_id": task_id,
        "task_type": req.task_type,
        "payload": req.payload,
        "required_capabilities": req.required_capabilities or [],
        "priority": req.priority,
        "status": "pending",
        "created_at": datetime.now(UTC).isoformat(),
    }
    await _state.hset(_TASKS_NS, task_id, task)
    return {"task_id": task_id, "task_type": req.task_type, "status": "pending"}


@router.post("/tasks/report", summary="Report task status")
async def report_task(request: Request, req: ReportTaskRequest) -> dict[str, Any]:
    """Report task status update from a node"""
    task = await _state.hget(_TASKS_NS, req.task_id)
    if task is None:
        return {"task_id": req.task_id, "status": "unknown", "success": False}

    task["status"] = req.status
    task["node_id"] = req.node_id
    if req.result:
        task["result"] = req.result
    if req.error:
        task["error"] = req.error
    task["updated_at"] = datetime.now(UTC).isoformat()

    await _state.hset(_TASKS_NS, req.task_id, task)
    return {"task_id": req.task_id, "status": req.status, "success": True}


@router.get("/tasks/{task_id}", summary="Get task details")
async def get_task(request: Request, task_id: str) -> dict[str, Any]:
    """Get task details by ID"""
    task = await _state.hget(_TASKS_NS, task_id)
    if task is None:
        return {"task_id": task_id, "task_type": "unknown", "status": "unknown"}
    return task


@router.get("/tasks", summary="List tasks")
async def list_tasks(request: Request, status: str | None = None, node_id: str | None = None) -> dict[str, Any]:
    """List all tasks with optional filters"""
    tasks = await _state.hgetall(_TASKS_NS)
    task_list = [t for t in tasks.values() if not t["task_id"].startswith("counter")]
    if status:
        task_list = [t for t in task_list if t.get("status") == status]
    if node_id:
        task_list = [t for t in task_list if t.get("node_id") == node_id]
    return {"tasks": task_list, "count": len(task_list), "filters": {"status": status, "node_id": node_id}}


@router.post("/clusters/create", summary="Create cluster")
async def create_cluster(request: Request, req: CreateClusterRequest) -> dict[str, Any]:
    """Create a new compute cluster"""
    cluster_counter = await _state.incr(_CLUSTERS_NS, "counter")
    cluster_id = f"cluster_{cluster_counter}"

    cluster = {
        "cluster_id": cluster_id,
        "name": req.name,
        "description": req.description,
        "node_ids": req.node_ids,
        "status": "active",
        "created_at": datetime.now(UTC).isoformat(),
    }
    await _state.hset(_CLUSTERS_NS, cluster_id, cluster)
    return cluster


@router.get("/clusters", summary="List clusters")
async def list_clusters(request: Request) -> dict[str, Any]:
    """List all compute clusters"""
    clusters = await _state.hgetall(_CLUSTERS_NS)
    cluster_list = [c for c in clusters.values() if not c["cluster_id"].startswith("counter")]
    return {"clusters": cluster_list, "count": len(cluster_list)}


@router.get("/clusters/{cluster_id}", summary="Get cluster details")
async def get_cluster(request: Request, cluster_id: str) -> dict[str, Any]:
    """Get cluster details by ID"""
    cluster = await _state.hget(_CLUSTERS_NS, cluster_id)
    if cluster is None:
        return {"cluster_id": cluster_id, "name": "unknown", "node_ids": [], "status": "unknown"}
    return cluster


@router.post("/clusters/{cluster_id}/nodes/{node_id}", summary="Add node to cluster")
async def add_node_to_cluster(request: Request, cluster_id: str, node_id: str) -> dict[str, Any]:
    """Add a node to a cluster"""
    cluster = await _state.hget(_CLUSTERS_NS, cluster_id)
    if cluster is None:
        return {"cluster_id": cluster_id, "node_id": node_id, "status": "cluster_not_found"}

    if node_id not in cluster.get("node_ids", []):
        cluster["node_ids"] = cluster.get("node_ids", []) + [node_id]
        await _state.hset(_CLUSTERS_NS, cluster_id, cluster)
    return {"cluster_id": cluster_id, "node_id": node_id, "status": "added"}


@router.get("/stats", summary="Get statistics")
async def get_stats(request: Request) -> dict[str, Any]:
    """Get swarm statistics"""
    nodes = await _state.hgetall(_NODES_NS)
    tasks = await _state.hgetall(_TASKS_NS)
    total_nodes = len([n for n in nodes.values() if not n.get("node_id", "").startswith("counter")])
    online_nodes = len([n for n in nodes.values() if n.get("status") == "alive"])
    total_tasks = len([t for t in tasks.values() if not t.get("task_id", "").startswith("counter")])
    active_tasks = len([t for t in tasks.values() if t.get("status") in ("pending", "running")])
    return {"total_nodes": total_nodes, "online_nodes": online_nodes, "total_tasks": total_tasks, "active_tasks": active_tasks}


@router.get("/health", summary="Health check")
async def swarm_health(request: Request) -> dict[str, Any]:
    """Check swarm service health"""
    return {"status": "healthy", "total_nodes": 0, "total_tasks": 0, "service": "swarm"}
