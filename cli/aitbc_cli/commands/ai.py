"""AI job submission and inspection commands for AITBC CLI"""


import click

from ..config import get_config
from ..utils import error, output, success
from ..utils.http_client import AITBCHTTPClient, NetworkError, get_logger

logger = get_logger(__name__)


@click.group()
def ai():
    """AI job submission and inspection"""
    pass


@ai.command()
@click.option('--wallet', help='Wallet name')
@click.option('--type', 'job_type', help='Job type')
@click.option('--prompt', help='Job prompt')
@click.option('--payment', type=float, help='Payment amount')
@click.option('--password', help='Wallet password')
@click.option('--password-file', type=click.Path(exists=True), help='Password file')
@click.option('--chain-id', help='Chain ID')
@click.option('--rpc-url', help='RPC URL')
@click.option('--coordinator-url', help='Coordinator URL')
@click.option('--format', type=click.Choice(['table', 'json']), default='table', help='Output format')
@click.pass_context
def submit(ctx, wallet, job_type, prompt, payment, password, password_file, chain_id, rpc_url, coordinator_url, format):
    """Submit an AI job"""
    config = get_config()

    try:
        # Get coordinator URL
        coord_url = coordinator_url or config.coordinator_url
        if not coord_url:
            error("Coordinator URL not configured")
            raise click.Abort()

        # Get RPC URL
        rpc = rpc_url or config.blockchain_rpc_url

        # Get password
        if password_file:
            with open(password_file) as f:
                password = f.read().strip()

        # Prepare job data
        job_data = {
            "job_type": job_type or "inference",
            "prompt": prompt or "",
        }

        if payment:
            job_data["payment"] = payment

        if wallet:
            job_data["wallet"] = wallet

        # Submit to coordinator
        http_client = AITBCHTTPClient(base_url=coord_url, timeout=30)
        result = http_client.post("/api/v1/jobs", json=job_data)

        success(f"Job submitted: {result.get('job_id')}")
        output(result, ctx.obj.get('output_format', format))

    except NetworkError as e:
        error(f"Network error: {e}")
        raise click.Abort()
    except Exception as e:
        error(f"Error submitting job: {e}")
        raise click.Abort()


@ai.command()
@click.option('--limit', type=int, default=10, help='Limit results')
@click.option('--status', help='Filter by status')
@click.option('--coordinator-url', help='Coordinator URL')
@click.option('--format', type=click.Choice(['table', 'json']), default='table', help='Output format')
@click.pass_context
def jobs(ctx, limit, status, coordinator_url, format):
    """List AI jobs"""
    config = get_config()

    try:
        coord_url = coordinator_url or config.coordinator_url
        if not coord_url:
            error("Coordinator URL not configured")
            raise click.Abort()

        http_client = AITBCHTTPClient(base_url=coord_url, timeout=30)
        params = {"limit": limit}
        if status:
            params["status"] = status

        result = http_client.get("/api/v1/jobs", params=params)
        output(result, ctx.obj.get('output_format', format), title="AI Jobs")

    except NetworkError as e:
        error(f"Network error: {e}")
        raise click.Abort()
    except Exception as e:
        error(f"Error listing jobs: {e}")
        raise click.Abort()


@ai.command()
@click.option('--job-id', help='Job ID')
@click.option('--coordinator-url', help='Coordinator URL')
@click.option('--format', type=click.Choice(['table', 'json']), default='table', help='Output format')
@click.pass_context
def status(ctx, job_id, coordinator_url, format):
    """Show AI job status"""
    config = get_config()

    try:
        coord_url = coordinator_url or config.coordinator_url
        if not coord_url:
            error("Coordinator URL not configured")
            raise click.Abort()

        if not job_id:
            error("Job ID required")
            raise click.Abort()

        http_client = AITBCHTTPClient(base_url=coord_url, timeout=30)
        result = http_client.get(f"/api/v1/jobs/{job_id}")

        output(result, ctx.obj.get('output_format', format), title=f"Job Status: {job_id}")

    except NetworkError as e:
        error(f"Network error: {e}")
        raise click.Abort()
    except Exception as e:
        error(f"Error getting job status: {e}")
        raise click.Abort()


@ai.group()
def service():
    """AI service management"""
    pass


@service.command()
@click.option('--coordinator-url', help='Coordinator URL')
@click.option('--format', type=click.Choice(['table', 'json']), default='table', help='Output format')
@click.pass_context
def list(ctx, coordinator_url, format):
    """List available AI services"""
    config = get_config()

    try:
        coord_url = coordinator_url or config.coordinator_url
        if not coord_url:
            error("Coordinator URL not configured")
            raise click.Abort()

        http_client = AITBCHTTPClient(base_url=coord_url, timeout=30)
        result = http_client.get("/api/v1/services")

        output(result, ctx.obj.get('output_format', format), title="AI Services")

    except NetworkError as e:
        error(f"Network error: {e}")
        raise click.Abort()
    except Exception as e:
        error(f"Error listing services: {e}")
        raise click.Abort()


@service.command()
@click.option('--name', help='Service name')
@click.option('--coordinator-url', help='Coordinator URL')
@click.option('--format', type=click.Choice(['table', 'json']), default='table', help='Output format')
@click.pass_context
def status(ctx, name, coordinator_url, format):
    """Check AI service status"""
    config = get_config()

    try:
        coord_url = coordinator_url or config.coordinator_url
        if not coord_url:
            error("Coordinator URL not configured")
            raise click.Abort()

        if not name:
            error("Service name required")
            raise click.Abort()

        http_client = AITBCHTTPClient(base_url=coord_url, timeout=30)
        result = http_client.get(f"/api/v1/services/{name}")

        output(result, ctx.obj.get('output_format', format), title=f"Service Status: {name}")

    except NetworkError as e:
        error(f"Network error: {e}")
        raise click.Abort()
    except Exception as e:
        error(f"Error getting service status: {e}")
        raise click.Abort()


@service.command()
@click.option('--name', help='Service name')
@click.option('--coordinator-url', help='Coordinator URL')
@click.option('--format', type=click.Choice(['table', 'json']), default='table', help='Output format')
@click.pass_context
def test(ctx, name, coordinator_url, format):
    """Test AI service endpoint"""
    config = get_config()

    try:
        coord_url = coordinator_url or config.coordinator_url
        if not coord_url:
            error("Coordinator URL not configured")
            raise click.Abort()

        if not name:
            error("Service name required")
            raise click.Abort()

        http_client = AITBCHTTPClient(base_url=coord_url, timeout=30)
        result = http_client.post(f"/api/v1/services/{name}/test")

        success(f"Service {name} test completed")
        output(result, ctx.obj.get('output_format', format), title=f"Service Test: {name}")

    except NetworkError as e:
        error(f"Network error: {e}")
        raise click.Abort()
    except Exception as e:
        error(f"Error testing service: {e}")
        raise click.Abort()


@ai.command()
@click.option('--job-id', help='Job ID')
@click.option('--coordinator-url', help='Coordinator URL')
@click.option('--format', type=click.Choice(['table', 'json']), default='table', help='Output format')
@click.pass_context
def results(ctx, job_id, coordinator_url, format):
    """Show AI job results"""
    config = get_config()

    try:
        coord_url = coordinator_url or config.coordinator_url
        if not coord_url:
            error("Coordinator URL not configured")
            raise click.Abort()

        if not job_id:
            error("Job ID required")
            raise click.Abort()

        http_client = AITBCHTTPClient(base_url=coord_url, timeout=30)
        result = http_client.get(f"/api/v1/jobs/{job_id}/results")

        output(result, ctx.obj.get('output_format', format), title=f"Job Results: {job_id}")

    except NetworkError as e:
        error(f"Network error: {e}")
        raise click.Abort()
    except Exception as e:
        error(f"Error getting job results: {e}")
        raise click.Abort()


@ai.command()
@click.option('--job-id', help='Job ID')
@click.option('--wallet', required=True, help='Wallet name')
@click.option('--password', help='Wallet password')
@click.option('--password-file', type=click.Path(exists=True), help='Password file')
@click.option('--coordinator-url', help='Coordinator URL')
@click.option('--format', type=click.Choice(['table', 'json']), default='table', help='Output format')
@click.pass_context
def cancel(ctx, job_id, wallet, password, password_file, coordinator_url, format):
    """Cancel AI job"""
    config = get_config()

    try:
        coord_url = coordinator_url or config.coordinator_url
        if not coord_url:
            error("Coordinator URL not configured")
            raise click.Abort()

        if not job_id:
            error("Job ID required")
            raise click.Abort()

        # Get password
        if password_file:
            with open(password_file) as f:
                password = f.read().strip()

        http_client = AITBCHTTPClient(base_url=coord_url, timeout=30)
        result = http_client.delete(f"/api/v1/jobs/{job_id}")

        success(f"Job {job_id} cancelled")
        output(result, ctx.obj.get('output_format', format))

    except NetworkError as e:
        error(f"Network error: {e}")
        raise click.Abort()
    except Exception as e:
        error(f"Error cancelling job: {e}")
        raise click.Abort()


@ai.command()
@click.option('--coordinator-url', help='Coordinator URL')
@click.option('--format', type=click.Choice(['table', 'json']), default='table', help='Output format')
@click.pass_context
def stats(ctx, coordinator_url, format):
    """AI service statistics"""
    config = get_config()

    try:
        coord_url = coordinator_url or config.coordinator_url
        if not coord_url:
            error("Coordinator URL not configured")
            raise click.Abort()

        http_client = AITBCHTTPClient(base_url=coord_url, timeout=30)
        result = http_client.get("/api/v1/stats")

        output(result, ctx.obj.get('output_format', format), title="AI Service Statistics")

    except NetworkError as e:
        error(f"Network error: {e}")
        raise click.Abort()
    except Exception as e:
        error(f"Error getting statistics: {e}")
        raise click.Abort()


@ai.command()
@click.option('--coordinator-url', help='Coordinator URL')
@click.option('--format', type=click.Choice(['table', 'json']), default='table', help='Output format')
@click.pass_context
def distribution_stats(ctx, coordinator_url, format):
    """Task distribution statistics from agent coordinator"""
    config = get_config()

    try:
        coord_url = coordinator_url or config.coordinator_url
        if not coord_url:
            error("Coordinator URL not configured")
            raise click.Abort()

        http_client = AITBCHTTPClient(base_url=coord_url, timeout=30)
        result = http_client.get("/api/v1/agent/stats/distribution")

        output(result, ctx.obj.get('output_format', format), title="Task Distribution Statistics")

    except NetworkError as e:
        error(f"Network error: {e}")
        raise click.Abort()
    except Exception as e:
        error(f"Error getting distribution statistics: {e}")
        raise click.Abort()
