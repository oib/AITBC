"""
Edge API CLI Commands
Commands for interacting with the Edge API service
"""

import click
import httpx
from typing import Optional
from ..utils import output, error, success, info, warning
from ..config import get_config

# Initialize logger
logger = None


@click.group()
def edge():
    """Edge API commands for island, GPU, database, serve, and metrics operations"""
    pass


def get_edge_client():
    """Get Edge API HTTP client"""
    config = get_config()
    base_url = f"http://{config.edge_api_host}:{config.edge_api_port}"
    return httpx.Client(base_url=base_url, timeout=30.0)


@edge.group()
def island():
    """Island operations via Edge API"""
    pass


@island.command()
@click.argument('island_id')
@click.argument('island_name')
@click.argument('chain_id')
@click.option('--role', default='compute-provider', help='Island role')
@click.option('--is-hub', is_flag=True, help='Mark as hub node')
def join(island_id: str, island_name: str, chain_id: str, role: str, is_hub: bool):
    """Join an island"""
    try:
        client = get_edge_client()
        response = client.post("/v1/islands/join", json={
            "island_id": island_id,
            "island_name": island_name,
            "chain_id": chain_id,
            "role": role,
            "is_hub": is_hub
        })
        response.raise_for_status()
        result = response.json()
        
        if result.get("success"):
            success(f"Successfully joined island {island_id}")
            output(result)
        else:
            error(f"Failed to join island: {result.get('message', 'Unknown error')}")
    except Exception as e:
        error(f"Error joining island: {str(e)}")


@island.command()
@click.argument('island_id')
def leave(island_id: str):
    """Leave an island"""
    try:
        client = get_edge_client()
        response = client.post("/v1/islands/leave", json={"island_id": island_id})
        response.raise_for_status()
        result = response.json()
        
        if result.get("success"):
            success(f"Successfully left island {island_id}")
            output(result)
        else:
            error(f"Failed to leave island: {result.get('message', 'Unknown error')}")
    except Exception as e:
        error(f"Error leaving island: {str(e)}")


@island.command(name='list')
def list_islands():
    """List all islands"""
    try:
        client = get_edge_client()
        response = client.get("/v1/islands/")
        response.raise_for_status()
        result = response.json()
        
        islands = result.get("islands", [])
        if islands:
            output(islands)
        else:
            info("No islands found")
    except Exception as e:
        error(f"Error listing islands: {str(e)}")


@island.command()
@click.argument('island_id')
def get(island_id: str):
    """Get island details"""
    try:
        client = get_edge_client()
        response = client.get(f"/v1/islands/{island_id}")
        response.raise_for_status()
        result = response.json()
        output(result)
    except Exception as e:
        error(f"Error getting island details: {str(e)}")


@island.command()
@click.argument('target_island_id')
def bridge(target_island_id: str):
    """Request bridge to another island"""
    try:
        client = get_edge_client()
        response = client.post("/v1/islands/bridge", json={"target_island_id": target_island_id})
        response.raise_for_status()
        result = response.json()
        
        if result.get("success"):
            success(f"Bridge request submitted to {target_island_id}")
            output(result)
        else:
            error(f"Failed to request bridge: {result.get('message', 'Unknown error')}")
    except Exception as e:
        error(f"Error requesting bridge: {str(e)}")


@edge.group()
def gpu():
    """GPU operations via Edge API"""
    pass


@gpu.command()
@click.option('--architecture', help='Filter by GPU architecture')
@click.option('--edge-optimized', is_flag=True, help='Filter edge-optimized GPUs')
@click.option('--min-memory-gb', type=int, help='Minimum memory in GB')
def list_gpus(architecture: Optional[str], edge_optimized: bool, min_memory_gb: Optional[int]):
    """List available GPUs"""
    try:
        client = get_edge_client()
        params = {}
        if architecture:
            params["architecture"] = architecture
        if edge_optimized:
            params["edge_optimized"] = edge_optimized
        if min_memory_gb:
            params["min_memory_gb"] = min_memory_gb
        
        response = client.get("/v1/gpu/", params=params)
        response.raise_for_status()
        result = response.json()
        
        gpus = result.get("gpus", [])
        if gpus:
            output(gpus)
        else:
            info("No GPUs found")
    except Exception as e:
        error(f"Error listing GPUs: {str(e)}")


