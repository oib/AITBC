"""Production deployment and scaling commands for AITBC CLI"""

import click
import asyncio
import json
from datetime import datetime
from typing import Optional
from ..core.deployment import (
    ProductionDeployment, ScalingPolicy, DeploymentStatus
)
from ..utils import output, error, success

@click.group()
def deploy():
    """Production deployment and scaling commands"""
    pass

@deploy.command()
@click.argument('name')
@click.argument('environment')
@click.argument('region')
@click.argument('instance_type')
@click.argument('min_instances', type=int)
@click.argument('max_instances', type=int)
@click.argument('desired_instances', type=int)
@click.argument('port', type=int)
@click.argument('domain')
@click.option('--db-host', default='localhost', help='Database host')
@click.option('--db-port', default=5432, help='Database port')
@click.option('--db-name', default='aitbc', help='Database name')
@click.pass_context
def create(ctx, name, environment, region, instance_type, min_instances, max_instances, desired_instances, port, domain, db_host, db_port, db_name):
    """Create a new deployment configuration"""
    try:
        deployment = ProductionDeployment()
        
        # Database configuration
        database_config = {
            "host": db_host,
            "port": db_port,
            "name": db_name,
            "ssl_enabled": True if environment == "production" else False
        }
        
        # Create deployment
        deployment_id = asyncio.run(deployment.create_deployment(
            name=name,
            environment=environment,
            region=region,
            instance_type=instance_type,
            min_instances=min_instances,
            max_instances=max_instances,
            desired_instances=desired_instances,
            port=port,
            domain=domain,
            database_config=database_config
        ))
        
        if deployment_id:
            success(f"Deployment configuration created! ID: {deployment_id}")
            
            deployment_data = {
                "Deployment ID": deployment_id,
                "Name": name,
                "Environment": environment,
                "Region": region,
                "Instance Type": instance_type,
                "Min Instances": min_instances,
                "Max Instances": max_instances,
                "Desired Instances": desired_instances,
                "Port": port,
                "Domain": domain,
                "Status": "pending",
                "Created": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            output(deployment_data, ctx.obj.get('output_format', 'table'))
        else:
            error("Failed to create deployment configuration")
            raise click.Abort()
        
    except Exception as e:
        error(f"Error creating deployment: {str(e)}")
        raise click.Abort()

@deploy.command()
@click.argument('deployment_id')
@click.pass_context
def start(ctx, deployment_id):
    """Deploy the application to production"""
    try:
        deployment = ProductionDeployment()
        
        # Deploy application
        success_deploy = asyncio.run(deployment.deploy_application(deployment_id))
        
        if success_deploy:
            success(f"Deployment {deployment_id} started successfully!")
            
            deployment_data = {
                "Deployment ID": deployment_id,
                "Status": "running",
                "Started": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            output(deployment_data, ctx.obj.get('output_format', 'table'))
        else:
            error(f"Failed to start deployment {deployment_id}")
            raise click.Abort()
        
    except Exception as e:
        error(f"Error starting deployment: {str(e)}")
        raise click.Abort()

@deploy.command()
@click.argument('deployment_id')
@click.argument('target_instances', type=int)
@click.option('--reason', default='manual', help='Scaling reason')
@click.pass_context
def scale(ctx, deployment_id, target_instances, reason):
    """Scale a deployment to target instance count"""
    try:
        deployment = ProductionDeployment()
        
        # Scale deployment
        success_scale = asyncio.run(deployment.scale_deployment(deployment_id, target_instances, reason))
        
        if success_scale:
            success(f"Deployment {deployment_id} scaled to {target_instances} instances!")
            
            scaling_data = {
                "Deployment ID": deployment_id,
                "Target Instances": target_instances,
                "Reason": reason,
                "Status": "completed",
                "Scaled": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            output(scaling_data, ctx.obj.get('output_format', 'table'))
        else:
            error(f"Failed to scale deployment {deployment_id}")
            raise click.Abort()
        
    except Exception as e:
        error(f"Error scaling deployment: {str(e)}")
        raise click.Abort()

@deploy.command()
@click.argument('deployment_id')
@click.pass_context
def status(ctx, deployment_id):
    """Get comprehensive deployment status"""
    try:
        deployment = ProductionDeployment()
        
        # Get deployment status
        status_data = asyncio.run(deployment.get_deployment_status(deployment_id))
        
        if not status_data:
            error(f"Deployment {deployment_id} not found")
            raise click.Abort()
        
        # Format deployment info
        deployment_info = status_data["deployment"]
        info_data = [
            {"Metric": "Deployment ID", "Value": deployment_info["deployment_id"]},
            {"Metric": "Name", "Value": deployment_info["name"]},
            {"Metric": "Environment", "Value": deployment_info["environment"]},
            {"Metric": "Region", "Value": deployment_info["region"]},
            {"Metric": "Instance Type", "Value": deployment_info["instance_type"]},
            {"Metric": "Min Instances", "Value": deployment_info["min_instances"]},
            {"Metric": "Max Instances", "Value": deployment_info["max_instances"]},
            {"Metric": "Desired Instances", "Value": deployment_info["desired_instances"]},
            {"Metric": "Port", "Value": deployment_info["port"]},
            {"Metric": "Domain", "Value": deployment_info["domain"]},
            {"Metric": "Health Status", "Value": "Healthy" if status_data["health_status"] else "Unhealthy"},
            {"Metric": "Uptime", "Value": f"{status_data['uptime_percentage']:.2f}%"}
        ]
        
        output(info_data, ctx.obj.get('output_format', 'table'), title=f"Deployment Status: {deployment_id}")
        
        # Show metrics if available
        if status_data["metrics"]:
            metrics = status_data["metrics"]
            metrics_data = [
                {"Metric": "CPU Usage", "Value": f"{metrics['cpu_usage']:.1f}%"},
                {"Metric": "Memory Usage", "Value": f"{metrics['memory_usage']:.1f}%"},
                {"Metric": "Disk Usage", "Value": f"{metrics['disk_usage']:.1f}%"},
                {"Metric": "Request Count", "Value": metrics['request_count']},
                {"Metric": "Error Rate", "Value": f"{metrics['error_rate']:.2f}%"},
                {"Metric": "Response Time", "Value": f"{metrics['response_time']:.1f}ms"},
                {"Metric": "Active Instances", "Value": metrics['active_instances']}
            ]
            
            output(metrics_data, ctx.obj.get('output_format', 'table'), title="Performance Metrics")
        
        # Show recent scaling events
        if status_data["recent_scaling_events"]:
            events = status_data["recent_scaling_events"]
            events_data = [
                {
                    "Event ID": event["event_id"][:8],
                    "Type": event["scaling_type"],
                    "From": event["old_instances"],
                    "To": event["new_instances"],
                    "Reason": event["trigger_reason"],
                    "Success": "Yes" if event["success"] else "No",
                    "Time": event["triggered_at"]
                }
                for event in events
            ]
            
            output(events_data, ctx.obj.get('output_format', 'table'), title="Recent Scaling Events")
        
    except Exception as e:
        error(f"Error getting deployment status: {str(e)}")
        raise click.Abort()

@deploy.command()
@click.option('--format', type=click.Choice(['table', 'json']), default='table', help='Output format')
@click.pass_context
def overview(ctx, format):
    """Get overview of all deployments"""
    try:
        deployment = ProductionDeployment()
        
        # Get cluster overview
        overview_data = asyncio.run(deployment.get_cluster_overview())
        
        if not overview_data:
            error("No deployment data available")
            raise click.Abort()
        
        # Cluster metrics
        cluster_data = [
            {"Metric": "Total Deployments", "Value": overview_data["total_deployments"]},
            {"Metric": "Running Deployments", "Value": overview_data["running_deployments"]},
            {"Metric": "Total Instances", "Value": overview_data["total_instances"]},
            {"Metric": "Health Check Coverage", "Value": f"{overview_data['health_check_coverage']:.1%}"},
            {"Metric": "Recent Scaling Events", "Value": overview_data["recent_scaling_events"]},
            {"Metric": "Scaling Success Rate", "Value": f"{overview_data['successful_scaling_rate']:.1%}"}
        ]
        
        output(cluster_data, ctx.obj.get('output_format', format), title="Cluster Overview")
        
        # Aggregate metrics
        if "aggregate_metrics" in overview_data:
            metrics = overview_data["aggregate_metrics"]
            metrics_data = [
                {"Metric": "Average CPU Usage", "Value": f"{metrics['total_cpu_usage']:.1f}%"},
                {"Metric": "Average Memory Usage", "Value": f"{metrics['total_memory_usage']:.1f}%"},
                {"Metric": "Average Disk Usage", "Value": f"{metrics['total_disk_usage']:.1f}%"},
                {"Metric": "Average Response Time", "Value": f"{metrics['average_response_time']:.1f}ms"},
                {"Metric": "Average Error Rate", "Value": f"{metrics['average_error_rate']:.2f}%"},
                {"Metric": "Average Uptime", "Value": f"{metrics['average_uptime']:.1f}%"}
            ]
            
            output(metrics_data, ctx.obj.get('output_format', format), title="Aggregate Performance Metrics")
        
    except Exception as e:
        error(f"Error getting cluster overview: {str(e)}")
        raise click.Abort()

@deploy.command()
@click.argument('deployment_id')
@click.option('--interval', default=60, help='Update interval in seconds')
@click.pass_context
def monitor(ctx, deployment_id, interval):
    """Monitor deployment performance in real-time"""
    try:
        deployment = ProductionDeployment()
        
        # Real-time monitoring
        from rich.console import Console
        from rich.live import Live
        from rich.table import Table
        import time
        
        console = Console()
        
        def generate_monitor_table():
            try:
                status_data = asyncio.run(deployment.get_deployment_status(deployment_id))
                
                if not status_data:
                    return f"Deployment {deployment_id} not found"
                
                deployment_info = status_data["deployment"]
                metrics = status_data.get("metrics")
                
                table = Table(title=f"Deployment Monitor - {deployment_info['name']} ({deployment_id[:8]}) - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                table.add_column("Metric", style="cyan")
                table.add_column("Value", style="green")
                
                table.add_row("Environment", deployment_info["environment"])
                table.add_row("Desired Instances", str(deployment_info["desired_instances"]))
                table.add_row("Health Status", "✅ Healthy" if status_data["health_status"] else "❌ Unhealthy")
                table.add_row("Uptime", f"{status_data['uptime_percentage']:.2f}%")
                
                if metrics:
                    table.add_row("CPU Usage", f"{metrics['cpu_usage']:.1f}%")
                    table.add_row("Memory Usage", f"{metrics['memory_usage']:.1f}%")
                    table.add_row("Disk Usage", f"{metrics['disk_usage']:.1f}%")
                    table.add_row("Request Count", str(metrics['request_count']))
                    table.add_row("Error Rate", f"{metrics['error_rate']:.2f}%")
                    table.add_row("Response Time", f"{metrics['response_time']:.1f}ms")
                    table.add_row("Active Instances", str(metrics['active_instances']))
                
                return table
            except Exception as e:
                return f"Error getting deployment data: {e}"
        
        with Live(generate_monitor_table(), refresh_per_second=1) as live:
            try:
                while True:
                    live.update(generate_monitor_table())
                    time.sleep(interval)
            except KeyboardInterrupt:
                console.print("\n[yellow]Monitoring stopped by user[/yellow]")
        
    except Exception as e:
        error(f"Error during monitoring: {str(e)}")
        raise click.Abort()

@deploy.command()
@click.argument('deployment_id')
@click.pass_context
def auto_scale(ctx, deployment_id):
    """Trigger auto-scaling evaluation for a deployment"""
    try:
        deployment = ProductionDeployment()
        
        # Trigger auto-scaling
        success_auto = asyncio.run(deployment.auto_scale_deployment(deployment_id))
        
        if success_auto:
            success(f"Auto-scaling evaluation completed for deployment {deployment_id}")
        else:
            error(f"Auto-scaling evaluation failed for deployment {deployment_id}")
            raise click.Abort()
        
    except Exception as e:
        error(f"Error in auto-scaling: {str(e)}")
        raise click.Abort()

@deploy.command()
@click.option('--format', type=click.Choice(['table', 'json']), default='table', help='Output format')
@click.pass_context
def list_deployments(ctx, format):
    """List all deployments"""
    try:
        deployment = ProductionDeployment()
        
        # Get all deployment statuses
        deployments = []
        for deployment_id in deployment.deployments.keys():
            status_data = asyncio.run(deployment.get_deployment_status(deployment_id))
            if status_data:
                deployment_info = status_data["deployment"]
                deployments.append({
                    "Deployment ID": deployment_info["deployment_id"][:8],
                    "Name": deployment_info["name"],
                    "Environment": deployment_info["environment"],
                    "Instances": f"{deployment_info['desired_instances']}/{deployment_info['max_instances']}",
                    "Status": "Running" if status_data["health_status"] else "Stopped",
                    "Uptime": f"{status_data['uptime_percentage']:.1f}%",
                    "Created": deployment_info["created_at"]
                })
        
        if not deployments:
            output("No deployments found", ctx.obj.get('output_format', 'table'))
            return
        
        output(deployments, ctx.obj.get('output_format', format), title="All Deployments")
        
    except Exception as e:
        error(f"Error listing deployments: {str(e)}")
        raise click.Abort()
