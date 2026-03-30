"""Miner commands for AITBC CLI"""

import click
import httpx
import json
import time
import concurrent.futures
from typing import Optional, Dict, Any, List
from ..utils import output, error, success


@click.group()
def miner():
    """Register as miner and process jobs"""
    pass


@miner.command()
@click.option("--gpu", help="GPU model name")
@click.option("--memory", type=int, help="GPU memory in GB")
@click.option("--cuda-cores", type=int, help="Number of CUDA cores")
@click.option("--miner-id", default="cli-miner", help="Miner ID")
@click.pass_context
def register(ctx, gpu: Optional[str], memory: Optional[int], 
             cuda_cores: Optional[int], miner_id: str):
    """Register as a miner with the coordinator"""
    config = ctx.obj['config']
    
    # Build capabilities
    capabilities = {}
    if gpu:
        capabilities["gpu"] = {"model": gpu}
    if memory:
        if "gpu" not in capabilities:
            capabilities["gpu"] = {}
        capabilities["gpu"]["memory_gb"] = memory
    if cuda_cores:
        if "gpu" not in capabilities:
            capabilities["gpu"] = {}
        capabilities["gpu"]["cuda_cores"] = cuda_cores
    
    # Default capabilities if none provided
    if not capabilities:
        capabilities = {
            "cpu": {"cores": 4},
            "memory": {"gb": 16}
        }
    
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/v1/miners/register?miner_id={miner_id}",
                headers={
                    "Content-Type": "application/json",
                    "X-Api-Key": config.api_key or ""
                },
                json={"capabilities": capabilities}
            )
            
            if response.status_code == 200:
                output({
                    "miner_id": miner_id,
                    "status": "registered",
                    "capabilities": capabilities
                }, ctx.obj['output_format'])
            else:
                error(f"Failed to register: {response.status_code} - {response.text}")
    except Exception as e:
        error(f"Network error: {e}")


@miner.command()
@click.option("--wait", type=int, default=5, help="Max wait time in seconds")
@click.option("--miner-id", default="cli-miner", help="Miner ID")
@click.pass_context
def poll(ctx, wait: int, miner_id: str):
    """Poll for a single job"""
    config = ctx.obj['config']
    
    try:
        with httpx.Client() as client:
            response = client.get(
                f"{config.coordinator_url}/v1/miners/poll",
                headers={
                    "X-Api-Key": config.api_key or "",
                    "X-Miner-ID": miner_id
                },
                timeout=wait + 5
            )
            
            if response.status_code == 200:
                job = response.json()
                if job:
                    output(job, ctx.obj['output_format'])
                else:
                    output({"message": "No jobs available"}, ctx.obj['output_format'])
            else:
                error(f"Failed to poll: {response.status_code}")
    except httpx.TimeoutException:
        output({"message": f"No jobs available within {wait} seconds"}, ctx.obj['output_format'])
    except Exception as e:
        error(f"Network error: {e}")


@miner.command()
@click.option("--jobs", type=int, default=1, help="Number of jobs to process")
@click.option("--miner-id", default="cli-miner", help="Miner ID")
@click.pass_context
def mine(ctx, jobs: int, miner_id: str):
    """Mine continuously for specified number of jobs"""
    config = ctx.obj['config']
    
    processed = 0
    while processed < jobs:
        try:
            with httpx.Client() as client:
                # Poll for job
                response = client.get(
                    f"{config.coordinator_url}/v1/miners/poll",
                    headers={
                        "X-Api-Key": config.api_key or "",
                        "X-Miner-ID": miner_id
                    },
                    timeout=30
                )
                
                if response.status_code == 200:
                    job = response.json()
                    if job:
                        job_id = job.get('job_id')
                        output({
                            "job_id": job_id,
                            "status": "processing",
                            "job_number": processed + 1
                        }, ctx.obj['output_format'])
                        
                        # Simulate processing (in real implementation, do actual work)
                        time.sleep(2)
                        
                        # Submit result
                        result_response = client.post(
                            f"{config.coordinator_url}/v1/miners/{job_id}/result",
                            headers={
                                "Content-Type": "application/json",
                                "X-Api-Key": config.api_key or "",
                                "X-Miner-ID": miner_id
                            },
                            json={
                                "result": f"Processed job {job_id}",
                                "success": True
                            }
                        )
                        
                        if result_response.status_code == 200:
                            success(f"Job {job_id} completed successfully")
                            processed += 1
                        else:
                            error(f"Failed to submit result: {result_response.status_code}")
                    else:
                        # No job available, wait a bit
                        time.sleep(5)
                else:
                    error(f"Failed to poll: {response.status_code}")
                    break
                    
        except Exception as e:
            error(f"Error: {e}")
            break
    
    output({
        "total_processed": processed,
        "miner_id": miner_id
    }, ctx.obj['output_format'])


