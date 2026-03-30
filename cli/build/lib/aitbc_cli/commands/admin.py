"""Admin commands for AITBC CLI"""

import click
import httpx
import json
from typing import Optional, List, Dict, Any
from ..utils import output, error, success


@click.group()
def admin():
    """System administration commands"""
    pass


@admin.command()
@click.pass_context
def status(ctx):
    """Get system status"""
    config = ctx.obj['config']
    
    try:
        with httpx.Client() as client:
            response = client.get(
                f"{config.coordinator_url}/v1/admin/status",
                headers={"X-Api-Key": config.api_key or ""}
            )
            
            if response.status_code == 200:
                status_data = response.json()
                output(status_data, ctx.obj['output_format'])
            else:
                error(f"Failed to get system status: {response.status_code}")
                ctx.exit(1)
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@admin.command()
@click.option("--limit", default=50, help="Number of jobs to show")
@click.option("--status", help="Filter by status")
@click.pass_context
def jobs(ctx, limit: int, status: Optional[str]):
    """List all jobs in the system"""
    config = ctx.obj['config']
    
    try:
        params = {"limit": limit}
        if status:
            params["status"] = status
            
        with httpx.Client() as client:
            response = client.get(
                f"{config.coordinator_url}/v1/admin/jobs",
                params=params,
                headers={"X-Api-Key": config.api_key or ""}
            )
            
            if response.status_code == 200:
                jobs = response.json()
                output(jobs, ctx.obj['output_format'])
            else:
                error(f"Failed to get jobs: {response.status_code}")
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@admin.command()
@click.argument("job_id")
@click.pass_context
def job_details(ctx, job_id: str):
    """Get detailed job information"""
    config = ctx.obj['config']
    
    try:
        with httpx.Client() as client:
            response = client.get(
                f"{config.coordinator_url}/v1/admin/jobs/{job_id}",
                headers={"X-Api-Key": config.api_key or ""}
            )
            
            if response.status_code == 200:
                job_data = response.json()
                output(job_data, ctx.obj['output_format'])
            else:
                error(f"Job not found: {response.status_code}")
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@admin.command()
@click.argument("job_id")
@click.pass_context
def delete_job(ctx, job_id: str):
    """Delete a job from the system"""
    config = ctx.obj['config']
    
    if not click.confirm(f"Are you sure you want to delete job {job_id}?"):
        return
    
    try:
        with httpx.Client() as client:
            response = client.delete(
                f"{config.coordinator_url}/v1/admin/jobs/{job_id}",
                headers={"X-Api-Key": config.api_key or ""}
            )
            
            if response.status_code == 200:
                success(f"Job {job_id} deleted")
                output({"status": "deleted", "job_id": job_id}, ctx.obj['output_format'])
            else:
                error(f"Failed to delete job: {response.status_code}")
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@admin.command()
@click.option("--limit", default=50, help="Number of miners to show")
@click.option("--status", help="Filter by status")
@click.pass_context
def miners(ctx, limit: int, status: Optional[str]):
    """List all registered miners"""
    config = ctx.obj['config']
    
    try:
        params = {"limit": limit}
        if status:
            params["status"] = status
            
        with httpx.Client() as client:
            response = client.get(
                f"{config.coordinator_url}/v1/admin/miners",
                params=params,
                headers={"X-Api-Key": config.api_key or ""}
            )
            
            if response.status_code == 200:
                miners = response.json()
                output(miners, ctx.obj['output_format'])
            else:
                error(f"Failed to get miners: {response.status_code}")
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@admin.command()
@click.argument("miner_id")
@click.pass_context
def miner_details(ctx, miner_id: str):
    """Get detailed miner information"""
    config = ctx.obj['config']
    
    try:
        with httpx.Client() as client:
            response = client.get(
                f"{config.coordinator_url}/v1/admin/miners/{miner_id}",
                headers={"X-Api-Key": config.api_key or ""}
            )
            
            if response.status_code == 200:
                miner_data = response.json()
                output(miner_data, ctx.obj['output_format'])
            else:
                error(f"Miner not found: {response.status_code}")
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@admin.command()
@click.argument("miner_id")
@click.pass_context
def deactivate_miner(ctx, miner_id: str):
    """Deactivate a miner"""
    config = ctx.obj['config']
    
    if not click.confirm(f"Are you sure you want to deactivate miner {miner_id}?"):
        return
    
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/v1/admin/miners/{miner_id}/deactivate",
                headers={"X-Api-Key": config.api_key or ""}
            )
            
            if response.status_code == 200:
                success(f"Miner {miner_id} deactivated")
                output({"status": "deactivated", "miner_id": miner_id}, ctx.obj['output_format'])
            else:
                error(f"Failed to deactivate miner: {response.status_code}")
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@admin.command()
@click.argument("miner_id")
@click.pass_context
def activate_miner(ctx, miner_id: str):
    """Activate a miner"""
    config = ctx.obj['config']
    
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/v1/admin/miners/{miner_id}/activate",
                headers={"X-Api-Key": config.api_key or ""}
            )
            
            if response.status_code == 200:
                success(f"Miner {miner_id} activated")
                output({"status": "activated", "miner_id": miner_id}, ctx.obj['output_format'])
            else:
                error(f"Failed to activate miner: {response.status_code}")
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@admin.command()
@click.option("--days", type=int, default=7, help="Number of days to analyze")
@click.pass_context
def analytics(ctx, days: int):
    """Get system analytics"""
    config = ctx.obj['config']
    
    try:
        with httpx.Client() as client:
            response = client.get(
                f"{config.coordinator_url}/v1/admin/analytics",
                params={"days": days},
                headers={"X-Api-Key": config.api_key or ""}
            )
            
            if response.status_code == 200:
                analytics_data = response.json()
                output(analytics_data, ctx.obj['output_format'])
            else:
                error(f"Failed to get analytics: {response.status_code}")
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@admin.command()
@click.option("--level", default="INFO", help="Log level (DEBUG, INFO, WARNING, ERROR)")
@click.option("--limit", default=100, help="Number of log entries to show")
@click.pass_context
def logs(ctx, level: str, limit: int):
    """Get system logs"""
    config = ctx.obj['config']
    
    try:
        with httpx.Client() as client:
            response = client.get(
                f"{config.coordinator_url}/v1/admin/logs",
                params={"level": level, "limit": limit},
                headers={"X-Api-Key": config.api_key or ""}
            )
            
            if response.status_code == 200:
                logs_data = response.json()
                output(logs_data, ctx.obj['output_format'])
            else:
                error(f"Failed to get logs: {response.status_code}")
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@admin.command()
@click.argument("job_id")
@click.option("--reason", help="Reason for priority change")
@click.pass_context
def prioritize_job(ctx, job_id: str, reason: Optional[str]):
    """Set job to high priority"""
    config = ctx.obj['config']
    
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/v1/admin/jobs/{job_id}/prioritize",
                json={"reason": reason or "Admin priority"},
                headers={"X-Api-Key": config.api_key or ""}
            )
            
            if response.status_code == 200:
                success(f"Job {job_id} prioritized")
                output({"status": "prioritized", "job_id": job_id}, ctx.obj['output_format'])
            else:
                error(f"Failed to prioritize job: {response.status_code}")
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@admin.command()
@click.option("--action", required=True, help="Action to perform")
@click.option("--target", help="Target of the action")
@click.option("--data", help="Additional data (JSON)")
@click.pass_context
def execute(ctx, action: str, target: Optional[str], data: Optional[str]):
    """Execute custom admin action"""
    config = ctx.obj['config']
    
    # Parse data if provided
    parsed_data = {}
    if data:
        try:
            parsed_data = json.loads(data)
        except json.JSONDecodeError:
            error("Invalid JSON data")
            return
    
    if target:
        parsed_data["target"] = target
    
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/v1/admin/execute/{action}",
                json=parsed_data,
                headers={"X-Api-Key": config.api_key or ""}
            )
            
            if response.status_code == 200:
                result = response.json()
                output(result, ctx.obj['output_format'])
            else:
                error(f"Failed to execute action: {response.status_code}")
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@admin.group()
def maintenance():
    """Maintenance operations"""
    pass


