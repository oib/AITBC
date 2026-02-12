"""Client commands for AITBC CLI"""

import click
import httpx
import json
import time
from typing import Optional
from ..utils import output, error, success


@click.group()
def client():
    """Submit and manage jobs"""
    pass


@client.command()
@click.option("--type", "job_type", default="inference", help="Job type")
@click.option("--prompt", help="Prompt for inference jobs")
@click.option("--model", help="Model name")
@click.option("--ttl", default=900, help="Time to live in seconds")
@click.option("--file", type=click.File('r'), help="Submit job from JSON file")
@click.option("--retries", default=0, help="Number of retry attempts (0 = no retry)")
@click.option("--retry-delay", default=1.0, help="Initial retry delay in seconds")
@click.pass_context
def submit(ctx, job_type: str, prompt: Optional[str], model: Optional[str], 
           ttl: int, file, retries: int, retry_delay: float):
    """Submit a job to the coordinator"""
    config = ctx.obj['config']
    
    # Build job data
    if file:
        try:
            task_data = json.load(file)
        except Exception as e:
            error(f"Failed to read job file: {e}")
            return
    else:
        task_data = {"type": job_type}
        if prompt:
            task_data["prompt"] = prompt
        if model:
            task_data["model"] = model
    
    # Submit job with retry and exponential backoff
    max_attempts = retries + 1
    for attempt in range(1, max_attempts + 1):
        try:
            with httpx.Client() as client:
                response = client.post(
                    f"{config.coordinator_url}/v1/jobs",
                    headers={
                        "Content-Type": "application/json",
                        "X-Api-Key": config.api_key or ""
                    },
                    json={
                        "payload": task_data,
                        "ttl_seconds": ttl
                    }
                )
                
                if response.status_code == 201:
                    job = response.json()
                    result = {
                        "job_id": job.get('job_id'),
                        "status": "submitted",
                        "message": "Job submitted successfully"
                    }
                    if attempt > 1:
                        result["attempts"] = attempt
                    output(result, ctx.obj['output_format'])
                    return
                else:
                    if attempt < max_attempts:
                        delay = retry_delay * (2 ** (attempt - 1))
                        click.echo(f"Attempt {attempt}/{max_attempts} failed ({response.status_code}), retrying in {delay:.1f}s...")
                        time.sleep(delay)
                    else:
                        error(f"Failed to submit job: {response.status_code} - {response.text}")
                        ctx.exit(response.status_code)
        except Exception as e:
            if attempt < max_attempts:
                delay = retry_delay * (2 ** (attempt - 1))
                click.echo(f"Attempt {attempt}/{max_attempts} failed ({e}), retrying in {delay:.1f}s...")
                time.sleep(delay)
            else:
                error(f"Network error after {max_attempts} attempts: {e}")
                ctx.exit(1)


