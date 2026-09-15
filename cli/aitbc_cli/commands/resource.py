"""Resource management commands for AITBC CLI.

Wired to the coordinator-api ``/v1/agent-performance`` endpoints:
- ``allocate`` → POST /v1/agent-performance/resources/allocate
- ``status`` → GET /v1/agent-performance/resources
- ``deallocate`` → POST /v1/agent-performance/resources/{id}/deallocate
- ``optimize`` → POST /v1/agent-performance/optimize
"""

from typing import Any

import click

from ..config import get_config
from ..utils import error, output, success
from ..utils.error_handling import abort
from ..utils.http_client import AITBCHTTPClient, NetworkError, auth_client_kwargs, get_logger, service_root_url

logger = get_logger(__name__)

_OPTIMIZATION_TARGETS = ["speed", "accuracy", "efficiency", "cost", "scalability", "reliability"]
_PERFORMANCE_METRICS = [
    "accuracy",
    "precision",
    "recall",
    "f1_score",
    "latency",
    "throughput",
    "resource_efficiency",
    "cost_efficiency",
    "adaptation_speed",
    "generalization",
]


def _client() -> AITBCHTTPClient:
    config = get_config()
    base_url = service_root_url(config.coordinator_api_url, "http://localhost:8203")
    return AITBCHTTPClient(base_url=base_url, timeout=30, **auth_client_kwargs(config_key=config.api_key))


@click.group(
    epilog="""Examples:

  aitbc resource allocate --agent-id agent-1 --cpu-cores 4 --memory-gb 16

  aitbc resource status --agent-id agent-1

  aitbc resource deallocate alloc_12345 --force

  aitbc resource optimize --agent-id agent-1 --target-metric latency"""
)
def resource():
    """Allocate and optimize agent resources through the coordinator API."""
    pass


@resource.command(
    epilog="""Examples:

  aitbc resource allocate --agent-id agent-1 --cpu-cores 4 --memory-gb 16

  aitbc resource allocate --agent-id agent-1 --gpu-count 1 --gpu-memory-gb 24 --priority high"""
)
@click.option("--agent-id", required=True, help="Agent ID to allocate resources for")
@click.option("--cpu-cores", type=float, help="Requested CPU cores")
@click.option("--memory-gb", type=float, help="Requested memory (GB)")
@click.option("--gpu-count", type=float, help="Requested GPU count")
@click.option("--gpu-memory-gb", type=float, help="Requested GPU memory (GB)")
@click.option("--storage-gb", type=float, help="Requested storage (GB)")
@click.option("--network-bandwidth", type=float, help="Requested network bandwidth (Mbps)")
@click.option(
    "--optimization-target",
    type=click.Choice(_OPTIMIZATION_TARGETS),
    default="efficiency",
    help="Optimization target for allocation",
)
@click.option("--priority", type=click.Choice(["low", "normal", "high", "critical"]), default="normal", help="Priority level")
@click.pass_context
def allocate(
    ctx,
    agent_id: str,
    cpu_cores: float | None,
    memory_gb: float | None,
    gpu_count: float | None,
    gpu_memory_gb: float | None,
    storage_gb: float | None,
    network_bandwidth: float | None,
    optimization_target: str,
    priority: str,
):
    """Allocate CPU, memory, GPU, and storage resources for an agent."""
    task_requirements: dict[str, float] = {}
    for key, val in [
        ("cpu_cores", cpu_cores),
        ("memory_gb", memory_gb),
        ("gpu_count", gpu_count),
        ("gpu_memory_gb", gpu_memory_gb),
        ("storage_gb", storage_gb),
        ("network_bandwidth", network_bandwidth),
    ]:
        if val is not None:
            task_requirements[key] = val
    if not task_requirements:
        abort(ctx, "At least one resource requirement must be specified (e.g. --cpu-cores, --gpu-count)")

    payload = {
        "agent_id": agent_id,
        "task_requirements": task_requirements,
        "optimization_target": optimization_target,
        "priority_level": priority,
    }
    try:
        result = _client().post("/v1/agent-performance/resources/allocate", json=payload)
        success(f"Allocated resources for agent {agent_id} (allocation_id: {result.get('allocation_id', 'N/A')})")
        output(result, ctx.obj.get("output_format", "table"))
    except NetworkError as e:
        error(f"Network error: {e}")
        ctx.exit(1)
    except Exception as e:
        error(f"Allocation failed: {e}")
        ctx.exit(1)


