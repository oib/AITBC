"""
Resource management commands for AITBC CLI
"""

import json
import os
import time

import click

from ..utils.http_client import AITBCHTTPClient, NetworkError, get_logger

from ..config import get_config
from ..utils import error, output, success

logger = get_logger(__name__)


@click.group()
def resource():
    """Resource management commands (EXPERIMENTAL - use --mock for testing)"""
    pass


@resource.command()
@click.option('--resource-type', required=True, help='Type of resource (gpu, cpu, storage)')
@click.option('--quantity', type=int, required=True, help='Quantity of resources')
@click.option('--priority', type=click.Choice(['low', 'medium', 'high']), default='medium', help='Allocation priority')
@click.option('--mock', is_flag=True, help='Use mock data for experimental command')
def allocate(resource_type: str, quantity: int, priority: str, mock: bool):
    """Allocate resources (EXPERIMENTAL)"""
    try:
        import httpx
        
        config = get_config()
        coordinator_url = config.get("coordinator_url", "http://localhost:8203")
        api_key = config.get("coordinator_api_key", os.environ.get("COORDINATOR_API_KEY"))
        
        if not mock:
            # Implement actual resource allocation via coordinator API
            allocation_payload = {
                "resource_type": resource_type,
                "quantity": quantity,
                "priority": priority
            }
            
            headers = {}
            if api_key:
                headers["X-API-Key"] = api_key
            
            response = httpx.post(
                f"{coordinator_url}/v1/resources/allocate",
                json=allocation_payload,
                headers=headers
            )
            
            if response.status_code != 200:
                error(f"Failed to allocate resources: {response.text}")
                return 1
            
            result = response.json()
            success(f"Allocated {quantity} {resource_type} with {priority} priority")
            click.echo(f"Allocation ID: {result.get('allocation_id')}")
            click.echo(f"Status: {result.get('status', 'Allocated')}")
            click.echo(f"Cost per hour: {result.get('cost_per_hour', 25)} AIT")
            return 0
        else:
            # Mock mode
            success(f"Allocate {quantity} {resource_type} with {priority} priority")
            click.echo(f"Allocation ID: alloc_{int(time.time())}")
            click.echo("Status: Allocated (mock)")
            click.echo("Cost per hour: 25 AIT")
            return 0
            
    except Exception as e:
        error(f"Error allocating resources: {e}")
        return 1


@resource.command()
@click.option('--resource-id', help='Specific resource ID')
@click.option('--format', type=click.Choice(['table', 'json']), default='table', help='Output format')
@click.option('--mock', is_flag=True, help='Use mock data for experimental command')
def list(resource_id: str | None, format: str, mock: bool):
    """List allocated resources (EXPERIMENTAL)"""
    if not mock:
        error("[EXPERIMENTAL] This command uses placeholder logic. Use --mock for testing.")
        click.echo("To proceed with mock data, run: aitbc resource list --mock")
        return 1

    success("Allocated resources:")
    resources = [
        {"type": "gpu", "allocated": 4, "available": 8, "efficiency": "78.5%"},
        {"type": "cpu", "allocated": "45.2%", "available": "54.8%", "efficiency": "82.1%"},
        {"type": "storage", "allocated": "45GB", "available": "55GB", "efficiency": "90.0%"}
    ]

    if format == 'json':
        click.echo(json.dumps(resources, indent=2))
    else:
        for res in resources:
            click.echo(f"  - {res['type'].upper()}: {res['allocated']} allocated, {res['available']} available ({res['efficiency']})")
    return 0


