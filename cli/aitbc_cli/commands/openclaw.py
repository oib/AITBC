"""OpenClaw integration commands for AITBC CLI"""

import click
import httpx
import json
import time
from typing import Optional, Dict, Any, List
from ..utils import output, error, success, warning


@click.group()
def openclaw():
    """OpenClaw integration with edge computing deployment"""
    pass


@click.group()
def deploy():
    """Agent deployment operations"""
    pass


openclaw.add_command(deploy)


@deploy.command()
@click.argument("agent_id")
@click.option("--region", required=True, help="Deployment region")
@click.option("--instances", default=1, help="Number of instances to deploy")
@click.option("--instance-type", default="standard", help="Instance type")
@click.option("--edge-locations", help="Comma-separated edge locations")
@click.option("--auto-scale", is_flag=True, help="Enable auto-scaling")
@click.pass_context
def deploy_agent(ctx, agent_id: str, region: str, instances: int, instance_type: str, 
                edge_locations: Optional[str], auto_scale: bool):
    """Deploy agent to OpenClaw network"""
    config = ctx.obj['config']
    
    deployment_data = {
        "agent_id": agent_id,
        "region": region,
        "instances": instances,
        "instance_type": instance_type,
        "auto_scale": auto_scale
    }
    
    if edge_locations:
        deployment_data["edge_locations"] = [loc.strip() for loc in edge_locations.split(',')]
    
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/openclaw/deploy",
                headers={"X-Api-Key": config.api_key or ""},
                json=deployment_data
            )
            
            if response.status_code == 202:
                deployment = response.json()
                success(f"Agent deployment started: {deployment['id']}")
                output(deployment, ctx.obj['output_format'])
            else:
                error(f"Failed to start deployment: {response.status_code}")
                if response.text:
                    error(response.text)
                ctx.exit(1)
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@click.argument("deployment_id")
@click.option("--instances", required=True, type=int, help="New number of instances")
@click.option("--auto-scale", is_flag=True, help="Enable auto-scaling")
@click.option("--min-instances", default=1, help="Minimum instances for auto-scaling")
@click.option("--max-instances", default=10, help="Maximum instances for auto-scaling")
@click.pass_context
def scale(ctx, deployment_id: str, instances: int, auto_scale: bool, min_instances: int, max_instances: int):
    """Scale agent deployment"""
    config = ctx.obj['config']
    
    scale_data = {
        "instances": instances,
        "auto_scale": auto_scale,
        "min_instances": min_instances,
        "max_instances": max_instances
    }
    
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/openclaw/deployments/{deployment_id}/scale",
                headers={"X-Api-Key": config.api_key or ""},
                json=scale_data
            )
            
            if response.status_code == 200:
                result = response.json()
                success(f"Deployment scaled successfully")
                output(result, ctx.obj['output_format'])
            else:
                error(f"Failed to scale deployment: {response.status_code}")
                if response.text:
                    error(response.text)
                ctx.exit(1)
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@deploy.command()
@click.argument("deployment_id")
@click.option("--objective", default="cost", 
              type=click.Choice(["cost", "performance", "latency", "efficiency"]),
              help="Optimization objective")
@click.pass_context
def optimize(ctx, deployment_id: str, objective: str):
    """Optimize agent deployment"""
    config = ctx.obj['config']
    
    optimization_data = {"objective": objective}
    
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/openclaw/deployments/{deployment_id}/optimize",
                headers={"X-Api-Key": config.api_key or ""},
                json=optimization_data
            )
            
            if response.status_code == 200:
                result = response.json()
                success(f"Deployment optimization completed")
                output(result, ctx.obj['output_format'])
            else:
                error(f"Failed to optimize deployment: {response.status_code}")
                if response.text:
                    error(response.text)
                ctx.exit(1)
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@click.group()
def monitor():
    """OpenClaw monitoring operations"""
    pass


openclaw.add_command(monitor)


