"""``aitbc ai service`` — AI service registry inspection commands."""

import click

import aitbc_cli.commands.ai as _ai

from ._group import ai


@ai.group(
    epilog="""Examples:

  aitbc ai service status --name my-service

  aitbc ai service"""
)
def service():
    """Manage and inspect AI services registered with the coordinator."""
    pass


@service.command(
    epilog="""Examples:

  aitbc ai service list

  aitbc ai service list --output json"""
)
@click.option("--coordinator-url", help="Coordinator URL")
@click.option("--format", type=click.Choice(["table", "json"]), default=None, help="Output format")
@click.pass_context
def list(ctx, coordinator_url, format):
    """List available AI services registered with the coordinator."""
    _ai.get_config()

    try:
        coord_url = _ai._coordinator_base_url(ctx, coordinator_url)
        if not coord_url:
            _ai.abort(ctx, "Coordinator URL not configured")

        headers = _ai._auth_headers(ctx)
        http_client = _ai.AITBCHTTPClient(base_url=coord_url, timeout=30, headers=headers)
        result = http_client.get("/v1/services")

        _ai.output(result, _ai.resolve_output_format(ctx, format), title="AI Services")

    except _ai.NetworkError as e:
        _ai._abort_for_network(ctx, e)
    except _ai._OPS_ERRORS as e:
        _ai.abort(ctx, f"Error listing services: {e}", from_exception=e)


@service.command(
    epilog="""Examples:

  aitbc ai service status --name my-service

  aitbc ai service status --name my-service --output json"""
)
@click.option("--name", help="Service name")
@click.option("--coordinator-url", help="Coordinator URL")
@click.option("--format", type=click.Choice(["table", "json"]), default=None, help="Output format")
@click.pass_context
def service_status(ctx, name, coordinator_url, format):
    """Show the status of a named AI service."""
    _ai.get_config()

    try:
        coord_url = _ai._coordinator_base_url(ctx, coordinator_url)
        if not coord_url:
            _ai.abort(ctx, "Coordinator URL not configured")

        if not name:
            _ai.abort(ctx, "Service name required")

        headers = _ai._auth_headers(ctx)
        http_client = _ai.AITBCHTTPClient(base_url=coord_url, timeout=30, headers=headers)
        result = http_client.get(f"/v1/services/{name}")

        _ai.output(result, _ai.resolve_output_format(ctx, format), title=f"Service Status: {name}")

    except _ai.NetworkError as e:
        _ai._abort_for_network(ctx, e)
    except _ai._OPS_ERRORS as e:
        _ai.abort(ctx, f"Error getting service status: {e}", from_exception=e)


@service.command(
    epilog="""Examples:

  aitbc ai service test --name my-service

  aitbc ai service test --name my-service --output json"""
)
@click.option("--name", help="Service name")
@click.option("--coordinator-url", help="Coordinator URL")
@click.option("--format", type=click.Choice(["table", "json"]), default=None, help="Output format")
@click.pass_context
def test(ctx, name, coordinator_url, format):
    """Test an AI service endpoint by service name."""
    _ai.get_config()

    try:
        coord_url = _ai._coordinator_base_url(ctx, coordinator_url)
        if not coord_url:
            _ai.abort(ctx, "Coordinator URL not configured")

        if not name:
            _ai.abort(ctx, "Service name required")

        headers = _ai._require_auth_headers(ctx)
        http_client = _ai.AITBCHTTPClient(base_url=coord_url, timeout=30, headers=headers)
        result = http_client.post(f"/v1/services/{name}/test")

        _ai.success(f"Service {name} test completed")
        _ai.output(result, _ai.resolve_output_format(ctx, format), title=f"Service Test: {name}")

    except _ai.NetworkError as e:
        _ai._abort_for_network(ctx, e)
    except _ai._OPS_ERRORS as e:
        _ai.abort(ctx, f"Error testing service: {e}", from_exception=e)