@resource.command()
@click.argument('resource_id')
@click.option('--mock', is_flag=True, help='Use mock data for experimental command')
def release(resource_id: str, mock: bool):
    """Release allocated resources (EXPERIMENTAL)"""
    try:
        import httpx
        
        config = get_config()
        coordinator_url = config.get("coordinator_url", "http://localhost:8203")
        api_key = config.get("coordinator_api_key", os.environ.get("COORDINATOR_API_KEY"))
        
        if not mock:
            # Implement actual resource release via coordinator API
            headers = {}
            if api_key:
                headers["X-API-Key"] = api_key
            
            response = httpx.post(
                f"{coordinator_url}/v1/resources/{resource_id}/release",
                headers=headers
            )
            
            if response.status_code != 200:
                error(f"Failed to release resource: {response.text}")
                return 1
            
            success(f"Release resource {resource_id}")
            click.echo("Status: Released")
            return 0
        else:
            # Mock mode
            success(f"Release resource {resource_id}")
            click.echo("Status: Released (mock)")
            return 0
            
    except Exception as e:
        error(f"Error releasing resource: {e}")
        return 1


@resource.command()
@click.option('--format', type=click.Choice(['table', 'json']), default='table', help='Output format')
@click.option('--mock', is_flag=True, help='Use mock data for experimental command')
def utilization(format: str, mock: bool):
    """Get resource utilization metrics (EXPERIMENTAL)"""
    if not mock:
        error("[EXPERIMENTAL] This command uses placeholder logic. Use --mock for testing.")
        click.echo("To proceed with mock data, run: aitbc resource utilization --mock")
        return 1

    success("Resource utilization:")
    metrics = {
        "cpu_utilization": "45.2%",
        "memory_usage": "2.1GB / 8GB (26%)",
        "storage_available": "45GB / 100GB",
        "network_bandwidth": "120Mbps / 1Gbps",
        "active_agents": 3,
        "resource_efficiency": "78.5%"
    }

    if format == 'json':
        click.echo(json.dumps(metrics, indent=2))
    else:
        for key, value in metrics.items():
            click.echo(f"  {key}: {value}")
    return 0


@resource.command()
@click.option('--target', default='all', help='Optimization target (all, cpu, gpu, memory)')
@click.option('--agent-id', help='Specific agent ID')
@click.option('--mock', is_flag=True, help='Use mock data for experimental command')
def optimize(target: str, agent_id: str | None, mock: bool):
    """Optimize resource allocation (EXPERIMENTAL)"""
    if not mock:
        error("[EXPERIMENTAL] This command uses placeholder logic. Use --mock for testing.")
        click.echo("To proceed with mock data, run: aitbc resource optimize --mock")
        return 1

    success(f"Optimize resources for target: {target}")
    if agent_id:
        click.echo(f"Agent: {agent_id}")
    # TODO: Implement actual optimization logic
    click.echo("Optimization score: 85.2%")
    click.echo("Improvement: 12.5%")
    click.echo("Status: Optimized")
    return 0


@resource.command()
@click.option('--resource-id', help='Specific resource ID to check')
@click.pass_context
def status(ctx, resource_id: str | None):
    """Get resource allocation status from coordinator-api"""
    config = get_config()

    try:
        http_client = AITBCHTTPClient(base_url=config.coordinator_url, timeout=10)

        if resource_id:
            status_data = http_client.get(f"/api/v1/resources/{resource_id}/status")
        else:
            status_data = http_client.get("/api/v1/resources/status")

        success("Resource Status:")
        output(status_data, ctx.obj.get("output_format", "table"))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error fetching resource status: {e}")


@resource.command()
@click.argument('resource_id')
@click.option('--force', is_flag=True, help='Force deallocation without confirmation')
@click.pass_context
def deallocate(ctx, resource_id: str, force: bool):
    """Deallocate resources via coordinator-api"""
    config = get_config()

    if not force:
        if not click.confirm(f"Are you sure you want to deallocate resource {resource_id}?"):
            return

    try:
        http_client = AITBCHTTPClient(base_url=config.coordinator_url, timeout=10)
        result = http_client.post(f"/api/v1/resources/{resource_id}/deallocate")
        success(f"Resource {resource_id} deallocated successfully")
        output(result, ctx.obj.get("output_format", "table"))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error deallocating resource: {e}")

