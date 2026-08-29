"""
Edge API CLI Commands
Commands for interacting with the Edge API service
"""

from decimal import Decimal

import click
import httpx

from ..config import get_config
from ..utils import DECIMAL, error, info, output, success, warning
from ..utils.http_client import AITBCHTTPClient, NetworkError, get_logger

# Initialize logger
logger = get_logger(__name__)


@click.group(
    epilog="""Examples:

  aitbc edge status

  aitbc edge island list"""
)
def edge():
    """Edge API commands for island, GPU, database, serve, and metrics operations."""
    pass


@edge.command(
    epilog="""Examples:

  aitbc edge status

  aitbc edge status --output json"""
)
@click.pass_context
def status(ctx):
    """Get edge status from the coordinator API."""
    config = get_config()

    try:
        http_client = AITBCHTTPClient(base_url=config.agent_coordinator_url, timeout=10)
        status_data = http_client.get("/edge-gpu/metrics")
        success("Edge Status:")
        output(status_data, ctx.obj.get("output_format", "table"))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error fetching edge status: {e}")


@edge.command(
    epilog="""Examples:

  aitbc edge balance

  aitbc edge balance --output json"""
)
@click.pass_context
def balance(ctx):
    """Get edge wallet balance from the coordinator API."""
    config = get_config()

    try:
        http_client = AITBCHTTPClient(base_url=config.agent_coordinator_url, timeout=10)
        balance_data = http_client.get("/edge-gpu/balance")
        success("Edge Wallet Balance:")
        output(balance_data, ctx.obj.get("output_format", "table"))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error fetching edge balance: {e}")


@edge.command(
    epilog="""Examples:

  aitbc edge transfer --to-address 0x... --amount 100

  aitbc edge transfer --to-address 0x... --amount 100 --note payment"""
)
@click.option("--to-address", "to_address", required=True, help="Destination address.")
@click.option("--amount", "amount", required=True, type=DECIMAL, help="Amount of AIT.")
@click.option("--note", help="Transfer note")
@click.pass_context
def transfer(ctx, to_address: str, amount: Decimal, note: str | None):
    """Transfer edge tokens to another address with an optional note."""
    config = get_config()

    try:
        http_client = AITBCHTTPClient(base_url=config.agent_coordinator_url, timeout=10)
        transfer_data = {"to_address": to_address, "amount": str(amount)}
        if note:
            transfer_data["note"] = note

        result = http_client.post("/edge-gpu/transfer", json=transfer_data)
        success(f"Transfer of {amount} to {to_address} submitted")
        output(result, ctx.obj.get("output_format", "table"))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error executing transfer: {e}")


def get_edge_client():
    """Get Edge API HTTP client"""
    config = get_config()
    base_url = f"http://{config.edge_api_host}:{config.edge_api_port}"
    return httpx.Client(base_url=base_url, timeout=30.0)


@edge.group(
    epilog="""Examples:

  aitbc edge island list

  aitbc edge island get --island-id island-1"""
)
def island():
    """Manage and query edge islands, including join, leave, bridge, and list."""
    pass


@island.command(
    epilog="""Examples:

  aitbc edge island join --island-id island-1 --island-name test --chain-id ait-mainnet --role follower

  aitbc edge island join --island-id island-1 --island-name hub --chain-id ait-mainnet --role hub --is-hub"""
)
@click.option("--island-id", "island_id", required=True, help="The Island id.")
@click.option("--island-name", "island_name", required=True, help="The Island name.")
@click.option("--chain-id", "chain_id", required=True, help="The Chain id.")
@click.option("--role", default="compute-provider", help="Island role")
@click.option("--is-hub", is_flag=True, help="Mark as hub node")
def join(island_id: str, island_name: str, chain_id: str, role: str, is_hub: bool):
    """Join an island with the given ID, name, chain, and role."""
    try:
        client = get_edge_client()
        response = client.post(
            "/v1/islands/join",
            json={"island_id": island_id, "island_name": island_name, "chain_id": chain_id, "role": role, "is_hub": is_hub},
        )
        response.raise_for_status()
        result = response.json()

        if result.get("success"):
            success(f"Successfully joined island {island_id}")
            output(result)
        else:
            error(f"Failed to join island: {result.get('message', 'Unknown error')}")
    except Exception as e:
        error(f"Error joining island: {str(e)}")


