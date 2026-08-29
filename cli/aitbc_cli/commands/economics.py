"""Economics commands for AITBC CLI."""

from __future__ import annotations

import os

import click

from ..config import get_config
from ..utils import output
from ..utils.error_handling import abort
from ..utils.http_client import AITBCHTTPClient, NetworkError


def _api_client() -> AITBCHTTPClient | None:
    """Return a client for the coordinator API if a URL is configured."""
    config = get_config()
    url = config.coordinator_api_url or os.getenv("COORDINATOR_API_URL", "")
    if not url:
        return None
    return AITBCHTTPClient(base_url=url, timeout=config.timeout, api_key=config.api_key or "")


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
    except Exception as e:
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
    except Exception as e:
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
    except Exception as e:
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
    client = _api_client()
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
    except Exception as e:
        abort(ctx, f"Error submitting economic proposal: {e}", from_exception=e)


@economics.command()
@click.argument("proposal-id")
@click.option("--vote", type=click.Choice(["for", "against", "abstain"]), required=True, help="Vote choice")
@click.option("--voting-power", default=1.0, help="Voting power to apply")
@click.pass_context
def vote(ctx, proposal_id, vote, voting_power):
    """Vote on an OpenClaw DAO economic parameter proposal."""
    client = _api_client()
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
    except Exception as e:
        abort(ctx, f"Error voting on proposal {proposal_id}: {e}", from_exception=e)


@economics.command()
@click.argument("proposal-id")
@click.pass_context
def status(ctx, proposal_id):
    """Show the status of an OpenClaw DAO economic parameter proposal."""
    client = _api_client()
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
    except Exception as e:
        abort(ctx, f"Error fetching proposal {proposal_id}: {e}", from_exception=e)
