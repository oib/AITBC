"""Economics commands for AITBC CLI."""

from __future__ import annotations

import os

import click
import httpx

from aitbc.exceptions import AITBCError
from ..config import get_config
from ..utils import output
from ..utils.error_handling import CLIError, abort
from ..utils.http_client import AITBCHTTPClient, NetworkError, auth_client_kwargs, service_root_url

# Expected failure surface for the command handlers below: filesystem/JSON,
# data-shape, runtime, optional-dependency imports, HTTP-client errors and
# both error hierarchies (CLIError, aitbc_errors.AITBCError). RuntimeError
# covers generic runtime failures; abort() raises CLIError (already listed),
# preserving the previous re-abort behaviour. BaseExceptions still propagate
# (#1864).
_OPS_ERRORS = (
    OSError,
    ValueError,
    KeyError,
    TypeError,
    AttributeError,
    RuntimeError,
    ImportError,
    CLIError,
    AITBCError,
    httpx.HTTPError,
)


def _api_client(explicit_key: str | None = None) -> AITBCHTTPClient | None:
    """Return a client for the coordinator API if a URL is configured.

    Endpoints below carry absolute ``/v1/...`` paths, so normalize the
    configured URL to the service root — a configured ``.../v1`` value
    (e.g. the public ``/c/v1`` mount) must not double the version prefix.

    #2246: credentials resolve explicit ``--api-key`` > stored ``auth
    login`` credential > ``config.api_key`` via ``auth_client_kwargs``.
    """
    config = get_config()
    url = config.coordinator_api_url or os.getenv("COORDINATOR_API_URL", "")
    if not url:
        return None
    return AITBCHTTPClient(
        base_url=service_root_url(url), timeout=config.timeout, **auth_client_kwargs(explicit_key, config.api_key)
    )


@click.group(
    epilog="""Examples:

  aitbc economics market

  aitbc economics propose --parameter tx_fee --current 0.001 --proposed 0.0005"""
)
def economics():
    """Economic intelligence, modeling, market analysis, and OpenClaw DAO proposals."""
    pass


@economics.command(
    epilog="""Examples:

  aitbc economics distributed

  aitbc economics distributed --cost-optimize"""
)
@click.option("--cost-optimize", is_flag=True, help="Enable cost optimization")
@click.pass_context
def distributed(ctx, cost_optimize):
    """Run distributed cost optimization for the AITBC economy."""
    try:
        result = {"action": "distributed_optimization", "cost_optimize": cost_optimize, "status": "simulated"}
        output(result, ctx.obj.get("output_format", "table"), title="Distributed Economics")
    except _OPS_ERRORS as e:
        abort(ctx, f"Error in distributed economics: {e}", from_exception=e)


@economics.command(
    epilog="""Examples:

  aitbc economics model

  aitbc economics model --type cost-optimization"""
)
@click.option("--type", default="cost-optimization", help="Model type")
@click.pass_context
def model(ctx, type):
    """Run an economic model of the configured type."""
    try:
        result = {"action": "economic_modeling", "model_type": type, "status": "simulated"}
        output(result, ctx.obj.get("output_format", "table"), title="Economic Model")
    except _OPS_ERRORS as e:
        abort(ctx, f"Error in economic modeling: {e}", from_exception=e)


@economics.command(
    epilog="""Examples:

  aitbc economics market

  aitbc economics market --output json"""
)
@click.pass_context
def market(ctx):
    """Run market analysis for the AITBC ecosystem."""
    try:
        result = {"action": "market_analysis", "status": "simulated"}
        output(result, ctx.obj.get("output_format", "table"), title="Market Economics")
    except _OPS_ERRORS as e:
        abort(ctx, f"Error in market analysis: {e}", from_exception=e)


@economics.command(
    epilog="""Examples:

  aitbc economics propose --parameter tx_fee --current 0.001 --proposed 0.0005

  aitbc economics propose --parameter block_reward --current 10 --proposed 12 --unit AIT"""
)
@click.option("--parameter", required=True, help="Economic parameter name")
@click.option("--current", required=True, help="Current parameter value")
@click.option("--proposed", required=True, help="Proposed parameter value")
@click.option("--unit", default="", help="Parameter unit")
@click.option("--proposer-id", default="cli-user", help="Proposer identifier")
@click.pass_context
def propose(ctx, parameter, current, proposed, unit, proposer_id):
    """Submit an OpenClaw DAO economic parameter proposal."""
    client = _api_client(ctx.obj.get("api_key") if ctx.obj else None)
    try:
        if client is None:
            result = {
                "action": "economic_proposal",
                "parameter": parameter,
                "current_value": current,
                "proposed_value": proposed,
                "unit": unit,
                "status": "simulated",
            }
        else:
            result = client.post(
                "/v1/economic-proposals",
                json={
                    "proposer_id": proposer_id,
                    "parameter_name": parameter,
                    "current_value": current,
                    "proposed_value": proposed,
                    "unit": unit,
                },
            )
        output(result, ctx.obj.get("output_format", "table"), title="Economic Proposal")
    except NetworkError as e:
        abort(ctx, f"Coordinator API error: {e}", from_exception=e)
    except _OPS_ERRORS as e:
        abort(ctx, f"Error submitting economic proposal: {e}", from_exception=e)


@economics.command(
    epilog="""Examples:

  aitbc economics vote --proposal-id prop-123 --vote for

  aitbc economics vote --proposal-id prop-123 --vote against --voting-power 10"""
)
@click.option("--proposal-id", "proposal_id", required=True, help="The Proposal-id.")
@click.option("--vote", type=click.Choice(["for", "against", "abstain"]), required=True, help="Vote choice")
@click.option("--voting-power", default=1.0, help="Voting power to apply")
@click.pass_context
def vote(ctx, proposal_id, vote, voting_power):
    """Vote for, against, or abstain on an OpenClaw DAO economic parameter proposal."""
    client = _api_client(ctx.obj.get("api_key") if ctx.obj else None)
    try:
        if client is None:
            result = {"action": "economic_vote", "proposal_id": proposal_id, "vote": vote, "status": "simulated"}
        else:
            result = client.post(
                f"/v1/economic-proposals/{proposal_id}/votes",
                json={"vote": vote, "voting_power": voting_power},
            )
        output(result, ctx.obj.get("output_format", "table"), title="Economic Vote")
    except NetworkError as e:
        abort(ctx, f"Coordinator API error: {e}", from_exception=e)
    except _OPS_ERRORS as e:
        abort(ctx, f"Error voting on proposal {proposal_id}: {e}", from_exception=e)


@economics.command(
    epilog="""Examples:

  aitbc economics status --proposal-id prop-123

  aitbc economics status --proposal-id prop-123 --output json"""
)
@click.option("--proposal-id", "proposal_id", required=True, help="The Proposal-id.")
@click.pass_context
def status(ctx, proposal_id):
    """Show the status of an OpenClaw DAO economic parameter proposal by proposal ID."""
    client = _api_client(ctx.obj.get("api_key") if ctx.obj else None)
    try:
        if client is None:
            result = {
                "action": "economic_status",
                "proposal_id": proposal_id,
                "status": "draft",
                "votes_for": 0,
                "votes_against": 0,
                "votes_abstain": 0,
            }
        else:
            result = client.get(f"/v1/economic-proposals/{proposal_id}")
        output(result, ctx.obj.get("output_format", "table"), title="Economic Proposal Status")
    except NetworkError as e:
        abort(ctx, f"Coordinator API error: {e}", from_exception=e)
    except _OPS_ERRORS as e:
        abort(ctx, f"Error fetching proposal {proposal_id}: {e}", from_exception=e)