@client.command()
@click.argument("job_id")
@click.pass_context
def status(ctx, job_id: str):
    """Check job status"""
    config = ctx.obj['config']
    
    try:
        with httpx.Client() as client:
            response = client.get(
                f"{config.coordinator_url}/v1/jobs/{job_id}",
                headers={"X-Api-Key": config.api_key or ""}
            )
            
            if response.status_code == 200:
                data = response.json()
                output(data, ctx.obj['output_format'])
            else:
                error(f"Failed to get job status: {response.status_code}")
                ctx.exit(1)
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@client.command()
@click.option("--limit", default=10, help="Number of blocks to show")
@click.pass_context
def blocks(ctx, limit: int):
    """List recent blocks"""
    config = ctx.obj['config']
    
    try:
        with httpx.Client() as client:
            response = client.get(
                f"{config.coordinator_url}/v1/explorer/blocks",
                params={"limit": limit},
                headers={"X-Api-Key": config.api_key or ""}
            )
            
            if response.status_code == 200:
                blocks = response.json()
                output(blocks, ctx.obj['output_format'])
            else:
                error(f"Failed to get blocks: {response.status_code}")
                ctx.exit(1)
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@client.command()
@click.argument("job_id")
@click.pass_context
def cancel(ctx, job_id: str):
    """Cancel a job"""
    config = ctx.obj['config']
    
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/v1/jobs/{job_id}/cancel",
                headers={"X-Api-Key": config.api_key or ""}
            )
            
            if response.status_code == 200:
                success(f"Job {job_id} cancelled")
            else:
                error(f"Failed to cancel job: {response.status_code}")
                ctx.exit(1)
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@client.command()
@click.option("--limit", default=10, help="Number of receipts to show")
@click.option("--job-id", help="Filter by job ID")
@click.option("--status", help="Filter by status")
@click.pass_context
def receipts(ctx, limit: int, job_id: Optional[str], status: Optional[str]):
    """List job receipts"""
    config = ctx.obj['config']
    
    try:
        params = {"limit": limit}
        if job_id:
            params["job_id"] = job_id
        if status:
            params["status"] = status
            
        with httpx.Client() as client:
            response = client.get(
                f"{config.coordinator_url}/v1/explorer/receipts",
                params=params,
                headers={"X-Api-Key": config.api_key or ""}
            )
            
            if response.status_code == 200:
                receipts = response.json()
                output(receipts, ctx.obj['output_format'])
            else:
                error(f"Failed to get receipts: {response.status_code}")
                ctx.exit(1)
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@client.command()
@click.option("--limit", default=10, help="Number of jobs to show")
@click.option("--status", help="Filter by status (pending, running, completed, failed)")
@click.option("--type", help="Filter by job type")
@click.option("--from-time", help="Filter jobs from this timestamp (ISO format)")
@click.option("--to-time", help="Filter jobs until this timestamp (ISO format)")
@click.pass_context
def history(ctx, limit: int, status: Optional[str], type: Optional[str],
            from_time: Optional[str], to_time: Optional[str]):
    """Show job history with filtering options"""
    config = ctx.obj['config']
    
    try:
        params = {"limit": limit}
        if status:
            params["status"] = status
        if type:
            params["type"] = type
        if from_time:
            params["from_time"] = from_time
        if to_time:
            params["to_time"] = to_time
            
        with httpx.Client() as client:
            response = client.get(
                f"{config.coordinator_url}/v1/jobs/history",
                params=params,
                headers={"X-Api-Key": config.api_key or ""}
            )
            
            if response.status_code == 200:
                jobs = response.json()
                output(jobs, ctx.obj['output_format'])
            else:
                error(f"Failed to get job history: {response.status_code}")
                ctx.exit(1)
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@client.command(name="batch-submit")
@click.argument("file_path", type=click.Path(exists=True))
@click.option("--format", "file_format", type=click.Choice(["json", "csv"]), default=None, help="File format (auto-detected if not specified)")
@click.option("--retries", default=0, help="Retry attempts per job")
@click.option("--delay", default=0.5, help="Delay between submissions (seconds)")
@click.pass_context
def batch_submit(ctx, file_path: str, file_format: Optional[str], retries: int, delay: float):
    """Submit multiple jobs from a CSV or JSON file"""
    import csv
    from pathlib import Path
    from ..utils import progress_bar

    config = ctx.obj['config']
    path = Path(file_path)

    if not file_format:
        file_format = "csv" if path.suffix.lower() == ".csv" else "json"

    jobs_data = []
    if file_format == "json":
        with open(path) as f:
            data = json.load(f)
            jobs_data = data if isinstance(data, list) else [data]
    else:
        with open(path) as f:
            reader = csv.DictReader(f)
            jobs_data = list(reader)

    if not jobs_data:
        error("No jobs found in file")
        return

    results = {"submitted": 0, "failed": 0, "job_ids": []}

    with progress_bar("Submitting jobs...", total=len(jobs_data)) as (progress, task):
        for i, job in enumerate(jobs_data):
            try:
                task_data = {"type": job.get("type", "inference")}
                if "prompt" in job:
                    task_data["prompt"] = job["prompt"]
                if "model" in job:
                    task_data["model"] = job["model"]

                with httpx.Client() as http_client:
                    response = http_client.post(
                        f"{config.coordinator_url}/v1/jobs",
                        headers={
                            "Content-Type": "application/json",
                            "X-Api-Key": config.api_key or ""
                        },
                        json={"payload": task_data, "ttl_seconds": int(job.get("ttl", 900))}
                    )
                    if response.status_code == 201:
                        result = response.json()
                        results["submitted"] += 1
                        results["job_ids"].append(result.get("job_id"))
                    else:
                        results["failed"] += 1
            except Exception:
                results["failed"] += 1

            progress.update(task, advance=1)
            if delay and i < len(jobs_data) - 1:
                time.sleep(delay)

    output(results, ctx.obj['output_format'])


@client.command(name="template")
@click.argument("action", type=click.Choice(["save", "list", "run", "delete"]))
@click.option("--name", help="Template name")
@click.option("--type", "job_type", help="Job type")
@click.option("--prompt", help="Prompt text")
@click.option("--model", help="Model name")
@click.option("--ttl", type=int, default=900, help="TTL in seconds")
@click.pass_context
def template(ctx, action: str, name: Optional[str], job_type: Optional[str],
             prompt: Optional[str], model: Optional[str], ttl: int):
    """Manage job templates for repeated tasks"""
    from pathlib import Path

    template_dir = Path.home() / ".aitbc" / "templates"
    template_dir.mkdir(parents=True, exist_ok=True)

    if action == "save":
        if not name:
            error("Template name required (--name)")
            return
        template_data = {"type": job_type or "inference", "ttl": ttl}
        if prompt:
            template_data["prompt"] = prompt
        if model:
            template_data["model"] = model
        with open(template_dir / f"{name}.json", "w") as f:
            json.dump(template_data, f, indent=2)
        output({"status": "saved", "name": name, "template": template_data}, ctx.obj['output_format'])

    elif action == "list":
        templates = []
        for tf in template_dir.glob("*.json"):
            with open(tf) as f:
                data = json.load(f)
            templates.append({"name": tf.stem, **data})
        output(templates if templates else {"message": "No templates found"}, ctx.obj['output_format'])

    elif action == "run":
        if not name:
            error("Template name required (--name)")
            return
        tf = template_dir / f"{name}.json"
        if not tf.exists():
            error(f"Template '{name}' not found")
            return
        with open(tf) as f:
            tmpl = json.load(f)
        if prompt:
            tmpl["prompt"] = prompt
        if model:
            tmpl["model"] = model
        ctx.invoke(submit, job_type=tmpl.get("type", "inference"),
                   prompt=tmpl.get("prompt"), model=tmpl.get("model"),
                   ttl=tmpl.get("ttl", 900), file=None, retries=0, retry_delay=1.0)

    elif action == "delete":
        if not name:
            error("Template name required (--name)")
            return
        tf = template_dir / f"{name}.json"
        if not tf.exists():
            error(f"Template '{name}' not found")
            return
        tf.unlink()
        output({"status": "deleted", "name": name}, ctx.obj['output_format'])
