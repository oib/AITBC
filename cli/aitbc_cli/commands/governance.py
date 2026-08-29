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

from ..config import get_config
from ..utils import error, output
from ..utils.http_client import AITBCHTTPClient, NetworkError

GOVERNANCE_SERVICE_URL = "http://localhost:8105"


def _get_client(ctx: click.Context | None = None, url: str | None = None) -> AITBCHTTPClient:
    """Create an HTTP client for the governance service."""
    import os

    base_url: str = url or os.getenv("GOVERNANCE_SERVICE_URL") or GOVERNANCE_SERVICE_URL
    if ctx is not None and not url:
        config = ctx.obj.get("config") or get_config()
        if getattr(config, "governance_service_url", ""):
            base_url = config.governance_service_url
    return AITBCHTTPClient(base_url=base_url, timeout=30)


@click.group(
    epilog="""Examples:

  aitbc governance propose --title 'Increase block reward' --description '...'

  aitbc governance list"""
)
def governance():
    """Create, vote, execute, and inspect OpenClaw DAO governance proposals."""
    pass


@governance.command(
    epilog="""Examples:

  aitbc governance propose --title 'Increase block reward' --description 'Raise reward to 12 AIT'

  aitbc governance propose --title 'Update fee' --description 'Lower tx fee' --category economics"""
)
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
    """Create a new governance proposal with title, description, and optional category."""
    from datetime import UTC, datetime, timedelta

    try:
        proposal_value = {}
        if params:
            proposal_value = json.loads(params)

        voting_starts = datetime.now(UTC).isoformat()
        voting_ends = (datetime.now(UTC) + timedelta(days=voting_days)).isoformat()

        client = _get_client(ctx)
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


@governance.command(
    epilog="""Examples:

  aitbc governance vote --proposal-id prop-123 --vote for

  aitbc governance vote --proposal-id prop-123 --vote against --voting-power 100"""
)
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
    """Vote for, against, or abstain on a governance proposal."""
    try:
        client = _get_client(ctx)
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


@governance.command(
    epilog="""Examples:

  aitbc governance list

  aitbc governance list --status active --category economics"""
)
@click.option("--status", default=None, help="Filter by status (draft, active, succeeded, defeated, executed, cancelled)")
@click.option("--category", default=None, help="Filter by category")
@click.option("--proposer-id", default=None, help="Filter by proposer ID")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def list(ctx, status: str | None, category: str | None, proposer_id: str | None, format: str):
    """List governance proposals with optional status, category, and proposer filters."""
    try:
        client = _get_client(ctx)
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


@governance.command(
    epilog="""Examples:

  aitbc governance execute --proposal-id prop-123

  aitbc governance execute --proposal-id prop-123 --executor-address 0x..."""
)
@click.option("--proposal-id", "proposal_id", required=True, help="The Proposal id.")
@click.option("--executor-address", default="", help="Executor wallet address (for on-chain execution)")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def execute(ctx, proposal_id: str, executor_address: str, format: str):
    """Execute an approved governance proposal on-chain."""
    try:
        client = _get_client(ctx)
        query = ""
        if executor_address:
            query = f"?executor_address={executor_address}"
        result = client.post(f"/v1/governance/proposals/{proposal_id}/execute{query}")
        output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error executing proposal: {e}")


@governance.command(
    epilog="""Examples:

  aitbc governance close --proposal-id prop-123

  aitbc governance close --proposal-id prop-123 --output json"""
)
@click.option("--proposal-id", "proposal_id", required=True, help="The Proposal id.")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def close(ctx, proposal_id: str, format: str):
    """Close a governance proposal and tally the final votes."""
    try:
        client = _get_client(ctx)
        result = client.post(f"/v1/governance/proposals/{proposal_id}/close")
        output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error closing proposal: {e}")


@governance.command(
    epilog="""Examples:

  aitbc governance status

  aitbc governance status --output json"""
)
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def status(ctx, format: str):
    """Show the global status of the governance system."""
    try:
        client = _get_client(ctx)
        result = client.get("/v1/governance/status")
        output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error getting governance status: {e}")


@governance.command(
    epilog="""Examples:

  aitbc governance get --proposal-id prop-123

  aitbc governance get --proposal-id prop-123 --output json"""
)
@click.option("--proposal-id", "proposal_id", required=True, help="The Proposal id.")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def get(ctx, proposal_id: str, format: str):
    """Get details of a specific governance proposal."""
    try:
        client = _get_client(ctx)
        result = client.get(f"/v1/governance/proposals/{proposal_id}")
        output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error getting proposal: {e}")


# ============================================================================
# v0.7.4 §B8: Cross-chain governance CLI commands
# ============================================================================


@governance.command(
    epilog="""Examples:

  aitbc governance propagate --proposal-id prop-123 --target-chains ait-side-1,ait-side-2

  aitbc governance propagate --proposal-id prop-123 --target-chains ait-side-1"""
)
@click.option("--proposal-id", "proposal_id", required=True, help="The Proposal id.")
@click.option("--target-chains", required=True, help="Comma-separated list of target chain IDs")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def propagate(ctx, proposal_id: str, target_chains: str, format: str):
    """Propagate a governance proposal to a comma-separated list of target chains."""
    try:
        chains = [c.strip() for c in target_chains.split(",") if c.strip()]
        if not chains:
            error("--target-chains must specify at least one chain ID")
            return
        client = _get_client(ctx)
        result = client.post(
            f"/v1/governance/proposals/{proposal_id}/propagate",
            json={"target_chains": chains},
        )
        output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error propagating proposal: {e}")


@governance.command(
    name="aggregate-votes",
    epilog="""Examples:

  aitbc governance aggregate-votes --proposal-id prop-123

  aitbc governance aggregate-votes --proposal-id prop-123 --output json""",
)
@click.option("--proposal-id", "proposal_id", required=True, help="The Proposal id.")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def aggregate_votes(ctx, proposal_id: str, format: str):
    """Aggregate and tally cross-chain votes for a proposal."""
    try:
        client = _get_client(ctx)
        result = client.post(f"/v1/governance/proposals/{proposal_id}/aggregate-votes")
        output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error aggregating votes: {e}")


@governance.command(
    name="execute-cross-chain",
    epilog="""Examples:

  aitbc governance execute-cross-chain --proposal-id prop-123

  aitbc governance execute-cross-chain --proposal-id prop-123 --output json""",
)
@click.option("--proposal-id", "proposal_id", required=True, help="The Proposal id.")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def execute_cross_chain(ctx, proposal_id: str, format: str):
    """Execute a governance proposal across target chains."""
    try:
        client = _get_client(ctx)
        result = client.post(f"/v1/governance/proposals/{proposal_id}/execute-cross-chain")
        output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error executing cross-chain: {e}")


__all__ = ["governance"]
