"""AI job submission and inspection commands for AITBC CLI"""

import os

import click

from ..config import get_config
from ..utils import output, success
from ..utils.error_handling import abort
from ..utils.http_client import AITBCHTTPClient, NetworkError, get_logger

logger = get_logger(__name__)


def _auth_headers(ctx) -> dict[str, str] | None:
    """Return Authorization header if the CLI was invoked with --api-key."""
    token = ctx.obj.get("api_key")
    if token:
        return {"Authorization": f"Bearer {token}"}
    return None


@click.group()
def ai():
    """AI job submission and inspection"""
    pass


@ai.command()
@click.option("--wallet", help="Wallet name")
@click.option("--type", "job_type", help="Job type")
@click.option("--prompt", help="Job prompt")
@click.option("--model", help="Ollama model to use")
@click.option("--payment", type=float, help="Payment amount")
@click.option("--buyer-address", help="Customer wallet address for escrow")
@click.option("--provider-address", help="Provider wallet address for escrow")
@click.option("--password", help="Wallet password")
@click.option("--password-file", type=click.Path(exists=True), help="Password file")
@click.option("--chain-id", help="Chain ID")
@click.option("--rpc-url", help="RPC URL")
@click.option("--coordinator-url", help="Coordinator URL")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def submit(
    ctx,
    wallet,
    job_type,
    prompt,
    model,
    payment,
    buyer_address,
    provider_address,
    password,
    password_file,
    chain_id,
    rpc_url,
    coordinator_url,
    format,
):
    """Submit an AI job"""
    config = get_config()

    try:
        # Get coordinator URL
        coord_url = coordinator_url or config.coordinator_api_url
        if not coord_url:
            abort(ctx, "Coordinator URL not configured")

        # Get RPC URL
        _ = rpc_url or config.blockchain_rpc_url

        # Get password
        if password_file:
            with open(password_file) as f:
                _ = f.read().strip()

        # Prepare job data in the JobCreate shape expected by coordinator-api
        payload = {
            "type": job_type or "inference",
            "prompt": prompt or "",
        }

        if model:
            payload["model"] = model

        job_data = {
            "payload": payload,
            "constraints": {},
            "ttl_seconds": 900,
        }

        if payment:
            job_data["payment_amount"] = payment
            job_data["payment_currency"] = "AITBC"
            job_data["buyer_address"] = buyer_address or os.environ.get("CUSTOMER_WALLET_ADDRESS")
            job_data["provider_address"] = provider_address or os.environ.get("SHOP_WALLET_ADDRESS")

        # Submit to coordinator
        headers = _auth_headers(ctx)
        http_client = AITBCHTTPClient(base_url=coord_url, timeout=30, headers=headers)
        result = http_client.post("/v1/jobs", json=job_data)

        success(f"Job submitted: {result.get('job_id')}")
        output(result, ctx.obj.get("output_format", format))

    except NetworkError as e:
        abort(ctx, f"Network error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error submitting job: {e}", from_exception=e)


@ai.command()
@click.option("--limit", type=int, default=10, help="Limit results")
@click.option("--status", help="Filter by status")
@click.option("--coordinator-url", help="Coordinator URL")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def jobs(ctx, limit, status, coordinator_url, format):
    """List AI jobs"""
    config = get_config()

    try:
        coord_url = coordinator_url or config.coordinator_api_url
        if not coord_url:
            abort(ctx, "Coordinator URL not configured")

        headers = _auth_headers(ctx)
        http_client = AITBCHTTPClient(base_url=coord_url, timeout=30, headers=headers)
        params = {"limit": limit}
        if status:
            params["status"] = status

        result = http_client.get("/v1/jobs", params=params)
        output(result, ctx.obj.get("output_format", format), title="AI Jobs")

    except NetworkError as e:
        abort(ctx, f"Network error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error listing jobs: {e}", from_exception=e)


@ai.command()
@click.option("--job-id", help="Job ID")
@click.option("--coordinator-url", help="Coordinator URL")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def status(ctx, job_id, coordinator_url, format):
    """Show AI job status"""
    config = get_config()

    try:
        coord_url = coordinator_url or config.coordinator_api_url
        if not coord_url:
            abort(ctx, "Coordinator URL not configured")

        if not job_id:
            abort(ctx, "Job ID required")

        headers = _auth_headers(ctx)
        http_client = AITBCHTTPClient(base_url=coord_url, timeout=30, headers=headers)
        result = http_client.get(f"/v1/jobs/{job_id}")

        output(result, ctx.obj.get("output_format", format), title=f"Job Status: {job_id}")

    except NetworkError as e:
        abort(ctx, f"Network error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error getting job status: {e}", from_exception=e)


@ai.group()
def service():
    """AI service management"""
    pass


@service.command()
@click.option("--coordinator-url", help="Coordinator URL")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def list(ctx, coordinator_url, format):
    """List available AI services"""
    config = get_config()

    try:
        coord_url = coordinator_url or config.coordinator_api_url
        if not coord_url:
            abort(ctx, "Coordinator URL not configured")

        headers = _auth_headers(ctx)
        http_client = AITBCHTTPClient(base_url=coord_url, timeout=30, headers=headers)
        result = http_client.get("/v1/services")

        output(result, ctx.obj.get("output_format", format), title="AI Services")

    except NetworkError as e:
        abort(ctx, f"Network error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error listing services: {e}", from_exception=e)


@service.command()
@click.option("--name", help="Service name")
@click.option("--coordinator-url", help="Coordinator URL")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def service_status(ctx, name, coordinator_url, format):
    """Check AI service status"""
    config = get_config()

    try:
        coord_url = coordinator_url or config.coordinator_api_url
        if not coord_url:
            abort(ctx, "Coordinator URL not configured")

        if not name:
            abort(ctx, "Service name required")

        headers = _auth_headers(ctx)
        http_client = AITBCHTTPClient(base_url=coord_url, timeout=30, headers=headers)
        result = http_client.get(f"/v1/services/{name}")

        output(result, ctx.obj.get("output_format", format), title=f"Service Status: {name}")

    except NetworkError as e:
        abort(ctx, f"Network error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error getting service status: {e}", from_exception=e)


@service.command()
@click.option("--name", help="Service name")
@click.option("--coordinator-url", help="Coordinator URL")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def test(ctx, name, coordinator_url, format):
    """Test AI service endpoint"""
    config = get_config()

    try:
        coord_url = coordinator_url or config.coordinator_api_url
        if not coord_url:
            abort(ctx, "Coordinator URL not configured")

        if not name:
            abort(ctx, "Service name required")

        headers = _auth_headers(ctx)
        http_client = AITBCHTTPClient(base_url=coord_url, timeout=30, headers=headers)
        result = http_client.post(f"/v1/services/{name}/test")

        success(f"Service {name} test completed")
        output(result, ctx.obj.get("output_format", format), title=f"Service Test: {name}")

    except NetworkError as e:
        abort(ctx, f"Network error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error testing service: {e}", from_exception=e)


@ai.command()
@click.option("--job-id", help="Job ID")
@click.option("--coordinator-url", help="Coordinator URL")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def results(ctx, job_id, coordinator_url, format):
    """Show AI job results"""
    config = get_config()

    try:
        coord_url = coordinator_url or config.coordinator_api_url
        if not coord_url:
            abort(ctx, "Coordinator URL not configured")

        if not job_id:
            abort(ctx, "Job ID required")

        headers = _auth_headers(ctx)
        http_client = AITBCHTTPClient(base_url=coord_url, timeout=30, headers=headers)
        result = http_client.get(f"/v1/jobs/{job_id}/result")

        output(result, ctx.obj.get("output_format", format), title=f"Job Results: {job_id}")

    except NetworkError as e:
        abort(ctx, f"Network error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error getting job results: {e}", from_exception=e)


@ai.command()
@click.option("--job-id", help="Job ID")
@click.option("--wallet", required=True, help="Wallet name")
@click.option("--password", help="Wallet password")
@click.option("--password-file", type=click.Path(exists=True), help="Password file")
@click.option("--coordinator-url", help="Coordinator URL")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def cancel(ctx, job_id, wallet, password, password_file, coordinator_url, format):
    """Cancel AI job"""
    config = get_config()

    try:
        coord_url = coordinator_url or config.coordinator_api_url
        if not coord_url:
            abort(ctx, "Coordinator URL not configured")

        if not job_id:
            abort(ctx, "Job ID required")

        # Get password
        if password_file:
            with open(password_file) as f:
                _ = f.read().strip()

        headers = _auth_headers(ctx)
        http_client = AITBCHTTPClient(base_url=coord_url, timeout=30, headers=headers)
        result = http_client.post(f"/v1/jobs/{job_id}/cancel")

        success(f"Job {job_id} cancelled")
        output(result, ctx.obj.get("output_format", format))

    except NetworkError as e:
        abort(ctx, f"Network error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error cancelling job: {e}", from_exception=e)


@ai.command()
@click.option("--coordinator-url", help="Coordinator URL")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def stats(ctx, coordinator_url, format):
    """AI service statistics"""
    config = get_config()

    try:
        coord_url = coordinator_url or config.coordinator_api_url
        if not coord_url:
            abort(ctx, "Coordinator URL not configured")

        headers = _auth_headers(ctx)
        http_client = AITBCHTTPClient(base_url=coord_url, timeout=30, headers=headers)
        result = http_client.get("/v1/stats")

        output(result, ctx.obj.get("output_format", format), title="AI Service Statistics")

    except NetworkError as e:
        abort(ctx, f"Network error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error getting statistics: {e}", from_exception=e)


@ai.command()
@click.option("--coordinator-url", help="Coordinator URL")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def distribution_stats(ctx, coordinator_url, format):
    """Task distribution statistics from agent coordinator"""
    config = get_config()

    try:
        coord_url = coordinator_url or config.coordinator_api_url
        if not coord_url:
            abort(ctx, "Coordinator URL not configured")

        headers = _auth_headers(ctx)
        http_client = AITBCHTTPClient(base_url=coord_url, timeout=30, headers=headers)
        result = http_client.get("/v1/agent/stats/distribution")

        output(result, ctx.obj.get("output_format", format), title="Task Distribution Statistics")

    except NetworkError as e:
        abort(ctx, f"Network error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error getting distribution statistics: {e}", from_exception=e)
