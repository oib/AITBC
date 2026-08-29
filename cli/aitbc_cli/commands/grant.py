"""Grant proposal CLI commands."""

from __future__ import annotations

import os

import click

from ..utils import error, output
from ..utils.http_client import AITBCHTTPClient, NetworkError

COORDINATOR_API_URL = "http://localhost:8203"


def _get_client(url: str | None = None) -> AITBCHTTPClient:
    """Create an HTTP client for the coordinator API."""
    base_url: str = url or os.getenv("COORDINATOR_API_URL") or COORDINATOR_API_URL
    return AITBCHTTPClient(base_url=base_url, timeout=30)


@click.group(
    epilog="""Examples:

  aitbc grant create --developer-id dev-1 --title 'AI SDK' --requested-amount 1000

  aitbc grant vote --grant-id grant-123 --vote for"""
)
def grant():
    """Create, vote on, and disburse funds from DAO grant proposals."""
    pass


@grant.command(
    epilog="""Examples:

  aitbc grant create --developer-id dev-1 --title 'AI SDK' --requested-amount 1000

  aitbc grant create --developer-id dev-1 --title 'AI SDK' --description 'Improve SDK' --requested-amount 1000 --voting-days 14"""
)
@click.option("--developer-id", required=True, help="Developer ID")
@click.option("--title", required=True, help="Grant title")
@click.option("--description", default="", help="Grant description")
@click.option("--requested-amount", required=True, help="Requested amount as decimal string")
@click.option("--voting-days", type=int, default=7, help="Voting period in days")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def create(
    ctx,
    developer_id: str,
    title: str,
    description: str,
    requested_amount: str,
    voting_days: int,
    format: str,
):
    """Create a new DAO grant proposal."""
    try:
        client = _get_client()
        payload = {
            "developer_id": developer_id,
            "title": title,
            "description": description,
            "requested_amount": requested_amount,
            "voting_days": voting_days,
        }
        result = client.post("/v1/grants", json=payload)
        output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error creating grant: {e}")


@grant.command(
    "list",
    epilog="""Examples:

  aitbc grant list

  aitbc grant list --status active --developer-id dev-1 --limit 50""",
)
@click.option("--status", default=None, help="Filter by status")
@click.option("--developer-id", default=None, help="Filter by developer ID")
@click.option("--limit", type=int, default=100, help="Maximum number of grants")
@click.option("--offset", type=int, default=0, help="Offset for pagination")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def list_grants(
    ctx,
    status: str | None,
    developer_id: str | None,
    limit: int,
    offset: int,
    format: str,
):
    """List DAO grant proposals with optional status, developer, and pagination filters."""
    try:
        client = _get_client()
        params: dict[str, str | int] = {"limit": limit, "offset": offset}
        if status:
            params["status"] = status
        if developer_id:
            params["developer_id"] = developer_id
        result = client.get("/v1/grants", params=params)
        output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error listing grants: {e}")


@grant.command(
    epilog="""Examples:

  aitbc grant vote --grant-id grant-123 --vote for

  aitbc grant vote --grant-id grant-123 --vote for --voting-power 100"""
)
@click.option("--grant-id", "grant_id", required=True, help="The Grant id.")
@click.option("--vote", type=click.Choice(["for", "against", "abstain"]), required=True, help="Vote choice")
@click.option("--voting-power", type=float, default=0.0, help="Voting power")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def vote(ctx, grant_id: str, vote: str, voting_power: float, format: str):
    """Cast a vote for, against, or abstain on a grant proposal."""
    try:
        client = _get_client()
        result = client.post(f"/v1/grants/{grant_id}/vote", json={"vote": vote, "voting_power": voting_power})
        output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error voting on grant: {e}")


@grant.command(
    epilog="""Examples:

  aitbc grant disburse --grant-id grant-123

  aitbc grant disburse --grant-id grant-123 --milestone-id ms-1 --amount 500"""
)
@click.option("--grant-id", "grant_id", required=True, help="The Grant id.")
@click.option("--milestone-id", default=None, help="Milestone to disburse")
@click.option("--amount", default=None, help="Amount to disburse (decimal string)")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def disburse(ctx, grant_id: str, milestone_id: str | None, amount: str | None, format: str):
    """Disburse funds for a grant or a specific milestone."""
    try:
        client = _get_client()
        payload = {"milestone_id": milestone_id, "amount": amount}
        result = client.post(
            f"/v1/grants/{grant_id}/disburse",
            json={k: v for k, v in payload.items() if v is not None},
        )
        output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error disbursing grant: {e}")
