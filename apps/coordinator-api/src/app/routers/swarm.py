"""
Swarm Router - Compute clustering API endpoints

Provides:
- Node registration and management
- Task submission and tracking
- Cluster formation
- Health monitoring
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from ..services.swarm_service import get_swarm_service, NodeStatus, TaskStatus
from ..rate_limiting import rate_limit


router = APIRouter(prefix="/swarm", tags=["swarm"])


class RegisterNodeRequest(BaseModel):
    """Request to register a node"""
    node_id: str
    address: str
    capabilities: List[str] = Field(default_factory=list)
    cpu_cores: int = 4
    memory_gb: int = 16
    gpu_count: int = 0


class SubmitTaskRequest(BaseModel):
    """Request to submit a task"""
    task_type: str
    payload: Dict[str, Any]
    required_capabilities: Optional[List[str]] = None
    priority: int = Field(default=1, ge=1, le=10)


class ReportTaskRequest(BaseModel):
    """Request to report task status"""
    task_id: str
    node_id: str
    status: str
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class CreateClusterRequest(BaseModel):
    """Request to create a cluster"""
    name: str
    description: str = ""
    node_ids: List[str] = Field(default_factory=list)


@router.post("/nodes/register", summary="Register compute node")
@rate_limit(rate=20, per=60)
async def register_node(
    request: Request,
    req: RegisterNodeRequest
) -> Dict[str, Any]:
    """Register a compute node with the swarm"""
    try:
        service = get_swarm_service()
        
        node = service.register_node(
            node_id=req.node_id,
            address=req.address,
            capabilities=req.capabilities,
            cpu_cores=req.cpu_cores,
            memory_gb=req.memory_gb,
            gpu_count=req.gpu_count
        )
        
        return {
            "success": True,
            "node": node.to_dict()
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Registration failed: {str(e)}"
        )


@router.post("/nodes/{node_id}/heartbeat", summary="Node heartbeat")
@rate_limit(rate=100, per=60)
async def heartbeat(
    request: Request,
    node_id: str
) -> Dict[str, Any]:
    """Send heartbeat from a node"""
    try:
        service = get_swarm_service()
        
        success = service.heartbeat(node_id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Node {node_id} not found"
            )
        
        return {
            "success": True,
            "node_id": node_id,
            "timestamp": __import__('datetime').datetime.now(
                __import__('datetime').timezone.utc
            ).isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Heartbeat failed: {str(e)}"
        )


@router.get("/nodes", summary="List nodes")
@rate_limit(rate=50, per=60)
async def list_nodes(
    request: Request,
    status: Optional[str] = None,
    capability: Optional[str] = None
) -> Dict[str, Any]:
    """List all compute nodes with optional filters"""
    try:
        service = get_swarm_service()
        
        nodes = service.list_nodes(status=status, capability=capability)
        
        return {
            "nodes": [n.to_dict() for n in nodes],
            "count": len(nodes),
            "filters": {
                "status": status,
                "capability": capability
            }
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list nodes: {str(e)}"
        )


@router.get("/nodes/{node_id}", summary="Get node details")
@rate_limit(rate=100, per=60)
async def get_node(
    request: Request,
    node_id: str
) -> Dict[str, Any]:
    """Get details of a specific node"""
    try:
        service = get_swarm_service()
        
        node = service.get_node(node_id)
        if not node:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Node {node_id} not found"
            )
        
        return node.to_dict()
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get node: {str(e)}"
        )


@router.post("/tasks/submit", summary="Submit task")
@rate_limit(rate=30, per=60)
async def submit_task(
    request: Request,
    req: SubmitTaskRequest
) -> Dict[str, Any]:
    """Submit a task to the swarm"""
    try:
        service = get_swarm_service()
        
        task = service.submit_task(
            task_type=req.task_type,
            payload=req.payload,
            required_capabilities=req.required_capabilities,
            priority=req.priority
        )
        
        return {
            "success": True,
            "task": task.to_dict()
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Task submission failed: {str(e)}"
        )


@router.post("/tasks/report", summary="Report task status")
@rate_limit(rate=100, per=60)
async def report_task(
    request: Request,
    req: ReportTaskRequest
) -> Dict[str, Any]:
    """Report task status update from a node"""
    try:
        service = get_swarm_service()
        
        success = service.report_task_status(
            task_id=req.task_id,
            node_id=req.node_id,
            status=req.status,
            result=req.result,
            error=req.error
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to update task status"
            )
        
        return {
            "success": True,
            "task_id": req.task_id,
            "status": req.status
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Report failed: {str(e)}"
        )


@router.get("/tasks/{task_id}", summary="Get task details")
@rate_limit(rate=100, per=60)
async def get_task(
    request: Request,
    task_id: str
) -> Dict[str, Any]:
    """Get task details by ID"""
    try:
        service = get_swarm_service()
        
        task = service.get_task(task_id)
        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Task {task_id} not found"
            )
        
        return task.to_dict()
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get task: {str(e)}"
        )


@router.get("/tasks", summary="List tasks")
@rate_limit(rate=50, per=60)
async def list_tasks(
    request: Request,
    status: Optional[str] = None,
    node_id: Optional[str] = None
) -> Dict[str, Any]:
    """List all tasks with optional filters"""
    try:
        service = get_swarm_service()
        
        tasks = service.list_tasks(status=status, node_id=node_id)
        
        return {
            "tasks": [t.to_dict() for t in tasks],
            "count": len(tasks),
            "filters": {
                "status": status,
                "node_id": node_id
            }
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list tasks: {str(e)}"
        )


@router.post("/clusters/create", summary="Create cluster")
@rate_limit(rate=10, per=60)
async def create_cluster(
    request: Request,
    req: CreateClusterRequest
) -> Dict[str, Any]:
    """Create a new compute cluster"""
    try:
        service = get_swarm_service()
        
        cluster = service.create_cluster(
            name=req.name,
            description=req.description,
            node_ids=req.node_ids
        )
        
        return {
            "success": True,
            "cluster": cluster.to_dict(service)
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Cluster creation failed: {str(e)}"
        )


@router.get("/clusters", summary="List clusters")
@rate_limit(rate=30, per=60)
async def list_clusters(request: Request) -> Dict[str, Any]:
    """List all compute clusters"""
    try:
        service = get_swarm_service()
        
        clusters = service.list_clusters()
        
        return {
            "clusters": [c.to_dict(service) for c in clusters],
            "count": len(clusters)
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list clusters: {str(e)}"
        )


@router.get("/clusters/{cluster_id}", summary="Get cluster details")
@rate_limit(rate=50, per=60)
async def get_cluster(
    request: Request,
    cluster_id: str
) -> Dict[str, Any]:
    """Get cluster details by ID"""
    try:
        service = get_swarm_service()
        
        cluster = service.get_cluster(cluster_id)
        if not cluster:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cluster {cluster_id} not found"
            )
        
        return cluster.to_dict(service)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get cluster: {str(e)}"
        )


@router.post("/clusters/{cluster_id}/nodes/{node_id}", summary="Add node to cluster")
@rate_limit(rate=20, per=60)
async def add_node_to_cluster(
    request: Request,
    cluster_id: str,
    node_id: str
) -> Dict[str, Any]:
    """Add a node to a cluster"""
    try:
        service = get_swarm_service()
        
        success = service.add_node_to_cluster(cluster_id, node_id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to add node to cluster"
            )
        
        return {
            "success": True,
            "cluster_id": cluster_id,
            "node_id": node_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to add node: {str(e)}"
        )


@router.get("/stats", summary="Get statistics")
@rate_limit(rate=30, per=60)
async def get_stats(request: Request) -> Dict[str, Any]:
    """Get swarm statistics"""
    try:
        service = get_swarm_service()
        
        return service.get_stats()
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get stats: {str(e)}"
        )


@router.get("/health", summary="Health check")
async def health_check(request: Request) -> Dict[str, Any]:
    """Check swarm service health"""
    try:
        service = get_swarm_service()
        stats = service.get_stats()
        
        return {
            "status": "healthy",
            "nodes_online": stats["nodes"]["online"],
            "total_tasks": stats["tasks"]["total"],
            "avg_load": stats["avg_load"]
        }
        
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }
