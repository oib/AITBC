"""
Workflow commands for AITBC CLI
"""

import json
import os
from typing import Any

import click
import httpx
import yaml

from ..auth import ExpiredAdminToken
from ..config import get_config
from ..utils import resolve_output_format, success
from ..utils.error_handling import CLIError, abort
from ..utils.http_client import auth_headers, service_root_url

# Expected failure surface for the workflow fallbacks below (#1860): httpx
# transport, yaml parse, filesystem and data-shape builtins.
_WORKFLOW_ERRORS = (
    httpx.HTTPError,
    yaml.YAMLError,
    OSError,
    ArithmeticError,
    ValueError,
    KeyError,
    TypeError,
    AttributeError,
    RuntimeError,
)


def _coordinator_url(config_obj) -> str:
    """Coordinator service root; configured values may already carry /v1."""
    return service_root_url(getattr(config_obj, "coordinator_api_url", None), "http://localhost:8203")


# All /v1/agents/workflows/* and /v1/agents/executions/* endpoints are
# AdminDep-gated server-side (coordinator-api agent_router.py). A plain
# `auth login` client JWT gets 403 "Role required" — these commands resolve
# the `admin` credential slot first and surface the gate explicitly (#2231).
_ADMIN_REQUIRED_HINT = (
    "requires an admin-role credential. Store an admin login with "
    "`aitbc auth login --credential-name admin`, pass --api-key, or set "
    "COORDINATOR_API_KEY to an admin JWT."
)


def _coordinator_headers(config_obj, ctx=None) -> dict[str, str]:
    """Stored ``auth login`` admin/client JWT as Bearer, else the configured key as X-API-Key."""
    explicit = (ctx.obj or {}).get("api_key") if ctx is not None else None
    return auth_headers(
        explicit_key=explicit,
        config_key=getattr(config_obj, "coordinator_api_key", None) or os.environ.get("COORDINATOR_API_KEY"),
        credential="admin",
    )


def _abort_403(command: str, body: str) -> None:
    """Abort on a 403 with the credential the endpoint actually demands."""
    abort(None, f"{command} {_ADMIN_REQUIRED_HINT} (HTTP 403 — {body[:200]})")


@click.group(
    epilog="""Examples:

  aitbc workflow list

  aitbc workflow run --workflow-name gpu-market"""
)
def workflow():
    """List, run, stop, and check the status of coordinator workflows."""
    pass


@workflow.command(
    epilog="""Examples:

  aitbc workflow run --workflow-name gpu-market

  aitbc workflow run --workflow-name ai-job-processing --config /tmp/workflow.yaml"""
)
@click.option("--workflow-name", "workflow_name", required=True, help="The Workflow name.")
@click.option("--config", help="Workflow configuration file")
@click.option("--dry-run", is_flag=True, help="Dry run without executing")
@click.pass_context
def run(ctx, workflow_name: str, config: str | None, dry_run: bool):
    """Run a workflow by name with optional configuration (admin-only)."""
    try:
        import httpx

        if dry_run:
            success(f"Dry run for workflow {workflow_name}")
            click.echo("Would execute workflow without making changes")
            return

        config_obj = get_config()
        coordinator_url = _coordinator_url(config_obj)
        headers = _coordinator_headers(config_obj, ctx)

        # Load config if provided
        workflow_config: dict[str, Any] = {}
        if config:
            with open(config) as f:
                workflow_config = yaml.safe_load(f) or {}

        execution_payload = {"workflow_id": workflow_name, "inputs": workflow_config}

        response = httpx.post(
            f"{coordinator_url}/v1/agents/workflows/{workflow_name}/execute",
            json=execution_payload,
            headers=headers,
        )

        if response.status_code == 403:
            _abort_403(f"workflow run {workflow_name}", response.text)
        if response.status_code != 200:
            abort(None, f"Failed to start workflow: {response.text}")

        result = response.json()
        execution_id = result.get("execution_id")

        success(f"Run workflow {workflow_name}")
        if config:
            click.echo(f"Using config: {config}")

        click.echo(f"Execution ID: {execution_id}")
        click.echo(f"Status: {result.get('status', 'Running')}")

    except FileNotFoundError:
        abort(None, f"Config file not found: {config}")
    except ExpiredAdminToken as e:
        abort(None, str(e))
    except CLIError:
        raise
    except _WORKFLOW_ERRORS as e:
        abort(None, f"Error running workflow: {e}")