@maintenance.command()
@click.pass_context
def cleanup(ctx):
    """Clean up old jobs and data"""
    config = ctx.obj['config']
    
    if not click.confirm("This will clean up old jobs and temporary data. Continue?"):
        return
    
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/v1/admin/maintenance/cleanup",
                headers={"X-Api-Key": config.api_key or ""}
            )
            
            if response.status_code == 200:
                result = response.json()
                success("Cleanup completed")
                output(result, ctx.obj['output_format'])
            else:
                error(f"Cleanup failed: {response.status_code}")
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@maintenance.command()
@click.pass_context
def reindex(ctx):
    """Reindex the database"""
    config = ctx.obj['config']
    
    if not click.confirm("This will reindex the entire database. Continue?"):
        return
    
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/v1/admin/maintenance/reindex",
                headers={"X-Api-Key": config.api_key or ""}
            )
            
            if response.status_code == 200:
                result = response.json()
                success("Reindex started")
                output(result, ctx.obj['output_format'])
            else:
                error(f"Reindex failed: {response.status_code}")
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@maintenance.command()
@click.pass_context
def backup(ctx):
    """Create system backup"""
    config = ctx.obj['config']
    
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/v1/admin/maintenance/backup",
                headers={"X-Api-Key": config.api_key or ""}
            )
            
            if response.status_code == 200:
                result = response.json()
                success("Backup created")
                output(result, ctx.obj['output_format'])
            else:
                error(f"Backup failed: {response.status_code}")
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@admin.command(name="audit-log")
@click.option("--limit", default=50, help="Number of entries to show")
@click.option("--action", "action_filter", help="Filter by action type")
@click.pass_context
def audit_log(ctx, limit: int, action_filter: Optional[str]):
    """View audit log"""
    from ..utils import AuditLogger
    
    logger = AuditLogger()
    entries = logger.get_logs(limit=limit, action_filter=action_filter)
    
    if not entries:
        output({"message": "No audit log entries found"}, ctx.obj['output_format'])
        return
    
    output(entries, ctx.obj['output_format'])


# Add maintenance group to admin
admin.add_command(maintenance)
