"""
Escrow subgroup and escrow-related helpers
"""

import re
from decimal import Decimal
from typing import Any

import click

from ...auth import AuthManager
from ...config import get_config
from ...utils import error, output, success, warning
from ...utils.http_client import AITBCHTTPClient, get_logger

# Initialize logger
logger = get_logger(__name__)


# ---------------------------------------------------------------------------


def escrow_group():
    """Create and return the escrow group"""

    @click.group()
    def escrow():
        """Manage blockchain escrow for GPU jobs"""
        pass

    return escrow


escrow = escrow_group()


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


def _escrow_create(job_id: str, buyer: str, provider: str, amount: Decimal | None, config) -> str | None:
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
                # A string, not float(): the node parses this back with Decimal(str(amount))
                # (escrow_routes.create_escrow), so sending a float threw away digits the
                # receiver then preserved faithfully.
                "amount": str(amount) if amount else "0",
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
            logger.debug("Escrow request failed", exc_info=True)
            pass
        if not result:
            try:
                http_client = AITBCHTTPClient(base_url=hub_url, timeout=10)
                result = http_client.post(f"/rpc/escrow/{job_id}/release", json={})
            except Exception:
                logger.debug("Escrow request failed", exc_info=True)
                pass
        if result:
            success(f"Escrow released for job {job_id}")
            output(result, ctx.obj.get("output_format", "table"))
        else:
            error(f"Failed to release escrow for job {job_id}")
    except Exception as e:
        error(f"Error releasing escrow: {e}")
        raise click.Abort() from e


def _coordinator_base_url(ctx) -> str:
    """Return coordinator base URL with any trailing /v1 stripped."""
    url = ctx.obj.get("url")
    if not url:
        url = get_config().coordinator_api_url or "http://localhost:8203"
    url = url.rstrip("/")
    if url.endswith("/v1"):
        url = url[:-3]
    return url


def _client_token(ctx) -> str | None:
    """Return API key from --api-key, then the stored client credential."""
    token = ctx.obj.get("api_key")
    if not token:
        token = AuthManager().get_credential("client")
    return token


def _coordinator_refund(ctx, job_id: str, reason: str) -> dict[str, Any] | None:
    """Ask the coordinator to refund the payment (which also refunds the on-chain escrow)."""
    token = _client_token(ctx)
    if not token:
        return None
    base_url = _coordinator_base_url(ctx)
    try:
        client = AITBCHTTPClient(base_url=base_url, timeout=30, headers={"Authorization": f"Bearer {token}"})
        job = client.get(f"/v1/jobs/{job_id}")
        payment_id = job.get("payment_id") if isinstance(job, dict) else None
        if not payment_id:
            return None
        return client.post(f"/v1/payments/{payment_id}/refund", json={"job_id": job_id, "reason": reason})
    except Exception:
        logger.debug("Coordinator refund request failed", exc_info=True)
        return None


@escrow.command(name="refund")
@click.argument("job_id")
@click.option("--reason", default="buyer_requested", help="Reason for refund")
@click.pass_context
def escrow_refund(ctx, job_id: str, reason: str):
    """Refund escrow back to the buyer (coordinator first, then blockchain fallback)."""
    try:
        config = get_config()
        coordinator_result = _coordinator_refund(ctx, job_id, reason)
        if coordinator_result:
            success(f"Coordinator refund accepted for job {job_id}")
            output(coordinator_result, ctx.obj.get("output_format", "table"))
            return
        rpc_url = _get_blockchain_rpc_url(config)
        hub_url = f"http://{config.hub_discovery_url or 'hub.aitbc.bubuit.net'}"
        result = None
        try:
            http_client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
            result = http_client.post(f"/rpc/escrow/{job_id}/refund", json={"reason": reason})
        except Exception:
            logger.debug("Escrow request failed", exc_info=True)
            pass
        if not result:
            try:
                http_client = AITBCHTTPClient(base_url=hub_url, timeout=10)
                result = http_client.post(f"/rpc/escrow/{job_id}/refund", json={"reason": reason})
            except Exception:
                logger.debug("Escrow request failed", exc_info=True)
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
            logger.debug("Escrow request failed", exc_info=True)
            pass
        if not result:
            try:
                http_client = AITBCHTTPClient(base_url=hub_url, timeout=10)
                result = http_client.get(f"/rpc/escrow/{job_id}")
            except Exception:
                logger.debug("Escrow request failed", exc_info=True)
                pass
        if result:
            output(result, ctx.obj.get("output_format", "table"), title=f"Escrow: {job_id}")
        else:
            error(f"No escrow found for job {job_id}")
    except Exception as e:
        error(f"Error checking escrow status: {e}")
        raise click.Abort() from e


@escrow.command(name="create")
@click.argument("job_id")
@click.argument("buyer")
@click.argument("provider")
@click.argument("amount", required=False)
@click.pass_context
def escrow_create_cmd(ctx, job_id, buyer, provider, amount):
    """Create an on-chain escrow for a job"""
    try:
        from decimal import Decimal as _Decimal
        from ...utils.money import wallet_amount

        config = get_config()
        amt = _Decimal(wallet_amount(amount)) if amount is not None else None
        contract_id = _escrow_create(job_id, buyer, provider, amt, config)
        if contract_id:
            output(
                {"contract_id": contract_id, "job_id": job_id, "buyer": buyer, "provider": provider},
                ctx.obj.get("output_format", "table"),
            )
        else:
            error("Failed to create escrow")
    except Exception as e:
        error(f"Error creating escrow: {e}")
