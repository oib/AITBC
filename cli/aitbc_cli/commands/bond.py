"""Performance bond commands for providers and agents."""

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


@click.group()
def bond():
    """Provider performance bond lifecycle commands."""
    pass


@bond.command()
@click.argument("provider-id")
@click.option("--amount", default="0", help="Amount to add to the bond")
@click.option("--token", default="AITBC", help="Token symbol")
@click.pass_context
def top_up(ctx, provider_id: str, amount: str, token: str):
    """Top up a provider's performance bond."""
    client = _api_client()
    try:
        if client is None:
            result = {
                "provider_id": provider_id,
                "action": "bond_top_up",
                "amount": amount,
                "token": token,
                "status": "simulated",
            }
        else:
            result = client.post(
                f"/v1/marketplace/providers/{provider_id}/bonds/top-up",
                json={"amount": amount, "token": token},
            )
        output(result, ctx.obj.get("output_format", "table"), title="Bond Top-Up")
    except NetworkError as e:
        abort(ctx, f"Coordinator API error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error topping up bond for {provider_id}: {e}", from_exception=e)


@bond.command()
@click.argument("provider-id")
@click.pass_context
def status(ctx, provider_id: str):
    """Show a provider's bond eligibility status."""
    client = _api_client()
    try:
        if client is None:
            result = {
                "provider_id": provider_id,
                "status": "simulated",
                "eligible": True,
                "amount": "0",
                "required": "0",
            }
        else:
            result = client.get(f"/v1/marketplace/providers/{provider_id}/eligibility")
        output(result, ctx.obj.get("output_format", "table"), title="Bond Status")
    except NetworkError as e:
        abort(ctx, f"Coordinator API error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error fetching bond status for {provider_id}: {e}", from_exception=e)


@bond.command()
@click.argument("bond-id")
@click.option("--reason", default="", help="Reason for the appeal")
@click.option("--evidence", default="", help="Evidence URL or CID")
@click.pass_context
def appeal(ctx, bond_id: str, reason: str, evidence: str):
    """Appeal a slashing decision for a bond."""
    client = _api_client()
    try:
        if client is None:
            result = {
                "bond_id": bond_id,
                "action": "slash_appeal",
                "reason": reason,
                "evidence": evidence,
                "status": "simulated",
            }
        else:
            result = client.post(
                "/v1/governance/slash-appeals",
                json={"bond_id": bond_id, "reason": reason, "evidence": [evidence] if evidence else []},
            )
        output(result, ctx.obj.get("output_format", "table"), title="Slash Appeal")
    except NetworkError as e:
        abort(ctx, f"Coordinator API error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error submitting slash appeal for {bond_id}: {e}", from_exception=e)
