"""Developer registry CLI commands."""

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

  aitbc developer register --wallet-address 0x...

  aitbc developer list"""
)
def developer():
    """Register and list developers in the DAO grant registry."""
    pass


@developer.command(
    epilog="""Examples:

  aitbc developer register --wallet-address 0x...

  aitbc developer register --wallet-address 0x... --name Alice --github-handle alice"""
)
@click.option("--wallet-address", required=True, help="Developer wallet address")
@click.option("--name", default=None, help="Developer name")
@click.option("--email", default=None, help="Developer email")
@click.option("--github-handle", default=None, help="GitHub handle")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def register(
    ctx,
    wallet_address: str,
    name: str | None,
    email: str | None,
    github_handle: str | None,
    format: str,
):
    """Register a developer in the DAO grant registry with optional name, email, and GitHub handle."""
    try:
        client = _get_client()
        payload = {
            "wallet_address": wallet_address,
            "name": name,
            "email": email,
            "github_handle": github_handle,
        }
        result = client.post("/v1/developers", json={k: v for k, v in payload.items() if v is not None})
        output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error registering developer: {e}")


@developer.command(
    "list",
    epilog="""Examples:

  aitbc developer list

  aitbc developer list --active-only --limit 50 --offset 0""",
)
@click.option("--active-only/--all", default=True, help="List only active developers")
@click.option("--limit", type=int, default=100, help="Maximum number of developers")
@click.option("--offset", type=int, default=0, help="Offset for pagination")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def list_developers(ctx, active_only: bool, limit: int, offset: int, format: str):
    """List registered developers with optional active-only, limit, and offset filters."""
    try:
        client = _get_client()
        params = {"active_only": active_only, "limit": limit, "offset": offset}
        result = client.get("/v1/developers", params=params)
        output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error listing developers: {e}")