@island.command(
    epilog="""Examples:

  aitbc edge island leave --island-id island-1"""
)
@click.option("--island-id", "island_id", required=True, help="The Island id.")
def leave(island_id: str):
    """Leave an island by its ID."""
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


@island.command(
    name="list",
    epilog="""Examples:

  aitbc edge island list

  aitbc edge island list --output json""",
)
def list_islands():
    """List all registered edge islands and their basic info."""
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


@island.command(
    epilog="""Examples:

  aitbc edge island get --island-id island-1

  aitbc edge island get --island-id island-1 --output json"""
)
@click.option("--island-id", "island_id", required=True, help="The Island id.")
def get(island_id: str):
    """Get details of a specific edge island."""
    try:
        client = get_edge_client()
        response = client.get(f"/v1/islands/{island_id}")
        response.raise_for_status()
        result = response.json()
        output(result)
    except Exception as e:
        error(f"Error getting island details: {str(e)}")


@island.command(
    epilog="""Examples:

  aitbc edge island bridge --target-island-id island-2

  aitbc edge island bridge --target-island-id island-2 --output json"""
)
@click.option("--target-island-id", "target_island_id", required=True, help="The Target island id.")
def bridge(target_island_id: str):
    """Request a bridge to another island."""
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


@edge.group(
    epilog="""Examples:

  aitbc edge gpu list-gpus

  aitbc edge gpu get-gpu --gpu-id gpu-1"""
)
def gpu():
    """Manage and query edge GPU resources."""
    pass


@gpu.command(
    epilog="""Examples:

  aitbc edge gpu list-gpus

  aitbc edge gpu list-gpus --edge-optimized --min-memory-gb 16"""
)
@click.option("--architecture", help="Filter by GPU architecture")
@click.option("--edge-optimized", is_flag=True, help="Filter edge-optimized GPUs")
@click.option("--min-memory-gb", type=int, help="Minimum memory in GB")
def list_gpus(architecture: str | None, edge_optimized: bool, min_memory_gb: int | None):
    """List available edge GPUs with optional architecture and memory filters."""
    try:
        client = get_edge_client()
        params: dict[str, str | int | bool] = {}
        if architecture:
            params["architecture"] = architecture
        if edge_optimized:
            params["edge_optimized"] = str(edge_optimized)
        if min_memory_gb:
            params["min_memory_gb"] = str(min_memory_gb)

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


@gpu.command(
    epilog="""Examples:

  aitbc edge gpu get-gpu --gpu-id gpu-1

  aitbc edge gpu get-gpu --gpu-id gpu-1 --output json"""
)
@click.option("--gpu-id", "gpu_id", required=True, help="The Gpu id.")
def get_gpu(gpu_id: str):
    """Get details of a specific edge GPU."""
    try:
        client = get_edge_client()
        response = client.get(f"/v1/gpu/{gpu_id}")
        response.raise_for_status()
        result = response.json()
        output(result)
    except Exception as e:
        error(f"Error getting GPU details: {str(e)}")


@gpu.command(
    epilog="""Examples:

  aitbc edge gpu remove-gpu --gpu-id gpu-1"""
)
@click.option("--gpu-id", "gpu_id", required=True, help="The Gpu id.")
def remove_gpu(gpu_id: str):
    """Remove a GPU from the listing."""
    try:
        client = get_edge_client()
        response = client.delete(f"/v1/gpu/{gpu_id}")
        response.raise_for_status()
        result = response.json()
        success(result.get("message", f"GPU {gpu_id} removed"))
    except Exception as e:
        error(f"Error removing GPU: {str(e)}")


