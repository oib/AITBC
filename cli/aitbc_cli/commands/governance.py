"""Governance CLI commands (v0.7.3).

Provides commands for on-chain governance operations:
- ``governance propose`` — create a governance proposal
- ``governance vote`` — cast a vote on a proposal
- ``governance list`` — list proposals (with optional status filter)
- ``governance execute`` — execute a passed proposal after timelock
- ``governance status`` — get governance service status
- ``governance get`` — get a specific proposal by ID

These commands talk to the governance service REST API (port 8105)
rather than non-existent blockchain RPC endpoints. The governance
service handles on-chain tx submission when ``enable_onchain_submission``
is enabled in its config.
"""

import json

import click

from ..utils import error, output
from ..utils.http_client import AITBCHTTPClient, NetworkError

GOVERNANCE_SERVICE_URL = "http://localhost:8105"


def _get_client(url: str | None = None) -> AITBCHTTPClient:
    """Create an HTTP client for the governance service."""
    import os

    base_url = url or os.getenv("GOVERNANCE_SERVICE_URL", GOVERNANCE_SERVICE_URL)
    return AITBCHTTPClient(base_url=base_url, timeout=30)


@click.group()
def governance():
    """Governance operations — on-chain proposals, voting, and execution"""
    pass


@governance.command()
@click.option("--title", required=True, help="Proposal title")
@click.option("--description", required=True, help="Proposal description")
@click.option(
    "--type", "proposal_type", default="parameter_change", help="Proposal type (parameter_change, fund_allocation, etc.)"
)
@click.option("--category", default="general", help="Proposal category")
@click.option("--proposer-id", required=True, help="Proposer profile ID")
@click.option("--proposer-address", default="", help="Proposer wallet address (for on-chain submission)")
@click.option("--params", default=None, help="JSON-encoded parameters for parameter_change proposals")
@click.option("--voting-days", type=int, default=7, help="Voting period in days")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def propose(
    ctx,
    title: str,
    description: str,
    proposal_type: str,
    category: str,
    proposer_id: str,
    proposer_address: str,
    params: str | None,
    voting_days: int,
    format: str,
):
    """Create a governance proposal"""
    from datetime import UTC, datetime, timedelta

    try:
        proposal_value = {}
        if params:
            proposal_value = json.loads(params)

        voting_starts = datetime.now(UTC).isoformat()
        voting_ends = (datetime.now(UTC) + timedelta(days=voting_days)).isoformat()

        client = _get_client()
        proposal_data = {
            "title": title,
            "description": description,
            "proposal_type": proposal_type,
            "category": category,
            "proposer_id": proposer_id,
            "proposer_address": proposer_address,
            "proposal_value": proposal_value,
            "voting_starts": voting_starts,
            "voting_ends": voting_ends,
        }
        result = client.post("/v1/governance/proposals", json=proposal_data)
        output(result, ctx.obj.get("output_format", format))
    except json.JSONDecodeError:
        error("Invalid JSON in --params")
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error creating proposal: {e}")


@governance.command()
@click.option("--proposal-id", required=True, help="Proposal ID to vote on")
@click.option("--voter-id", required=True, help="Voter profile ID")
@click.option("--vote", type=click.Choice(["for", "against", "abstain"]), required=True, help="Vote choice")
@click.option("--voter-address", default="", help="Voter wallet address (for on-chain voting power)")
@click.option("--reason", default="", help="Reason for the vote")
@click.option(
    "--voting-power", type=float, default=0.0, help="Voting power (auto-calculated from on-chain balance if enabled)"
)
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def vote(
    ctx,
    proposal_id: str,
    voter_id: str,
    vote: str,
    voter_address: str,
    reason: str,
    voting_power: float,
    format: str,
):
    """Cast a vote on a governance proposal"""
    try:
        client = _get_client()
        vote_data = {
            "proposal_id": proposal_id,
            "voter_id": voter_id,
            "voter_address": voter_address,
            "vote_type": vote,
            "voting_power": voting_power,
            "reason": reason,
        }
        result = client.post("/v1/governance/votes", json=vote_data)
        output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error casting vote: {e}")


@governance.command()
@click.option("--status", default=None, help="Filter by status (draft, active, succeeded, defeated, executed, cancelled)")
@click.option("--category", default=None, help="Filter by category")
@click.option("--proposer-id", default=None, help="Filter by proposer ID")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def list(ctx, status: str | None, category: str | None, proposer_id: str | None, format: str):
    """List governance proposals"""
    try:
        client = _get_client()
        params: dict[str, str] = {}
        if status:
            params["status"] = status
        if category:
            params["category"] = category
        if proposer_id:
            params["proposer_id"] = proposer_id
        result = client.get("/v1/governance/proposals", params=params)
        output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error listing proposals: {e}")


@governance.command()
@click.argument("proposal_id")
@click.option("--executor-address", default="", help="Executor wallet address (for on-chain execution)")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def execute(ctx, proposal_id: str, executor_address: str, format: str):
    """Execute a passed proposal (after timelock expires)"""
    try:
        client = _get_client()
        params: dict[str, str] = {}
        if executor_address:
            params["executor_address"] = executor_address
        result = client.post(f"/v1/governance/proposals/{proposal_id}/execute", json=params)
        output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error executing proposal: {e}")


@governance.command()
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def status(ctx, format: str):
    """Get governance service status and configuration"""
    try:
        client = _get_client()
        result = client.get("/v1/governance/status")
        output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error getting governance status: {e}")


@governance.command()
@click.argument("proposal_id")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def get(ctx, proposal_id: str, format: str):
    """Get a specific governance proposal by ID"""
    try:
        client = _get_client()
        result = client.get(f"/v1/governance/proposals/{proposal_id}")
        output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error getting proposal: {e}")


__all__ = ["governance"]