@gpu.command()
@click.argument('gpu_id')
def get_gpu(gpu_id: str):
    """Get GPU details"""
    try:
        client = get_edge_client()
        response = client.get(f"/v1/gpu/{gpu_id}")
        response.raise_for_status()
        result = response.json()
        output(result)
    except Exception as e:
        error(f"Error getting GPU details: {str(e)}")


@gpu.command()
@click.argument('gpu_id')
def remove_gpu(gpu_id: str):
    """Remove GPU from listing"""
    try:
        client = get_edge_client()
        response = client.delete(f"/v1/gpu/{gpu_id}")
        response.raise_for_status()
        result = response.json()
        success(result.get("message", f"GPU {gpu_id} removed"))
    except Exception as e:
        error(f"Error removing GPU: {str(e)}")


@gpu.command()
@click.argument('miner_id')
def scan_gpus(miner_id: str):
    """Scan GPUs for a miner"""
    try:
        client = get_edge_client()
        response = client.post("/v1/gpu/scan", json={"miner_id": miner_id})
        response.raise_for_status()
        result = response.json()
        success(f"GPU scan initiated for miner {miner_id}")
        output(result)
    except Exception as e:
        error(f"Error scanning GPUs: {str(e)}")


@gpu.command()
@click.argument('gpu_id')
@click.option('--limit', type=int, default=100, help='Number of metrics to return')
def gpu_metrics(gpu_id: str, limit: int):
    """Get GPU metrics"""
    try:
        client = get_edge_client()
        response = client.get(f"/v1/gpu/{gpu_id}/metrics", params={"limit": limit})
        response.raise_for_status()
        result = response.json()
        output(result)
    except Exception as e:
        error(f"Error getting GPU metrics: {str(e)}")


@edge.group()
def database():
    """Database operations via Edge API"""
    pass


@database.command()
@click.argument('database_id')
@click.argument('island_id')
@click.argument('capacity_gb', type=int)
def init_db(database_id: str, island_id: str, capacity_gb: int):
    """Initialize edge database"""
    try:
        client = get_edge_client()
        response = client.post("/v1/database/init", json={
            "database_id": database_id,
            "island_id": island_id,
            "capacity_gb": capacity_gb
        })
        response.raise_for_status()
        result = response.json()
        
        if result.get("success"):
            success(f"Database {database_id} initialized")
            output(result)
        else:
            error(f"Failed to initialize database: {result.get('message', 'Unknown error')}")
    except Exception as e:
        error(f"Error initializing database: {str(e)}")


@database.command()
@click.option('--island-id', help='Filter by island ID')
def list_dbs(island_id: Optional[str]):
    """List edge databases"""
    try:
        client = get_edge_client()
        params = {}
        if island_id:
            params["island_id"] = island_id
        
        response = client.get("/v1/database/", params=params)
        response.raise_for_status()
        result = response.json()
        
        databases = result.get("databases", [])
        if databases:
            output(databases)
        else:
            info("No databases found")
    except Exception as e:
        error(f"Error listing databases: {str(e)}")


@database.command()
@click.argument('database_id')
def get_db(database_id: str):
    """Get database details"""
    try:
        client = get_edge_client()
        response = client.get(f"/v1/database/{database_id}")
        response.raise_for_status()
        result = response.json()
        output(result)
    except Exception as e:
        error(f"Error getting database details: {str(e)}")


@database.command()
@click.argument('database_id')
def delete_db(database_id: str):
    """Delete database"""
    try:
        client = get_edge_client()
        response = client.delete(f"/v1/database/{database_id}")
        response.raise_for_status()
        result = response.json()
        success(result.get("message", f"Database {database_id} deleted"))
    except Exception as e:
        error(f"Error deleting database: {str(e)}")


@database.command()
@click.argument('database_id')
def sync_db(database_id: str):
    """Sync database"""
    try:
        client = get_edge_client()
        response = client.post(f"/v1/database/{database_id}/sync")
        response.raise_for_status()
        result = response.json()
        
        if result.get("success"):
            success(f"Database {database_id} synced")
            output(result)
        else:
            error(f"Failed to sync database: {result.get('message', 'Unknown error')}")
    except Exception as e:
        error(f"Error syncing database: {str(e)}")


@edge.group()
def serve():
    """Serve operations via Edge API"""
    pass