@monitor.command()
@click.argument("deployment_id")
@click.option("--metrics", default="latency,cost", help="Comma-separated metrics to monitor")
@click.option("--real-time", is_flag=True, help="Show real-time metrics")
@click.option("--interval", default=10, help="Update interval for real-time monitoring")
@click.pass_context
def monitor(ctx, deployment_id: str, metrics: str, real_time: bool, interval: int):
    """Monitor OpenClaw agent performance"""
    config = ctx.obj['config']
    
    params = {"metrics": [m.strip() for m in metrics.split(',')]}
    
    def get_metrics():
        try:
            with httpx.Client() as client:
                response = client.get(
                    f"{config.coordinator_url}/openclaw/deployments/{deployment_id}/metrics",
                    headers={"X-Api-Key": config.api_key or ""},
                    params=params
                )
                
                if response.status_code == 200:
                    return response.json()
                else:
                    error(f"Failed to get metrics: {response.status_code}")
                    return None
        except Exception as e:
            error(f"Network error: {e}")
            return None
    
    if real_time:
        click.echo(f"Monitoring deployment {deployment_id} (Ctrl+C to stop)...")
        while True:
            metrics_data = get_metrics()
            if metrics_data:
                click.clear()
                click.echo(f"Deployment ID: {deployment_id}")
                click.echo(f"Status: {metrics_data.get('status', 'Unknown')}")
                click.echo(f"Instances: {metrics_data.get('instances', 'N/A')}")
                
                metrics_list = metrics_data.get('metrics', {})
                for metric in [m.strip() for m in metrics.split(',')]:
                    if metric in metrics_list:
                        value = metrics_list[metric]
                        click.echo(f"{metric.title()}: {value}")
                
                if metrics_data.get('status') in ['terminated', 'failed']:
                    break
            
            time.sleep(interval)
    else:
        metrics_data = get_metrics()
        if metrics_data:
            output(metrics_data, ctx.obj['output_format'])


@monitor.command()
@click.argument("deployment_id")
@click.pass_context
def status(ctx, deployment_id: str):
    """Get deployment status"""
    config = ctx.obj['config']
    
    try:
        with httpx.Client() as client:
            response = client.get(
                f"{config.coordinator_url}/openclaw/deployments/{deployment_id}/status",
                headers={"X-Api-Key": config.api_key or ""}
            )
            
            if response.status_code == 200:
                status_data = response.json()
                output(status_data, ctx.obj['output_format'])
            else:
                error(f"Failed to get deployment status: {response.status_code}")
                ctx.exit(1)
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@click.group()
def edge():
    """Edge computing operations"""
    pass


openclaw.add_command(edge)


@edge.command()
@click.argument("agent_id")
@click.option("--locations", required=True, help="Comma-separated edge locations")
@click.option("--strategy", default="latency", 
              type=click.Choice(["latency", "cost", "availability", "hybrid"]),
              help="Edge deployment strategy")