@gpu.command(
    epilog="""Examples:

  aitbc edge gpu scan-gpus --miner-id miner-1

  aitbc edge gpu scan-gpus --miner-id miner-1 --output json"""
)
@click.option("--miner-id", "miner_id", required=True, help="The Miner id.")
def scan_gpus(miner_id: str):
    """Scan GPUs for a miner by miner ID."""
    try:
        client = get_edge_client()
        response = client.post("/v1/gpu/scan", json={"miner_id": miner_id})
        response.raise_for_status()
        result = response.json()
        success(f"GPU scan initiated for miner {miner_id}")
        output(result)
    except Exception as e:
        error(f"Error scanning GPUs: {str(e)}")


@gpu.command(
    epilog="""Examples:

  aitbc edge gpu gpu-metrics --gpu-id gpu-1

  aitbc edge gpu gpu-metrics --gpu-id gpu-1 --limit 50"""
)
@click.option("--gpu-id", "gpu_id", required=True, help="The Gpu id.")
@click.option("--limit", type=int, default=100, help="Number of metrics to return")
def gpu_metrics(gpu_id: str, limit: int):
    """Get metrics for a specific edge GPU."""
    try:
        client = get_edge_client()
        response = client.get(f"/v1/gpu/{gpu_id}/metrics", params={"limit": limit})
        response.raise_for_status()
        result = response.json()
        output(result)
    except Exception as e:
        error(f"Error getting GPU metrics: {str(e)}")


@edge.group(
    epilog="""Examples:

  aitbc edge database list-dbs

  aitbc edge database init-db --database-id db-1 --island-id island-1 --capacity-gb 100"""
)
def database():
    """Initialize, list, get, delete, and sync edge databases."""
    pass


@database.command(
    epilog="""Examples:

  aitbc edge database init-db --database-id db-1 --island-id island-1 --capacity-gb 100"""
)
@click.option("--database-id", "database_id", required=True, help="The Database id.")
@click.option("--island-id", "island_id", required=True, help="The Island id.")
@click.option("--capacity-gb", "capacity_gb", required=True, type=int, help="The Capacity gb.")
def init_db(database_id: str, island_id: str, capacity_gb: int):
    """Initialize a new edge database on an island."""
    try:
        client = get_edge_client()
        response = client.post(
            "/v1/database/init", json={"database_id": database_id, "island_id": island_id, "capacity_gb": capacity_gb}
        )
        response.raise_for_status()
        result = response.json()

        if result.get("success"):
            success(f"Database {database_id} initialized")
            output(result)
        else:
            error(f"Failed to initialize database: {result.get('message', 'Unknown error')}")
    except Exception as e:
        error(f"Error initializing database: {str(e)}")


@database.command(
    epilog="""Examples:

  aitbc edge database list-dbs

  aitbc edge database list-dbs --island-id island-1"""
)
@click.option("--island-id", help="Filter by island ID")
def list_dbs(island_id: str | None):
    """List edge databases, optionally filtered by island."""
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


@database.command(
    epilog="""Examples:

  aitbc edge database get-db --database-id db-1

  aitbc edge database get-db --database-id db-1 --output json"""
)
@click.option("--database-id", "database_id", required=True, help="The Database id.")
def get_db(database_id: str):
    """Get details of a specific edge database."""
    try:
        client = get_edge_client()
        response = client.get(f"/v1/database/{database_id}")
        response.raise_for_status()
        result = response.json()
        output(result)
    except Exception as e:
        error(f"Error getting database details: {str(e)}")


@database.command(
    epilog="""Examples:

  aitbc edge database delete-db --database-id db-1"""
)
@click.option("--database-id", "database_id", required=True, help="The Database id.")
def delete_db(database_id: str):
    """Delete an edge database by its ID."""
    try:
        client = get_edge_client()
        response = client.delete(f"/v1/database/{database_id}")
        response.raise_for_status()
        result = response.json()
        success(result.get("message", f"Database {database_id} deleted"))
    except Exception as e:
        error(f"Error deleting database: {str(e)}")