@resource.command(
    epilog="""Examples:

  aitbc resource optimize --agent-id agent-1 --target-metric latency --current-latency 100

  aitbc resource optimize --agent-id agent-1 --target-metric accuracy --current-accuracy 0.9"""
)
@click.option("--agent-id", required=True, help="Agent ID to optimize")
@click.option(
    "--target-metric",
    type=click.Choice(_PERFORMANCE_METRICS),
    required=True,
    help="Performance metric to optimize",
)
@click.option("--optimization-type", default="comprehensive", help="Optimization type (comprehensive, targeted, etc.)")
@click.option("--current-accuracy", type=float, help="Current accuracy (0-1)")
@click.option("--current-latency", type=float, help="Current latency (ms)")
@click.option("--current-throughput", type=float, help="Current throughput (req/s)")
@click.pass_context
def optimize(
    ctx,
    agent_id: str,
    target_metric: str,
    optimization_type: str,
    current_accuracy: float | None,
    current_latency: float | None,
    current_throughput: float | None,
):
    """Optimize an agent's performance for a specific target metric."""
    current_performance: dict[str, float] = {}
    if current_accuracy is not None:
        current_performance["accuracy"] = current_accuracy
    if current_latency is not None:
        current_performance["latency"] = current_latency
    if current_throughput is not None:
        current_performance["throughput"] = current_throughput
    if not current_performance:
        abort(ctx, "At least one current performance metric must be specified (e.g. --current-accuracy)")

    payload = {
        "agent_id": agent_id,
        "target_metric": target_metric,
        "current_performance": current_performance,
        "optimization_type": optimization_type,
    }
    try:
        result = _client().post("/v1/agent-performance/optimize", json=payload)
        success(f"Optimization started for agent {agent_id} (optimization_id: {result.get('optimization_id', 'N/A')})")
        output(result, ctx.obj.get("output_format", "table"))
    except NetworkError as e:
        error(f"Network error: {e}")
        ctx.exit(1)
    except Exception as e:
        error(f"Optimization failed: {e}")
        ctx.exit(1)


@resource.command(
    epilog="""Examples:

  aitbc resource status

  aitbc resource status --agent-id agent-1 --status allocated"""
)
@click.option("--agent-id", help="Filter by agent ID")
@click.option(
    "--status",
    "status_filter",
    type=click.Choice(["pending", "allocated", "active", "released", "completed", "failed"]),
    help="Filter by allocation status",
)
@click.option("--limit", type=int, default=50, help="Max allocations to list")
@click.pass_context
def status(ctx, agent_id: str | None, status_filter: str | None, limit: int):
    """List resource allocations from the coordinator API."""
    params: dict[str, Any] = {"limit": limit}
    if agent_id:
        params["agent_id"] = agent_id
    if status_filter:
        params["status"] = status_filter
    try:
        rows: Any = _client().get("/v1/agent-performance/resources", params=params)
        if not isinstance(rows, list):
            rows = [rows] if rows else []
        output(
            [
                {
                    "Allocation": r.get("allocation_id"),
                    "Agent": r.get("agent_id"),
                    "Status": r.get("status"),
                    "CPU": r.get("cpu_cores"),
                    "Mem (GB)": r.get("memory_gb"),
                    "GPU": r.get("gpu_count"),
                    "Allocated": (r.get("allocated_at") or "")[:19],
                }
                for r in rows
            ],
            ctx.obj.get("output_format", "table"),
            title="Resource Allocations",
        )
    except NetworkError as e:
        error(f"Network error: {e}")
        ctx.exit(1)
    except Exception as e:
        error(f"Failed to list allocations: {e}")
        ctx.exit(1)


@resource.command(
    epilog="""Examples:

  aitbc resource deallocate alloc_12345

  aitbc resource deallocate alloc_12345 --force"""
)
@click.argument("allocation_id")
@click.option("--force", is_flag=True, help="Deallocate without confirmation")
@click.pass_context
def deallocate(ctx, allocation_id: str, force: bool):
    """Release a resource allocation by its allocation ID."""
    if not force:
        click.confirm(f"Release allocation {allocation_id}?", abort=True)
    try:
        result = _client().post(f"/v1/agent-performance/resources/{allocation_id}/deallocate")
        success(f"Allocation {allocation_id} released (status: {result.get('status', 'released')})")
        output(result, ctx.obj.get("output_format", "table"))
    except NetworkError as e:
        error(f"Network error: {e}")
        ctx.exit(1)
    except Exception as e:
        error(f"Deallocation failed: {e}")
        ctx.exit(1)
