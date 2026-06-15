"""
Workflow commands for AITBC CLI
"""

import json
import os

import click
import yaml

from ..config import get_config
from ..utils import error, success


@click.group()
def workflow():
    """Workflow management commands"""
    pass


@workflow.command()
@click.argument("workflow_name")
@click.option("--config", help="Workflow configuration file")
@click.option("--dry-run", is_flag=True, help="Dry run without executing")
def run(workflow_name: str, config: str | None, dry_run: bool):
    """Run a workflow"""
    try:
        import httpx

        config_obj = get_config()
        coordinator_url = getattr(config_obj, "coordinator_url", "http://localhost:8203")
        api_key = getattr(config_obj, "coordinator_api_key", os.environ.get("COORDINATOR_API_KEY"))

        if dry_run:
            success(f"Dry run for workflow {workflow_name}")
            click.echo("Would execute workflow without making changes")
            return

        # Load config if provided
        workflow_config = {}
        if config:
            with open(config) as f:
                workflow_config = yaml.safe_load(f) or {}

        # Submit workflow to coordinator API
        headers = {}
        if api_key:
            headers["X-API-Key"] = api_key

        execution_payload = {"workflow_name": workflow_name, "config": workflow_config, "dry_run": False}

        response = httpx.post(f"{coordinator_url}/v1/workflows/execute", json=execution_payload, headers=headers)

        if response.status_code != 200:
            error(f"Failed to start workflow: {response.text}")
            return

        result = response.json()
        execution_id = result.get("execution_id")

        success(f"Run workflow {workflow_name}")
        if config:
            click.echo(f"Using config: {config}")

        click.echo(f"Execution ID: {execution_id}")
        click.echo("Status: Running")

    except FileNotFoundError:
        error(f"Config file not found: {config}")
        return
    except Exception as e:
        error(f"Error running workflow: {e}")
        return


@workflow.command()
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
def list(format: str):
    """List available workflows"""
    workflows = [
        {"name": "gpu-marketplace", "status": "active", "steps": 5},
        {"name": "ai-job-processing", "status": "active", "steps": 3},
        {"name": "mining-optimization", "status": "inactive", "steps": 4},
    ]

    if format == "json":
        click.echo(json.dumps(workflows, indent=2))
    else:
        success("Available workflows:")
        for wf in workflows:
            click.echo(f"  - {wf['name']}: {wf['status']} ({wf['steps']} steps)")


@workflow.command()
@click.argument("workflow_name")
def status(workflow_name: str):
    """Get workflow status"""
    try:
        import httpx

        config_obj = get_config()
        coordinator_url = getattr(config_obj, "coordinator_url", "http://localhost:8203")
        api_key = getattr(config_obj, "coordinator_api_key", os.environ.get("COORDINATOR_API_KEY"))

        headers = {}
        if api_key:
            headers["X-API-Key"] = api_key

        response = httpx.get(f"{coordinator_url}/v1/workflows/{workflow_name}/status", headers=headers)

        if response.status_code != 200:
            error(f"Failed to get workflow status: {response.text}")
            return

        result = response.json()

        success(f"Get status for workflow {workflow_name}")
        click.echo(f"Status: {result.get('status', 'Unknown')}")
        click.echo(f"Last execution: {result.get('last_execution', 'Never')}")
        if result.get("execution_id"):
            click.echo(f"Execution ID: {result['execution_id']}")

    except Exception as e:
        error(f"Error getting workflow status: {e}")


@workflow.command()
@click.argument("workflow_name")
def stop(workflow_name: str):
    """Stop a running workflow"""
    try:
        import httpx

        config_obj = get_config()
        coordinator_url = getattr(config_obj, "coordinator_url", "http://localhost:8203")
        api_key = getattr(config_obj, "coordinator_api_key", os.environ.get("COORDINATOR_API_KEY"))

        headers = {}
        if api_key:
            headers["X-API-Key"] = api_key

        response = httpx.post(f"{coordinator_url}/v1/workflows/{workflow_name}/stop", headers=headers)

        if response.status_code != 200:
            error(f"Failed to stop workflow: {response.text}")
            return

        success(f"Stop workflow {workflow_name}")
        click.echo("Status: Stopped")

    except Exception as e:
        error(f"Error stopping workflow: {e}")
