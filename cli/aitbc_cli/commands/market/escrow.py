"""
Escrow subgroup and escrow-related helpers
"""

import re

import click

from ...config import get_config
from ...utils import error, output, success, warning
from ...utils.http_client import AITBCHTTPClient, get_logger

# Initialize logger
logger = get_logger(__name__)

from . import market


# ---------------------------------------------------------------------------


@market.group()
def escrow():
    """Manage blockchain escrow for GPU jobs"""


def _get_blockchain_rpc_url(config) -> str:
    """Return local blockchain RPC base URL (no trailing /rpc — callers add the path)."""
    url = getattr(config, "blockchain_rpc_url", "http://localhost:8202")
    # Normalise to port 8202 if the stored URL points to localhost
    if "localhost" in url or "127.0.0.1" in url:
        url = re.sub(r":\d+", ":8202", url)
    # Strip trailing /rpc so callers that use /rpc/... paths don't double up
    url = url.rstrip("/")
    if url.endswith("/rpc"):
        url = url[:-4]
    return url


def _escrow_create(job_id: str, buyer: str, provider: str, amount, config) -> str | None:
    """Create escrow on local blockchain node. Returns contract_id or None."""
    rpc_url = _get_blockchain_rpc_url(config)
    try:
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
        result = http_client.post(
            "/rpc/escrow/create",
            json={
                "job_id": job_id,
                "buyer": buyer,
                "provider": provider,
                "amount": float(amount) if amount else 0,
            },
        )
        contract_id = result.get("contract_id") if isinstance(result, dict) else None
        if contract_id:
            success(f"Escrow created: contract_id={contract_id}")
        return contract_id
    except Exception as e:
        warning(f"Escrow creation skipped (non-fatal): {e}")
        return None


@escrow.command(name="release")
@click.argument("job_id")
@click.pass_context
def escrow_release(ctx, job_id: str):
    """Release escrow funds to the provider after job completion"""
    try:
        config = get_config()
        rpc_url = _get_blockchain_rpc_url(config)
        hub_url = f"http://{config.hub_discovery_url or 'hub.aitbc.bubuit.net'}"
        result = None
        try:
            http_client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
            result = http_client.post(f"/rpc/escrow/{job_id}/release", json={})
        except Exception:
            pass
        if not result:
            try:
                http_client = AITBCHTTPClient(base_url=hub_url, timeout=10)
                result = http_client.post(f"/rpc/escrow/{job_id}/release", json={})
            except Exception:
                pass
        if result:
            success(f"Escrow released for job {job_id}")
            output(result, ctx.obj.get("output_format", "table"))
        else:
            error(f"Failed to release escrow for job {job_id}")
    except Exception as e:
        error(f"Error releasing escrow: {e}")
        raise click.Abort() from e


@escrow.command(name="refund")
@click.argument("job_id")
@click.option("--reason", default="buyer_requested", help="Reason for refund")
@click.pass_context
def escrow_refund(ctx, job_id: str, reason: str):
    """Refund escrow back to the buyer"""
    try:
        config = get_config()
        rpc_url = _get_blockchain_rpc_url(config)
        hub_url = f"http://{config.hub_discovery_url or 'hub.aitbc.bubuit.net'}"
        result = None
        try:
            http_client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
            result = http_client.post(f"/rpc/escrow/{job_id}/refund", json={"reason": reason})
        except Exception:
            pass
        if not result:
            try:
                http_client = AITBCHTTPClient(base_url=hub_url, timeout=10)
                result = http_client.post(f"/rpc/escrow/{job_id}/refund", json={"reason": reason})
            except Exception:
                pass
        if result:
            success(f"Escrow refunded for job {job_id}")
            output(result, ctx.obj.get("output_format", "table"))
        else:
            error(f"Failed to refund escrow for job {job_id}")
    except Exception as e:
        error(f"Error refunding escrow: {e}")
        raise click.Abort() from e


@escrow.command(name="status")
@click.argument("job_id")
@click.pass_context
def escrow_status(ctx, job_id: str):
    """Check on-chain escrow state for a job"""
    try:
        config = get_config()
        rpc_url = _get_blockchain_rpc_url(config)
        hub_url = f"http://{config.hub_discovery_url or 'hub.aitbc.bubuit.net'}"
        result = None
        try:
            http_client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
            result = http_client.get(f"/rpc/escrow/{job_id}")
        except Exception:
            pass
        if not result:
            try:
                http_client = AITBCHTTPClient(base_url=hub_url, timeout=10)
                result = http_client.get(f"/rpc/escrow/{job_id}")
            except Exception:
                pass
        if result:
            output(result, ctx.obj.get("output_format", "table"), title=f"Escrow: {job_id}")
        else:
            error(f"No escrow found for job {job_id}")
    except Exception as e:
        error(f"Error checking escrow status: {e}")
        raise click.Abort() from e