@serve.command()
@click.argument('gpu_id')
@click.argument('model_name')
@click.argument('input_data')
@click.option('--priority', default='normal', help='Request priority')
def submit_request(gpu_id: str, model_name: str, input_data: str, priority: str):
    """Submit compute request"""
    try:
        import json
        client = get_edge_client()
        response = client.post("/v1/serve/requests", json={
            "gpu_id": gpu_id,
            "model_name": model_name,
            "input_data": json.loads(input_data),
            "priority": priority
        })
        response.raise_for_status()
        result = response.json()
        
        if result.get("success"):
            success(f"Compute request {result.get('request_id')} submitted")
            output(result)
        else:
            error(f"Failed to submit request: {result.get('message', 'Unknown error')}")
    except Exception as e:
        error(f"Error submitting compute request: {str(e)}")


@serve.command()
@click.option('--gpu-id', help='Filter by GPU ID')
@click.option('--status', help='Filter by status')
def list_requests(gpu_id: Optional[str], status: Optional[str]):
    """List compute requests"""
    try:
        client = get_edge_client()
        params = {}
        if gpu_id:
            params["gpu_id"] = gpu_id
        if status:
            params["status"] = status
        
        response = client.get("/v1/serve/requests", params=params)
        response.raise_for_status()
        result = response.json()
        
        requests = result.get("requests", [])
        if requests:
            output(requests)
        else:
            info("No requests found")
    except Exception as e:
        error(f"Error listing requests: {str(e)}")


@serve.command()
@click.argument('request_id')
def get_request(request_id: str):
    """Get compute request details"""
    try:
        client = get_edge_client()
        response = client.get(f"/v1/serve/requests/{request_id}")
        response.raise_for_status()
        result = response.json()
        output(result)
    except Exception as e:
        error(f"Error getting request details: {str(e)}")


@serve.command()
@click.argument('request_id')
def cancel_request(request_id: str):
    """Cancel compute request"""
    try:
        client = get_edge_client()
        response = client.post(f"/v1/serve/requests/{request_id}/cancel")
        response.raise_for_status()
        result = response.json()
        success(result.get("message", f"Request {request_id} cancelled"))
    except Exception as e:
        error(f"Error cancelling request: {str(e)}")


@serve.command()
@click.argument('request_id')
def get_result(request_id: str):
    """Get compute result"""
    try:
        client = get_edge_client()
        response = client.get(f"/v1/serve/requests/{request_id}/result")
        response.raise_for_status()
        result = response.json()
        output(result)
    except Exception as e:
        error(f"Error getting result: {str(e)}")


@edge.group()
def metrics():
    """Metrics operations via Edge API"""
    pass


@metrics.command()
@click.argument('gpu_id')
@click.argument('metrics')
def record(gpu_id: str, metrics: str):
    """Record edge metrics"""
    try:
        import json
        client = get_edge_client()
        response = client.post("/v1/metrics/", json={
            "gpu_id": gpu_id,
            "metrics": json.loads(metrics)
        })
        response.raise_for_status()
        result = response.json()
        
        if result.get("success"):
            success(f"Metrics {result.get('metric_id')} recorded")
            output(result)
        else:
            error(f"Failed to record metrics: {result.get('message', 'Unknown error')}")
    except Exception as e:
        error(f"Error recording metrics: {str(e)}")


@metrics.command()
@click.option('--gpu-id', help='Filter by GPU ID')
@click.option('--limit', type=int, default=100, help='Number of metrics to return')
def list_metrics(gpu_id: Optional[str], limit: int):
    """List edge metrics"""
    try:
        client = get_edge_client()
        params = {"limit": limit}
        if gpu_id:
            params["gpu_id"] = gpu_id
        
        response = client.get("/v1/metrics/", params=params)
        response.raise_for_status()
        result = response.json()
        
        metrics = result.get("metrics", [])
        if metrics:
            output(metrics)
        else:
            info("No metrics found")
    except Exception as e:
        error(f"Error listing metrics: {str(e)}")


@metrics.command()
@click.argument('metric_id')
def get_metric(metric_id: str):
    """Get metric details"""
    try:
        client = get_edge_client()
        response = client.get(f"/v1/metrics/{metric_id}")
        response.raise_for_status()
        result = response.json()
        output(result)
    except Exception as e:
        error(f"Error getting metric details: {str(e)}")


@metrics.command()
@click.argument('metric_id')
def delete_metric(metric_id: str):
    """Delete metric"""
    try:
        client = get_edge_client()
        response = client.delete(f"/v1/metrics/{metric_id}")
        response.raise_for_status()
        result = response.json()
        success(result.get("message", f"Metric {metric_id} deleted"))
    except Exception as e:
        error(f"Error deleting metric: {str(e)}")