@miner.command()
@click.option("--miner-id", default="cli-miner", help="Miner ID")
@click.pass_context
def heartbeat(ctx, miner_id: str):
    """Send heartbeat to coordinator"""
    config = ctx.obj['config']
    
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/v1/miners/heartbeat?miner_id={miner_id}",
                headers={
                    "X-Api-Key": config.api_key or ""
                }
            )
            
            if response.status_code == 200:
                output({
                    "miner_id": miner_id,
                    "status": "heartbeat_sent",
                    "timestamp": time.time()
                }, ctx.obj['output_format'])
            else:
                error(f"Failed to send heartbeat: {response.status_code}")
    except Exception as e:
        error(f"Network error: {e}")


@miner.command()
@click.option("--miner-id", default="cli-miner", help="Miner ID")
@click.pass_context
def status(ctx, miner_id: str):
    """Check miner status"""
    config = ctx.obj['config']
    
    # This would typically query a miner status endpoint
    # For now, we'll just show the miner info
    output({
        "miner_id": miner_id,
        "coordinator": config.coordinator_url,
        "status": "active"
    }, ctx.obj['output_format'])


@miner.command()
@click.option("--miner-id", default="cli-miner", help="Miner ID")
@click.option("--from-time", help="Filter from timestamp (ISO format)")
@click.option("--to-time", help="Filter to timestamp (ISO format)")
@click.pass_context
def earnings(ctx, miner_id: str, from_time: Optional[str], to_time: Optional[str]):
    """Show miner earnings"""
    config = ctx.obj['config']
    
    try:
        params = {"miner_id": miner_id}
        if from_time:
            params["from_time"] = from_time
        if to_time:
            params["to_time"] = to_time
        
        with httpx.Client() as client:
            response = client.get(
                f"{config.coordinator_url}/v1/miners/{miner_id}/earnings",
                params=params,
                headers={"X-Api-Key": config.api_key or ""}
            )
            
            if response.status_code == 200:
                data = response.json()
                output(data, ctx.obj['output_format'])
            else:
                error(f"Failed to get earnings: {response.status_code}")
                ctx.exit(1)
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@miner.command(name="update-capabilities")
@click.option("--gpu", help="GPU model name")
@click.option("--memory", type=int, help="GPU memory in GB")
@click.option("--cuda-cores", type=int, help="Number of CUDA cores")
@click.option("--miner-id", default="cli-miner", help="Miner ID")
@click.pass_context
def update_capabilities(ctx, gpu: Optional[str], memory: Optional[int],
                        cuda_cores: Optional[int], miner_id: str):
    """Update miner GPU capabilities"""
    config = ctx.obj['config']
    
    capabilities = {}
    if gpu:
        capabilities["gpu"] = {"model": gpu}
    if memory:
        if "gpu" not in capabilities:
            capabilities["gpu"] = {}
        capabilities["gpu"]["memory_gb"] = memory
    if cuda_cores:
        if "gpu" not in capabilities:
            capabilities["gpu"] = {}
        capabilities["gpu"]["cuda_cores"] = cuda_cores
    
    if not capabilities:
        error("No capabilities specified. Use --gpu, --memory, or --cuda-cores.")
        return
    
    try:
        with httpx.Client() as client:
            response = client.put(
                f"{config.coordinator_url}/v1/miners/{miner_id}/capabilities",
                headers={
                    "Content-Type": "application/json",
                    "X-Api-Key": config.api_key or ""
                },
                json={"capabilities": capabilities}
            )
            
            if response.status_code == 200:
                output({
                    "miner_id": miner_id,
                    "status": "capabilities_updated",
                    "capabilities": capabilities
                }, ctx.obj['output_format'])
            else:
                error(f"Failed to update capabilities: {response.status_code}")
                ctx.exit(1)
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@miner.command()
@click.option("--miner-id", default="cli-miner", help="Miner ID")
@click.option("--force", is_flag=True, help="Force deregistration without confirmation")
@click.pass_context
def deregister(ctx, miner_id: str, force: bool):
    """Deregister miner from the coordinator"""
    if not force:
        if not click.confirm(f"Deregister miner '{miner_id}'?"):
            click.echo("Cancelled.")
            return
    
    config = ctx.obj['config']
    
    try:
        with httpx.Client() as client:
            response = client.delete(
                f"{config.coordinator_url}/v1/miners/{miner_id}",
                headers={"X-Api-Key": config.api_key or ""}
            )
            
            if response.status_code == 200:
                output({
                    "miner_id": miner_id,
                    "status": "deregistered"
                }, ctx.obj['output_format'])
            else:
                error(f"Failed to deregister: {response.status_code}")
                ctx.exit(1)
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@miner.command()
@click.option("--limit", default=10, help="Number of jobs to show")
@click.option("--type", "job_type", help="Filter by job type")
@click.option("--min-reward", type=float, help="Minimum reward threshold")
@click.option("--status", "job_status", help="Filter by status (pending, running, completed, failed)")
@click.option("--miner-id", default="cli-miner", help="Miner ID")
@click.pass_context
def jobs(ctx, limit: int, job_type: Optional[str], min_reward: Optional[float],
        job_status: Optional[str], miner_id: str):
    """List miner jobs with filtering"""
    config = ctx.obj['config']
    
    try:
        params = {"limit": limit, "miner_id": miner_id}
        if job_type:
            params["type"] = job_type
        if min_reward is not None:
            params["min_reward"] = min_reward
        if job_status:
            params["status"] = job_status
        
        with httpx.Client() as client:
            response = client.get(
                f"{config.coordinator_url}/v1/miners/{miner_id}/jobs",
                params=params,
                headers={"X-Api-Key": config.api_key or ""}
            )
            
            if response.status_code == 200:
                data = response.json()
                output(data, ctx.obj['output_format'])
            else:
                error(f"Failed to get jobs: {response.status_code}")
                ctx.exit(1)
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


