"""Swarm intelligence commands for AITBC CLI"""

import click
import httpx
import json
from typing import Optional, Dict, Any, List
from utils import output, error, success, warning


@click.group()
def swarm():
    """Swarm intelligence and collective optimization"""
    pass


@swarm.command()
@click.option("--role", required=True, 
              type=click.Choice(["load-balancer", "resource-optimizer", "task-coordinator", "monitor"]),
              help="Swarm role")
@click.option("--capability", required=True, help="Agent capability")
@click.option("--region", help="Operating region")
@click.option("--priority", default="normal", 
              type=click.Choice(["low", "normal", "high"]),
              help="Swarm priority")
@click.pass_context
def join(ctx, role: str, capability: str, region: Optional[str], priority: str):
    """Join agent swarm for collective optimization"""
    config = ctx.obj['config']
    
    swarm_data = {
        "role": role,
        "capability": capability,
        "priority": priority
    }
    
    if region:
        swarm_data["region"] = region
    
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/swarm/join",
                headers={"X-Api-Key": config.api_key or ""},
                json=swarm_data
            )
            
            if response.status_code == 201:
                result = response.json()
                success(f"Joined swarm: {result['swarm_id']}")
                output(result, ctx.obj['output_format'])
            else:
                error(f"Failed to join swarm: {response.status_code}")
                if response.text:
                    error(response.text)
                ctx.exit(1)
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@swarm.command()
@click.option("--task", required=True, help="Swarm task type")
@click.option("--collaborators", type=int, default=5, help="Number of collaborators")
@click.option("--strategy", default="consensus", 
              type=click.Choice(["consensus", "leader-election", "distributed"]),
              help="Coordination strategy")
@click.option("--timeout", default=3600, help="Task timeout in seconds")
@click.pass_context
def coordinate(ctx, task: str, collaborators: int, strategy: str, timeout: int):
    """Coordinate swarm task execution"""
    config = ctx.obj['config']
    
    coordination_data = {
        "task": task,
        "collaborators": collaborators,
        "strategy": strategy,
        "timeout_seconds": timeout
    }
    
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/swarm/coordinate",
                headers={"X-Api-Key": config.api_key or ""},
                json=coordination_data
            )
            
            if response.status_code == 202:
                result = response.json()
                success(f"Swarm coordination started: {result['task_id']}")
                output(result, ctx.obj['output_format'])
            else:
                error(f"Failed to start coordination: {response.status_code}")
                if response.text:
                    error(response.text)
                ctx.exit(1)
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@swarm.command()
@click.option("--swarm-id", help="Filter by swarm ID")
@click.option("--status", help="Filter by status")
@click.option("--limit", default=20, help="Number of swarms to list")
@click.pass_context
def list(ctx, swarm_id: Optional[str], status: Optional[str], limit: int):
    """List active swarms"""
    config = ctx.obj['config']
    
    params = {"limit": limit}
    if swarm_id:
        params["swarm_id"] = swarm_id
    if status:
        params["status"] = status
    
    try:
        with httpx.Client() as client:
            response = client.get(
                f"{config.coordinator_url}/swarm/list",
                headers={"X-Api-Key": config.api_key or ""},
                params=params
            )
            
            if response.status_code == 200:
                swarms = response.json()
                output(swarms, ctx.obj['output_format'])
            else:
                error(f"Failed to list swarms: {response.status_code}")
                ctx.exit(1)
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@swarm.command()
@click.argument("task_id")
@click.option("--real-time", is_flag=True, help="Show real-time progress")
@click.option("--interval", default=10, help="Update interval for real-time monitoring")
@click.pass_context
def status(ctx, task_id: str, real_time: bool, interval: int):
    """Get swarm task status"""
    config = ctx.obj['config']
    
    def get_status():
        try:
            with httpx.Client() as client:
                response = client.get(
                    f"{config.coordinator_url}/swarm/tasks/{task_id}/status",
                    headers={"X-Api-Key": config.api_key or ""}
                )
                
                if response.status_code == 200:
                    return response.json()
                else:
                    error(f"Failed to get task status: {response.status_code}")
                    return None
        except Exception as e:
            error(f"Network error: {e}")
            return None
    
    if real_time:
        click.echo(f"Monitoring swarm task {task_id} (Ctrl+C to stop)...")
        while True:
            status_data = get_status()
            if status_data:
                click.clear()
                click.echo(f"Task ID: {task_id}")
                click.echo(f"Status: {status_data.get('status', 'Unknown')}")
                click.echo(f"Progress: {status_data.get('progress', 0)}%")
                click.echo(f"Collaborators: {status_data.get('active_collaborators', 0)}/{status_data.get('total_collaborators', 0)}")
                
                if status_data.get('status') in ['completed', 'failed', 'cancelled']:
                    break
            
            time.sleep(interval)
    else:
        status_data = get_status()
        if status_data:
            output(status_data, ctx.obj['output_format'])


@swarm.command()
@click.argument("swarm_id")
@click.pass_context
def leave(ctx, swarm_id: str):
    """Leave swarm"""
    config = ctx.obj['config']
    
    if not click.confirm(f"Leave swarm {swarm_id}?"):
        click.echo("Operation cancelled")
        return
    
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/swarm/{swarm_id}/leave",
                headers={"X-Api-Key": config.api_key or ""}
            )
            
            if response.status_code == 200:
                result = response.json()
                success(f"Left swarm {swarm_id}")
                output(result, ctx.obj['output_format'])
            else:
                error(f"Failed to leave swarm: {response.status_code}")
                if response.text:
                    error(response.text)
                ctx.exit(1)
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@swarm.command()
@click.argument("task_id")
@click.option("--consensus-threshold", default=0.7, help="Consensus threshold (0.0-1.0)")
@click.pass_context
def consensus(ctx, task_id: str, consensus_threshold: float):
    """Achieve swarm consensus on task result"""
    config = ctx.obj['config']
    
    consensus_data = {
        "consensus_threshold": consensus_threshold
    }
    
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/swarm/tasks/{task_id}/consensus",
                headers={"X-Api-Key": config.api_key or ""},
                json=consensus_data
            )
            
            if response.status_code == 200:
                result = response.json()
                success(f"Consensus achieved: {result.get('consensus_reached', False)}")
                output(result, ctx.obj['output_format'])
            else:
                error(f"Failed to achieve consensus: {response.status_code}")
                if response.text:
                    error(response.text)
                ctx.exit(1)
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)