@click.option("--replicas", default=1, help="Number of replicas per location")
@click.pass_context
def deploy(ctx, agent_id: str, locations: str, strategy: str, replicas: int):
    """Deploy agent to edge locations"""
    config = ctx.obj['config']
    
    edge_data = {
        "agent_id": agent_id,
        "locations": [loc.strip() for loc in locations.split(',')],
        "strategy": strategy,
        "replicas": replicas
    }
    
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/openclaw/edge/deploy",
                headers={"X-Api-Key": config.api_key or ""},
                json=edge_data
            )
            
            if response.status_code == 202:
                deployment = response.json()
                success(f"Edge deployment started: {deployment['id']}")
                output(deployment, ctx.obj['output_format'])
            else:
                error(f"Failed to start edge deployment: {response.status_code}")
                if response.text:
                    error(response.text)
                ctx.exit(1)
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@edge.command()
@click.option("--location", help="Filter by location")
@click.pass_context
def resources(ctx, location: Optional[str]):
    """Manage edge resources"""
    config = ctx.obj['config']
    
    params = {}
    if location:
        params["location"] = location
    
    try:
        with httpx.Client() as client:
            response = client.get(
                f"{config.coordinator_url}/openclaw/edge/resources",
                headers={"X-Api-Key": config.api_key or ""},
                params=params
            )
            
            if response.status_code == 200:
                resources = response.json()
                output(resources, ctx.obj['output_format'])
            else:
                error(f"Failed to get edge resources: {response.status_code}")
                ctx.exit(1)
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@edge.command()
@click.argument("deployment_id")
@click.option("--latency-target", type=int, help="Target latency in milliseconds")
@click.option("--cost-budget", type=float, help="Cost budget")
@click.option("--availability", type=float, help="Target availability (0.0-1.0)")
@click.pass_context
def optimize(ctx, deployment_id: str, latency_target: Optional[int], 
           cost_budget: Optional[float], availability: Optional[float]):
    """Optimize edge deployment performance"""
    config = ctx.obj['config']
    
    optimization_data = {}
    if latency_target:
        optimization_data["latency_target_ms"] = latency_target
    if cost_budget:
        optimization_data["cost_budget"] = cost_budget
    if availability:
        optimization_data["availability_target"] = availability
    
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/openclaw/edge/deployments/{deployment_id}/optimize",
                headers={"X-Api-Key": config.api_key or ""},
                json=optimization_data
            )
            
            if response.status_code == 200:
                result = response.json()
                success(f"Edge optimization completed")
                output(result, ctx.obj['output_format'])
            else:
                error(f"Failed to optimize edge deployment: {response.status_code}")
                if response.text:
                    error(response.text)
                ctx.exit(1)
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@edge.command()
@click.argument("deployment_id")
@click.option("--standards", help="Comma-separated compliance standards")
@click.pass_context
def compliance(ctx, deployment_id: str, standards: Optional[str]):
    """Check edge security compliance"""
    config = ctx.obj['config']
    
    params = {}
    if standards:
        params["standards"] = [s.strip() for s in standards.split(',')]
    
    try:
        with httpx.Client() as client:
            response = client.get(
                f"{config.coordinator_url}/openclaw/edge/deployments/{deployment_id}/compliance",
                headers={"X-Api-Key": config.api_key or ""},
                params=params
            )
            
            if response.status_code == 200:
                compliance_data = response.json()
                output(compliance_data, ctx.obj['output_format'])
            else:
                error(f"Failed to check compliance: {response.status_code}")
                ctx.exit(1)
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@click.group()
def routing():
    """Agent skill routing and job offloading"""
    pass


openclaw.add_command(routing)


@routing.command()
@click.argument("deployment_id")
@click.option("--algorithm", default="load-balanced", 
              type=click.Choice(["load-balanced", "skill-based", "cost-based", "latency-based"]),
              help="Routing algorithm")
@click.option("--weights", help="Comma-separated weights for routing factors")
@click.pass_context
def optimize(ctx, deployment_id: str, algorithm: str, weights: Optional[str]):
    """Optimize agent skill routing"""
    config = ctx.obj['config']
    
    routing_data = {"algorithm": algorithm}
    if weights:
        routing_data["weights"] = [w.strip() for w in weights.split(',')]
    
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/openclaw/routing/deployments/{deployment_id}/optimize",
                headers={"X-Api-Key": config.api_key or ""},
                json=routing_data
            )
            
            if response.status_code == 200:
                result = response.json()
                success(f"Routing optimization completed")
                output(result, ctx.obj['output_format'])
            else:
                error(f"Failed to optimize routing: {response.status_code}")
                if response.text:
                    error(response.text)
                ctx.exit(1)
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@routing.command()
@click.argument("deployment_id")
@click.pass_context
def status(ctx, deployment_id: str):
    """Get routing status and statistics"""
    config = ctx.obj['config']
    
    try:
        with httpx.Client() as client:
            response = client.get(
                f"{config.coordinator_url}/openclaw/routing/deployments/{deployment_id}/status",
                headers={"X-Api-Key": config.api_key or ""}
            )
            
            if response.status_code == 200:
                status_data = response.json()
                output(status_data, ctx.obj['output_format'])
            else:
                error(f"Failed to get routing status: {response.status_code}")
                ctx.exit(1)
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@click.group()
def ecosystem():
    """OpenClaw ecosystem development"""
    pass