def _process_single_job(config, miner_id: str, worker_id: int) -> Dict[str, Any]:
    """Process a single job (used by concurrent mine)"""
    try:
        with httpx.Client() as http_client:
            response = http_client.get(
                f"{config.coordinator_url}/v1/miners/poll",
                headers={
                    "X-Api-Key": config.api_key or "",
                    "X-Miner-ID": miner_id
                },
                timeout=30
            )
            
            if response.status_code == 200:
                job = response.json()
                if job:
                    job_id = job.get('job_id')
                    time.sleep(2)  # Simulate processing
                    
                    result_response = http_client.post(
                        f"{config.coordinator_url}/v1/miners/{job_id}/result",
                        headers={
                            "Content-Type": "application/json",
                            "X-Api-Key": config.api_key or "",
                            "X-Miner-ID": miner_id
                        },
                        json={"result": f"Processed by worker {worker_id}", "success": True}
                    )
                    
                    return {
                        "worker": worker_id,
                        "job_id": job_id,
                        "status": "completed" if result_response.status_code == 200 else "failed"
                    }
            return {"worker": worker_id, "status": "no_job"}
    except Exception as e:
        return {"worker": worker_id, "status": "error", "error": str(e)}


@miner.command(name="concurrent-mine")
@click.option("--workers", type=int, default=2, help="Number of concurrent workers")
@click.option("--jobs", "total_jobs", type=int, default=5, help="Total jobs to process")
@click.option("--miner-id", default="cli-miner", help="Miner ID")
@click.pass_context
def concurrent_mine(ctx, workers: int, total_jobs: int, miner_id: str):
    """Mine with concurrent job processing"""
    config = ctx.obj['config']
    
    success(f"Starting concurrent mining: {workers} workers, {total_jobs} jobs")
    
    completed = 0
    failed = 0
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        remaining = total_jobs
        while remaining > 0:
            batch_size = min(remaining, workers)
            futures = [
                executor.submit(_process_single_job, config, miner_id, i)
                for i in range(batch_size)
            ]
            
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                if result.get("status") == "completed":
                    completed += 1
                    remaining -= 1
                    output(result, ctx.obj['output_format'])
                elif result.get("status") == "no_job":
                    time.sleep(2)
                else:
                    failed += 1
                    remaining -= 1
    
    output({
        "status": "finished",
        "completed": completed,
        "failed": failed,
        "workers": workers
    }, ctx.obj['output_format'])