@database.command(
    epilog="""Examples:

  aitbc edge database sync-db --database-id db-1"""
)
@click.option("--database-id", "database_id", required=True, help="The Database id.")
def sync_db(database_id: str):
    """Sync an edge database by its ID."""
    try:
        client = get_edge_client()
        response = client.post(f"/v1/database/{database_id}/sync")

        # V23-17: edge sync is not implemented and answers 501. Surface the server's
        # explanation rather than letting raise_for_status turn it into a bare status line.
        if response.status_code == 501:
            error(response.json().get("detail", "Edge database sync is not implemented"))
            return

        response.raise_for_status()
        result = response.json()

        if not result.get("success"):
            error(f"Failed to sync database: {result.get('message', 'Unknown error')}")
            return

        # A simulated response must not be reported as a completed sync. The service
        # labels it; repeating "synced" here would discard the label one layer up.
        if result.get("simulated"):
            warning(f"Database {database_id}: {result.get('message', 'simulated sync, no data transferred')}")
        else:
            success(f"Database {database_id} synced")
        output(result)
    except Exception as e:
        error(f"Error syncing database: {str(e)}")


@edge.group(
    epilog="""Examples:

  aitbc edge serve list-requests

  aitbc edge serve submit-request --gpu-id gpu-1 --model-name model-1 --input-data '{"x":1}'"""
)
def serve():
    """Submit, list, cancel, and retrieve edge compute requests."""
    pass


@serve.command(
    epilog="""Examples:

  aitbc edge serve submit-request --gpu-id gpu-1 --model-name model-1 --input-data '{"x":1}'

  aitbc edge serve submit-request --gpu-id gpu-1 --model-name model-1 --input-data '{"x":1}' --priority high"""
)
@click.option("--gpu-id", "gpu_id", required=True, help="The Gpu id.")
@click.option("--model-name", "model_name", required=True, help="The Model name.")
@click.option("--input-data", "input_data", required=True, help="The Input data.")
@click.option("--priority", default="normal", help="Request priority")
def submit_request(gpu_id: str, model_name: str, input_data: str, priority: str):
    """Submit a compute request to a GPU with model name and input data."""
    try:
        import json

        client = get_edge_client()
        response = client.post(
            "/v1/serve/requests",
            json={"gpu_id": gpu_id, "model_name": model_name, "input_data": json.loads(input_data), "priority": priority},
        )
        response.raise_for_status()
        result = response.json()

        if result.get("success"):
            success(f"Compute request {result.get('request_id')} submitted")
            output(result)
        else:
            error(f"Failed to submit request: {result.get('message', 'Unknown error')}")
    except Exception as e:
        error(f"Error submitting compute request: {str(e)}")


@serve.command(
    epilog="""Examples:

  aitbc edge serve list-requests

  aitbc edge serve list-requests --gpu-id gpu-1 --status pending"""
)
@click.option("--gpu-id", help="Filter by GPU ID")
@click.option("--status", help="Filter by status")
def list_requests(gpu_id: str | None, status: str | None):
    """List compute requests, optionally filtered by GPU and status."""
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


@serve.command(
    epilog="""Examples:

  aitbc edge serve get-request --request-id req-123

  aitbc edge serve get-request --request-id req-123 --output json"""
)
@click.option("--request-id", "request_id", required=True, help="The Request id.")
def get_request(request_id: str):
    """Get details of a specific compute request."""
    try:
        client = get_edge_client()
        response = client.get(f"/v1/serve/requests/{request_id}")
        response.raise_for_status()
        result = response.json()
        output(result)
    except Exception as e:
        error(f"Error getting request details: {str(e)}")


