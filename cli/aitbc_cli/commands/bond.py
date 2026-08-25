"""Performance bond commands for providers and agents."""

from __future__ import annotations

import os
from typing import Any

import click

from ..config import get_config
from ..utils import output
from ..auth import AuthManager
from ..utils.error_handling import abort
from ..utils.http_client import AITBCHTTPClient, NetworkError


def _looks_like_jwt(token: str) -> bool:
    """A JWT is three base64url segments separated by dots."""
    return token.startswith("ey") and token.count(".") == 2


def _coordinator_base_url(ctx, coordinator_url: str | None = None) -> str:
    """Return the coordinator base URL without a trailing /v1 path."""
    config = get_config()
    url = coordinator_url or ctx.obj.get("url") or config.coordinator_api_url or os.getenv("COORDINATOR_API_URL", "")
    if not url:
        return ""
    url = url.rstrip("/")
    if url.endswith("/v1"):
        url = url[:-3]
    return url


def _api_client(ctx, coordinator_url: str | None = None, timeout: int | None = None) -> AITBCHTTPClient:
    """Return an HTTP client for the coordinator API."""
    config = get_config()
    url = _coordinator_base_url(ctx, coordinator_url)
    if not url:
        abort(ctx, "Coordinator URL not configured")

    token = ctx.obj.get("api_key") or config.api_key or ""
    if not token:
        token = AuthManager().get_credential("client") or ""

    headers: dict[str, str] | None = None
    client_kwargs: dict[str, Any] = {"base_url": url, "timeout": timeout or config.timeout or 30, "headers": headers}
    if token and _looks_like_jwt(token):
        client_kwargs["headers"] = {"Authorization": f"Bearer {token}"}
    elif token:
        client_kwargs["api_key"] = token

    return AITBCHTTPClient(**client_kwargs)


@click.group()
def bond():
    """Provider performance bond lifecycle commands."""
    pass


@bond.command()
@click.argument("provider-id")
@click.option("--amount", default="0.0", help="Amount to lock as a performance bond")
@click.option("--required-amount", default="0.0", help="Required bond amount for this provider")
@click.option("--bond-id", default=None, help="Optional on-chain/external bond identifier")
@click.option("--coordinator-url", help="Coordinator URL")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def create(ctx, provider_id, amount, required_amount, bond_id, coordinator_url, format):
    """Create or top-up a provider's performance bond."""
    try:
        client = _api_client(ctx, coordinator_url)
        payload: dict[str, Any] = {
            "amount": amount,
            "required_amount": required_amount,
        }
        if bond_id:
            payload["bond_id"] = bond_id
        result = client.post(f"/v1/marketplace/providers/{provider_id}/bonds", json=payload)
        output(result, ctx.obj.get("output_format", format), title="Bond Created")
    except NetworkError as e:
        abort(ctx, f"Coordinator API error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error creating bond for {provider_id}: {e}", from_exception=e)


@bond.command()
@click.argument("provider-id")
@click.option("--coordinator-url", help="Coordinator URL")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def status(ctx, provider_id, coordinator_url, format):
    """Show a provider's bond eligibility status."""
    try:
        client = _api_client(ctx, coordinator_url)
        result = client.get(f"/v1/marketplace/providers/{provider_id}/eligibility")
        output(result, ctx.obj.get("output_format", format), title="Bond Status")
    except NetworkError as e:
        abort(ctx, f"Coordinator API error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error fetching bond status for {provider_id}: {e}", from_exception=e)


@bond.command()
@click.argument("provider-id")
@click.option("--amount", default="0.0", help="Amount to add to the bond")
@click.option("--bond-id", default=None, help="Optional on-chain/external bond identifier")
@click.option("--coordinator-url", help="Coordinator URL")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def top_up(ctx, provider_id, amount, bond_id, coordinator_url, format):
    """Top up a provider's performance bond."""
    try:
        client = _api_client(ctx, coordinator_url)
        payload: dict[str, Any] = {"amount": amount}
        if bond_id:
            payload["bond_id"] = bond_id
        result = client.post(f"/v1/marketplace/providers/{provider_id}/bonds", json=payload)
        output(result, ctx.obj.get("output_format", format), title="Bond Top-Up")
    except NetworkError as e:
        abort(ctx, f"Coordinator API error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error topping up bond for {provider_id}: {e}", from_exception=e)


@bond.command()
@click.argument("provider-id")
@click.option("--coordinator-url", help="Coordinator URL")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def lock(ctx, provider_id, coordinator_url, format):
    """Lock a provider's bond while a high-value job is in flight."""
    try:
        client = _api_client(ctx, coordinator_url)
        result = client.post(f"/v1/marketplace/providers/{provider_id}/bonds/lock")
        output(result, ctx.obj.get("output_format", format), title="Bond Locked")
    except NetworkError as e:
        abort(ctx, f"Coordinator API error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error locking bond for {provider_id}: {e}", from_exception=e)


@bond.command()
@click.argument("provider-id")
@click.option("--coordinator-url", help="Coordinator URL")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def release(ctx, provider_id, coordinator_url, format):
    """Release a locked provider bond."""
    try:
        client = _api_client(ctx, coordinator_url)
        result = client.post(f"/v1/marketplace/providers/{provider_id}/bonds/release")
        output(result, ctx.obj.get("output_format", format), title="Bond Released")
    except NetworkError as e:
        abort(ctx, f"Coordinator API error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error releasing bond for {provider_id}: {e}", from_exception=e)


@bond.command()
@click.argument("provider-id")
@click.option("--reason", default="", help="Reason for the slash")
@click.option("--coordinator-url", help="Coordinator URL")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def slash(ctx, provider_id, reason, coordinator_url, format):
    """Slash a provider's bond."""
    try:
        client = _api_client(ctx, coordinator_url)
        payload = {"reason": reason} if reason else {}
        result = client.post(f"/v1/marketplace/providers/{provider_id}/bonds/slash", json=payload)
        output(result, ctx.obj.get("output_format", format), title="Bond Slashed")
    except NetworkError as e:
        abort(ctx, f"Coordinator API error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error slashing bond for {provider_id}: {e}", from_exception=e)


@bond.command()
@click.argument("bond-id")
@click.option("--reason", default="", help="Reason for the appeal")
@click.option("--evidence", default="", help="Evidence URL or CID")
@click.option("--coordinator-url", help="Coordinator URL")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def appeal(ctx, bond_id, reason, evidence, coordinator_url, format):
    """Appeal a slashing decision for a bond."""
    try:
        client = _api_client(ctx, coordinator_url)
        result = client.post(
            "/v1/governance/slash-appeals",
            json={"bond_id": bond_id, "reason": reason, "evidence": [evidence] if evidence else []},
        )
        output(result, ctx.obj.get("output_format", format), title="Slash Appeal")
    except NetworkError as e:
        abort(ctx, f"Coordinator API error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error submitting slash appeal for {bond_id}: {e}", from_exception=e)
