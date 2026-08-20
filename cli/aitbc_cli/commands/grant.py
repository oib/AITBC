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


@click.group()
def grant():
    """DAO grant proposal commands."""
    pass


@grant.command()
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
    """Create a new grant proposal."""
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


@grant.command("list")
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
    """List grant proposals."""
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


@grant.command()
@click.argument("grant_id")
@click.option("--vote", type=click.Choice(["for", "against", "abstain"]), required=True, help="Vote choice")
@click.option("--voting-power", type=float, default=0.0, help="Voting power")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def vote(ctx, grant_id: str, vote: str, voting_power: float, format: str):
    """Cast a vote on a grant proposal."""
    try:
        client = _get_client()
        result = client.post(f"/v1/grants/{grant_id}/vote", json={"vote": vote, "voting_power": voting_power})
        output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error voting on grant: {e}")


@grant.command()
@click.argument("grant_id")
@click.option("--milestone-id", default=None, help="Milestone to disburse")
@click.option("--amount", default=None, help="Amount to disburse (decimal string)")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def disburse(ctx, grant_id: str, milestone_id: str | None, amount: str | None, format: str):
    """Disburse funds for a grant or milestone."""
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