@serve.command(
    epilog="""Examples:

  aitbc edge serve cancel-request --request-id req-123"""
)
@click.option("--request-id", "request_id", required=True, help="The Request id.")
def cancel_request(request_id: str):
    """Cancel a compute request by its ID."""
    try:
        client = get_edge_client()
        response = client.post(f"/v1/serve/requests/{request_id}/cancel")
        response.raise_for_status()
        result = response.json()
        success(result.get("message", f"Request {request_id} cancelled"))
    except Exception as e:
        error(f"Error cancelling request: {str(e)}")


@serve.command(
    epilog="""Examples:

  aitbc edge serve get-result --request-id req-123

  aitbc edge serve get-result --request-id req-123 --output json"""
)
@click.option("--request-id", "request_id", required=True, help="The Request id.")
def get_result(request_id: str):
    """Get the result of a compute request by its ID."""
    try:
        client = get_edge_client()
        response = client.get(f"/v1/serve/requests/{request_id}/result")
        response.raise_for_status()
        result = response.json()
        output(result)
    except Exception as e:
        error(f"Error getting result: {str(e)}")


@edge.group(
    epilog="""Examples:

  aitbc edge metrics list-metrics

  aitbc edge metrics record --gpu-id gpu-1 --metrics '{"temp":60}'"""
)
def metrics():
    """Record, list, get, and delete edge GPU metrics."""
    pass


@metrics.command(
    epilog="""Examples:

  aitbc edge metrics record --gpu-id gpu-1 --metrics '{"temperature":60}'

  aitbc edge metrics record --gpu-id gpu-1 --metrics '{"memory_used":1024}'"""
)
@click.option("--gpu-id", "gpu_id", required=True, help="The Gpu id.")
@click.option("--metrics", "metrics", required=True, help="The Metrics.")
def record(gpu_id: str, metrics: str):
    """Record metrics for a GPU as a JSON object."""
    try:
        import json

        client = get_edge_client()
        response = client.post("/v1/metrics/", json={"gpu_id": gpu_id, "metrics": json.loads(metrics)})
        response.raise_for_status()
        result = response.json()

        if result.get("success"):
            success(f"Metrics {result.get('metric_id')} recorded")
            output(result)
        else:
            error(f"Failed to record metrics: {result.get('message', 'Unknown error')}")
    except Exception as e:
        error(f"Error recording metrics: {str(e)}")


@metrics.command(
    epilog="""Examples:

  aitbc edge metrics list-metrics

  aitbc edge metrics list-metrics --gpu-id gpu-1 --limit 50"""
)
@click.option("--gpu-id", help="Filter by GPU ID")
@click.option("--limit", type=int, default=100, help="Number of metrics to return")
def list_metrics(gpu_id: str | None, limit: int):
    """List edge metrics, optionally filtered by GPU."""
    try:
        client = get_edge_client()
        params: dict[str, str | int | None] = {"limit": limit}
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


@metrics.command(
    epilog="""Examples:

  aitbc edge metrics get-metric --metric-id metric-123

  aitbc edge metrics get-metric --metric-id metric-123 --output json"""
)
@click.option("--metric-id", "metric_id", required=True, help="The Metric id.")
def get_metric(metric_id: str):
    """Get details of a specific edge metric."""
    try:
        client = get_edge_client()
        response = client.get(f"/v1/metrics/{metric_id}")
        response.raise_for_status()
        result = response.json()
        output(result)
    except Exception as e:
        error(f"Error getting metric details: {str(e)}")


@metrics.command(
    epilog="""Examples:

  aitbc edge metrics delete-metric --metric-id metric-123"""
)
@click.option("--metric-id", "metric_id", required=True, help="The Metric id.")
def delete_metric(metric_id: str):
    """Delete an edge metric by its ID."""
    try:
        client = get_edge_client()
        response = client.delete(f"/v1/metrics/{metric_id}")
        response.raise_for_status()
        result = response.json()
        success(result.get("message", f"Metric {metric_id} deleted"))
    except Exception as e:
        error(f"Error deleting metric: {str(e)}")
