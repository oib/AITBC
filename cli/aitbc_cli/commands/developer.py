"""Developer registry CLI commands."""

from __future__ import annotations

import os

import click
import httpx

from aitbc.exceptions import AITBCError
from ..config import get_config
from ..utils import output, resolve_output_format
from ..utils.http_client import AITBCHTTPClient, NetworkError, auth_client_kwargs, service_root_url
from ..utils.error_handling import CLIError, abort

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

COORDINATOR_API_URL = "http://localhost:8203"


def _get_client(ctx: click.Context | None = None, url: str | None = None) -> AITBCHTTPClient:
    """Create an authenticated HTTP client for the configured coordinator API."""
    config = get_config()
    ctx_obj = ctx.obj if ctx is not None and isinstance(ctx.obj, dict) else {}
    base_url: str = service_root_url(
        url or ctx_obj.get("url") or os.getenv("COORDINATOR_API_URL") or config.coordinator_api_url,
        COORDINATOR_API_URL,
    )
    return AITBCHTTPClient(
        base_url=base_url,
        timeout=30,
        **auth_client_kwargs(ctx_obj.get("api_key"), config.api_key),
    )


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
@click.option("--format", type=click.Choice(["table", "json"]), default=None, help="Output format")
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
        client = _get_client(ctx)
        payload = {
            "wallet_address": wallet_address,
            "name": name,
            "email": email,
            "github_handle": github_handle,
        }
        result = client.post("/v1/developers", json={k: v for k, v in payload.items() if v is not None})
        output(result, resolve_output_format(ctx, format))
    except NetworkError as e:
        abort(None, f"Network error: {e}")
    except _OPS_ERRORS as e:
        abort(None, f"Error registering developer: {e}")


@developer.command(
    "list",
    epilog="""Examples:

  aitbc developer list

  aitbc developer list --active-only --limit 50 --offset 0""",
)
@click.option("--active-only/--all", default=True, help="List only active developers")
@click.option("--limit", type=int, default=100, help="Maximum number of developers")
@click.option("--offset", type=int, default=0, help="Offset for pagination")
@click.option("--format", type=click.Choice(["table", "json"]), default=None, help="Output format")
@click.pass_context
def list_developers(ctx, active_only: bool, limit: int, offset: int, format: str):
    """List registered developers with optional active-only, limit, and offset filters."""
    try:
        client = _get_client(ctx)
        params = {"active_only": active_only, "limit": limit, "offset": offset}
        # GET /v1/developers returns a bare JSON array; get() narrows via
        # expect_object and raises TypeError on non-object bodies (#552).
        result = client.get_json("/v1/developers", params=params)
        output(result, resolve_output_format(ctx, format))
    except NetworkError as e:
        abort(None, f"Network error: {e}")
    except _OPS_ERRORS as e:
        abort(None, f"Error listing developers: {e}")
