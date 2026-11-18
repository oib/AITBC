"""``aitbc ai stats`` / ``distribution-stats`` — aggregate statistics commands."""

import click

import aitbc_cli.commands.ai as _ai

from ...auth import ExpiredAdminToken
from ._group import ai


@ai.command(
    epilog="""Examples:

  aitbc ai stats

  aitbc ai stats --output json"""
)
@click.option("--coordinator-url", help="Coordinator URL")
@click.option("--format", type=click.Choice(["table", "json"]), default=None, help="Output format")
@click.pass_context
def stats(ctx, coordinator_url, format):
    """Show aggregate AI service statistics (admin-only).

    /v1/admin/stats requires an admin-role credential: store one with
    `aitbc auth login --credential-name admin` (or pass --api-key).
    A plain client login gets 403.
    """
    config = _ai.get_config()

    try:
        coord_url = _ai._coordinator_base_url(ctx, coordinator_url)
        if not coord_url:
            _ai.abort(ctx, "Coordinator URL not configured")

        http_client = _ai.AITBCHTTPClient(
            base_url=coord_url,
            timeout=30,
            **_ai.auth_client_kwargs(
                ctx.obj.get("api_key"), config.api_key, credential="admin", warn_within_seconds=24 * 3600
            ),
        )
        result = http_client.get("/v1/admin/stats")

        _ai.output(result, _ai.resolve_output_format(ctx, format), title="AI Service Statistics")

    except ExpiredAdminToken as e:
        _ai.abort(ctx, str(e))
    except _ai.NetworkError as e:
        if _ai.http_response_status(e) == 403:
            _ai.abort(
                ctx,
                "aitbc ai stats is admin-only: /v1/admin/stats rejected the credential (403). "
                "Store an admin login with: aitbc auth login --credential-name admin",
                from_exception=e,
            )
        _ai._abort_for_network(ctx, e)
    except _ai._OPS_ERRORS as e:
        _ai.abort(ctx, f"Error getting statistics: {e}", from_exception=e)


@ai.command(
    epilog="""Examples:

  aitbc ai distribution-stats

  aitbc ai distribution-stats --output json"""
)
@click.option("--coordinator-url", help="Agent Coordinator URL")
@click.option("--format", type=click.Choice(["table", "json"]), default=None, help="Output format")
@click.pass_context
def distribution_stats(ctx, coordinator_url, format):
    """Show task distribution statistics from the agent coordinator.

    /api/v1/agent/messages/load-balancer/stats is admin-gated in the
    agent-coordinator's own auth realm: the `aitbc auth login`
    coordinator-api JWT is a different issuer/secret and is rejected with
    401. Pass an agent-coordinator admin credential via --api-key (the
    operator COORDINATOR_API_KEY when the service has one configured).
    """
    config = _ai.get_config()

    try:
        # The load balancer lives in the agent-coordinator, not the
        # coordinator-api — its stats include distribution counters.
        # agent_coordinator_url may resolve to a mounted nginx prefix, so
        # reduce it to the origin like agent_comm does.
        base_url = _ai.origin_base_url(
            coordinator_url or config.agent_coordinator_url or config.coordinator_api_url,
            "http://localhost:8107",
        )
        if not base_url:
            _ai.abort(ctx, "Agent Coordinator URL not configured")

        http_client = _ai.AITBCHTTPClient(
            base_url=base_url,
            timeout=30,
            **_ai.auth_client_kwargs(ctx.obj.get("api_key"), config.api_key),
        )
        result = http_client.get("/api/v1/agent/messages/load-balancer/stats")

        _ai.output(result, _ai.resolve_output_format(ctx, format), title="Task Distribution Statistics")

    except _ai.NetworkError as e:
        status = _ai.http_response_status(e)
        if status in (401, 403):
            _ai.abort(
                ctx,
                "load-balancer stats is admin-only on the agent-coordinator and does not accept "
                "the coordinator-api login JWT. Pass an agent-coordinator admin credential "
                "with --api-key (e.g. the operator COORDINATOR_API_KEY).",
                from_exception=e,
            )
        _ai._abort_for_network(ctx, e)
    except _ai._OPS_ERRORS as e:
        _ai.abort(ctx, f"Error getting distribution statistics: {e}", from_exception=e)