@workflow.command(
    epilog="""Examples:

  aitbc workflow list

  aitbc workflow list --output json"""
)
@click.option("--format", type=click.Choice(["table", "json"]), default=None, help="Output format")
@click.pass_context
def list(ctx, format: str):
    """List all available workflows from the coordinator (admin-only)."""
    fmt = resolve_output_format(ctx, format)
    config_obj = get_config()
    coordinator_url = _coordinator_url(config_obj)
    try:
        headers = _coordinator_headers(config_obj, ctx)
    except ExpiredAdminToken as e:
        abort(None, str(e))

    try:
        import httpx

        response = httpx.get(f"{coordinator_url}/v1/agents/workflows", headers=headers, timeout=15)
    except Exception as e:  # noqa: BLE001 - surface any transport/config failure to the caller
        abort(None, f"Error listing workflows: {e}")

    if response.status_code == 403:
        _abort_403("workflow list", response.text)
    if response.status_code != 200:
        abort(None, f"Failed to list workflows: HTTP {response.status_code} — {response.text[:200]}")

    raw = response.json()
    # ``list`` is shadowed by this module's command function — use builtins.
    import builtins

    items = raw if isinstance(raw, builtins.list) else raw.get("workflows", []) if isinstance(raw, builtins.dict) else []
    workflows = [
        {
            "name": w.get("name", w.get("id", "?")),
            "id": w.get("id"),
            "owner_id": w.get("owner_id"),
            "version": w.get("version"),
            "steps": len(w.get("steps") or {}),
        }
        for w in items
        if isinstance(w, dict)
    ]

    if fmt == "json":
        click.echo(json.dumps(workflows, indent=2))
    else:
        if not workflows:
            success("No workflows registered")
            return
        success("Available workflows:")
        for wf in workflows:
            click.echo(f"  - {wf['name']}: {wf['steps']} steps (v{wf.get('version', '?')})")


@workflow.command(
    epilog="""Examples:

  aitbc workflow status --workflow-name gpu-market"""
)
@click.option("--workflow-name", "workflow_name", required=True, help="The Workflow name.")
@click.pass_context
def status(ctx, workflow_name: str):
    """Get the execution status of a workflow by name (admin-only)."""
    try:
        import httpx

        config_obj = get_config()
        coordinator_url = _coordinator_url(config_obj)
        headers = _coordinator_headers(config_obj, ctx)

        response = httpx.get(
            f"{coordinator_url}/v1/agents/executions/{workflow_name}/status",
            headers=headers,
        )

        if response.status_code == 403:
            _abort_403(f"workflow status {workflow_name}", response.text)
        if response.status_code != 200:
            abort(None, f"Failed to get execution status: {response.text}")

        result = response.json()

        success(f"Get status for execution {workflow_name}")
        click.echo(f"Status: {result.get('status', 'Unknown')}")
        click.echo(f"Workflow ID: {result.get('workflow_id', 'Unknown')}")
        click.echo(f"Current step: {result.get('current_step', 0)}/{result.get('total_steps', 0)}")
        if result.get("error_message"):
            click.echo(f"Error: {result['error_message']}")

    except ExpiredAdminToken as e:
        abort(None, str(e))
    except CLIError:
        raise
    except _WORKFLOW_ERRORS as e:
        abort(None, f"Error getting workflow status: {e}")


@workflow.command(
    epilog="""Examples:

  aitbc workflow stop --workflow-name exec-123"""
)
@click.option("--workflow-name", "workflow_name", required=True, help="The Workflow name.")
@click.pass_context
def stop(ctx, workflow_name: str):
    """Stop a running workflow by its execution ID (admin-only)."""
    try:
        import httpx

        config_obj = get_config()
        coordinator_url = _coordinator_url(config_obj)
        headers = _coordinator_headers(config_obj, ctx)

        response = httpx.post(
            f"{coordinator_url}/v1/agents/workflows/{workflow_name}/cancel",
            headers=headers,
            params={"execution_id": workflow_name},
        )

        if response.status_code == 403:
            _abort_403(f"workflow stop {workflow_name}", response.text)
        if response.status_code != 200:
            abort(None, f"Failed to cancel workflow: {response.text}")

        success(f"Cancel workflow {workflow_name}")
        click.echo("Status: Cancelled")

    except ExpiredAdminToken as e:
        abort(None, str(e))
    except CLIError:
        raise
    except _WORKFLOW_ERRORS as e:
        abort(None, f"Error stopping workflow: {e}")