openclaw.add_command(ecosystem)


@ecosystem.command()
@click.option("--name", required=True, help="Solution name")
@click.option("--type", required=True, 
              type=click.Choice(["agent", "workflow", "integration", "tool"]),
              help="Solution type")
@click.option("--description", default="", help="Solution description")
@click.option("--package", type=click.File('rb'), help="Solution package file")
@click.pass_context
def create(ctx, name: str, type: str, description: str, package):
    """Create OpenClaw ecosystem solution"""
    config = ctx.obj['config']
    
    solution_data = {
        "name": name,
        "type": type,
        "description": description
    }
    
    files = {}
    if package:
        files["package"] = package.read()
    
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/openclaw/ecosystem/solutions",
                headers={"X-Api-Key": config.api_key or ""},
                data=solution_data,
                files=files
            )
            
            if response.status_code == 201:
                solution = response.json()
                success(f"OpenClaw solution created: {solution['id']}")
                output(solution, ctx.obj['output_format'])
            else:
                error(f"Failed to create solution: {response.status_code}")
                if response.text:
                    error(response.text)
                ctx.exit(1)
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@ecosystem.command()
@click.option("--type", help="Filter by solution type")
@click.option("--category", help="Filter by category")
@click.option("--limit", default=20, help="Number of solutions to list")
@click.pass_context
def list(ctx, type: Optional[str], category: Optional[str], limit: int):
    """List OpenClaw ecosystem solutions"""
    config = ctx.obj['config']
    
    params = {"limit": limit}
    if type:
        params["type"] = type
    if category:
        params["category"] = category
    
    try:
        with httpx.Client() as client:
            response = client.get(
                f"{config.coordinator_url}/openclaw/ecosystem/solutions",
                headers={"X-Api-Key": config.api_key or ""},
                params=params
            )
            
            if response.status_code == 200:
                solutions = response.json()
                output(solutions, ctx.obj['output_format'])
            else:
                error(f"Failed to list solutions: {response.status_code}")
                ctx.exit(1)
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@ecosystem.command()
@click.argument("solution_id")
@click.pass_context
def install(ctx, solution_id: str):
    """Install OpenClaw ecosystem solution"""
    config = ctx.obj['config']
    
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/openclaw/ecosystem/solutions/{solution_id}/install",
                headers={"X-Api-Key": config.api_key or ""}
            )
            
            if response.status_code == 200:
                result = response.json()
                success(f"Solution installed successfully")
                output(result, ctx.obj['output_format'])
            else:
                error(f"Failed to install solution: {response.status_code}")
                if response.text:
                    error(response.text)
                ctx.exit(1)
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@openclaw.command()
@click.argument("deployment_id")
@click.pass_context
def terminate(ctx, deployment_id: str):
    """Terminate OpenClaw deployment"""
    config = ctx.obj['config']
    
    if not click.confirm(f"Terminate deployment {deployment_id}? This action cannot be undone."):
        click.echo("Operation cancelled")
        return
    
    try:
        with httpx.Client() as client:
            response = client.delete(
                f"{config.coordinator_url}/openclaw/deployments/{deployment_id}",
                headers={"X-Api-Key": config.api_key or ""}
            )
            
            if response.status_code == 200:
                result = response.json()
                success(f"Deployment {deployment_id} terminated")
                output(result, ctx.obj['output_format'])
            else:
                error(f"Failed to terminate deployment: {response.status_code}")
                if response.text:
                    error(response.text)
                ctx.exit(1)
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)
