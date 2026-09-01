"""
Escrow subgroup and escrow-related helpers
"""

import re
from decimal import Decimal
from typing import Any

import click

from aitbc.utils.units import units_to_ait

from ...auth import AuthManager
from ...config import get_config
from ...utils import error, info, output, success
from ...utils.http_client import AITBCHTTPClient, get_logger

# Initialize logger
logger = get_logger(__name__)


# ---------------------------------------------------------------------------


def escrow_group():
    """Create and return the escrow group"""

    @click.group(
        epilog="""Examples:

  aitbc market escrow status --job-id job-123

  aitbc market escrow create --job-id job-123 --buyer 0x... --provider 0x..."""
    )
    def escrow():
        """Manage on-chain escrow for GPU jobs."""
        pass

    return escrow


escrow = escrow_group()


def _get_rpc_client(config, base_url: str, timeout: int = 10) -> AITBCHTTPClient:
    """Return an HTTP client for blockchain RPC calls, with the API key if configured."""
    return AITBCHTTPClient(
        base_url=base_url,
        timeout=timeout,
        api_key=getattr(config, "blockchain_rpc_api_key", None),
    )


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


def _escrow_create(
    ctx,
    job_id: str,
    buyer: str,
    provider: str,
    amount: Decimal | None,
    config,
    private_key: str | None = None,
    node_wallet: str | None = None,
) -> str | None:
    """Create an on-chain escrow for a paid job.

    If ``private_key`` is provided, the ESCROW_LOCK transaction is signed by
    the buyer and the blockchain RPC can settle it on-chain.  Without it, the
    helper aborts because the chain refuses to lock escrow without a buyer
    signature.

    The chain's smallest unit is the compute-unit (1 AIT = 36_000_000).
    Estimates that round to zero compute-units are rounded up to one compute-unit
    so the lock transaction is valid and the provider can be paid.

    ``node_wallet`` is the hub proposer address that will hold the escrow.
    On follower/customer nodes the local RPC has no proposer, so callers should
    pass the hub's proposer (``HUB_PROPOSER_ID`` or ``--proposer``).
    """
    from ...utils.escrow import create_signed_escrow_lock

    if not private_key:
        error("Escrow creation requires a buyer-signed transaction. Use --wallet to select a wallet with a private key.")
        raise click.Abort()

    if not amount or amount <= 0:
        error("Escrow amount must be positive")
        raise click.Abort()

    # 1 AIT = 36_000_000 compute-units; 0.0000000277... AIT = 1 compute-unit.
    min_escrow_ait = units_to_ait(1)
    if amount < min_escrow_ait:
        info(f"Rounding escrow up to minimum {min_escrow_ait} AIT (1 compute-unit)")
        amount = min_escrow_ait

    # Follower/customer nodes have no local proposer; use the configured hub proposer.
    if not node_wallet:
        node_wallet = getattr(config, "hub_proposer_id", None) or None
    if not node_wallet:
        # Try local /health discovery (hub/proposer nodes) before giving up.
        from ...utils.escrow import get_node_wallet

        try:
            node_wallet = get_node_wallet(ctx, _get_blockchain_rpc_url(config))
        except Exception:
            pass
    if not node_wallet:
        error("No escrow proposer address available. Set HUB_PROPOSER_ID, or run on a hub/proposer node.")
        raise click.Abort()

    rpc_url = _get_blockchain_rpc_url(config)
    try:
        lock_tx, signature = create_signed_escrow_lock(
            ctx,
            rpc_url,
            job_id,
            buyer,
            provider,
            amount,
            private_key,
            node_wallet=node_wallet,
        )
    except Exception as e:
        error(f"Failed to build escrow lock transaction: {e}")
        raise click.Abort() from e

    try:
        http_client = _get_rpc_client(config, rpc_url, timeout=10)
        result = http_client.post(
            "/rpc/escrow/create",
            json={
                "job_id": job_id,
                "buyer": buyer,
                "provider": provider,
                "amount": str(amount) if amount else "0",
                "lock_tx": {**lock_tx, "signature": signature},
                "lock_signature": signature,
            },
        )
        contract_id = result.get("contract_id") if isinstance(result, dict) else None
        if contract_id:
            success(f"Escrow created: contract_id={contract_id}")
        return contract_id
    except Exception as e:
        error(f"Escrow creation failed: {e}")
        raise click.Abort() from e


@escrow.command(
    name="release",
    epilog="""Examples:

  aitbc market escrow release --job-id job-123""",
)
@click.option("--job-id", "job_id", required=True, help="Coordinator job ID.")
@click.pass_context
def escrow_release(ctx, job_id: str):
    """Release escrow funds to the provider after job completion."""
    try:
        config = get_config()
        rpc_url = _get_blockchain_rpc_url(config)
        hub_url = f"http://{config.hub_discovery_url or 'hub.aitbc.bubuit.net'}"
        result = None
        try:
            http_client = _get_rpc_client(config, rpc_url, timeout=10)
            result = http_client.post(f"/rpc/escrow/{job_id}/release", json={})
        except Exception:
            logger.debug("Escrow request failed", exc_info=True)
            pass
        if not result:
            try:
                http_client = _get_rpc_client(config, hub_url, timeout=10)
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


def refund_escrow(ctx: click.Context, job_id: str, reason: str) -> dict[str, Any] | None:
    """Refund escrow back to the buyer (coordinator first, then blockchain fallback)."""
    try:
        config = get_config()
        coordinator_result = _coordinator_refund(ctx, job_id, reason)
        if coordinator_result:
            success(f"Coordinator refund accepted for job {job_id}")
            output(coordinator_result, ctx.obj.get("output_format", "table"))
            return coordinator_result
        rpc_url = _get_blockchain_rpc_url(config)
        hub_url = f"http://{config.hub_discovery_url or 'hub.aitbc.bubuit.net'}"
        result = None
        try:
            http_client = _get_rpc_client(config, rpc_url, timeout=10)
            result = http_client.post(f"/rpc/escrow/{job_id}/refund", json={"reason": reason})
        except Exception:
            logger.debug("Escrow request failed", exc_info=True)
            pass
        if not result:
            try:
                http_client = _get_rpc_client(config, hub_url, timeout=10)
                result = http_client.post(f"/rpc/escrow/{job_id}/refund", json={"reason": reason})
            except Exception:
                logger.debug("Escrow request failed", exc_info=True)
                pass
        if result:
            success(f"Escrow refunded for job {job_id}")
            output(result, ctx.obj.get("output_format", "table"))
            return result
        return None
    except Exception as e:
        error(f"Error refunding escrow: {e}")
        raise click.Abort() from e


@escrow.command(
    name="refund",
    epilog="""Examples:

  aitbc market escrow refund --job-id job-123

  aitbc market escrow refund --job-id job-123 --reason 'job_failed'""",
)
@click.option("--job-id", "job_id", required=True, help="Coordinator job ID.")
@click.option("--reason", default="buyer_requested", help="Reason for refund")
@click.pass_context
def escrow_refund(ctx, job_id: str, reason: str):
    """Refund escrow back to the buyer."""
    refund_escrow(ctx, job_id, reason)


@escrow.command(
    name="status",
    epilog="""Examples:

  aitbc market escrow status --job-id job-123

  aitbc market escrow status --job-id job-123 --output json""",
)
@click.option("--job-id", "job_id", required=True, help="Coordinator job ID.")
@click.pass_context
def escrow_status(ctx, job_id: str):
    """Check the on-chain escrow state for a job."""
    try:
        config = get_config()
        rpc_url = _get_blockchain_rpc_url(config)
        hub_url = f"http://{config.hub_discovery_url or 'hub.aitbc.bubuit.net'}"
        result = None
        try:
            http_client = _get_rpc_client(config, rpc_url, timeout=10)
            result = http_client.get(f"/rpc/escrow/{job_id}")
        except Exception:
            logger.debug("Escrow request failed", exc_info=True)
            pass
        if not result:
            try:
                http_client = _get_rpc_client(config, hub_url, timeout=10)
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


@escrow.command(
    name="create",
    epilog="""Examples:

  aitbc market escrow create --job-id job-123 --buyer 0x... --provider 0x...

  aitbc market escrow create --job-id job-123 --buyer 0x... --provider 0x... --amount 100""",
)
@click.option("--job-id", "job_id", required=True, help="Coordinator job ID.")
@click.option("--buyer", "buyer", required=True, help="The Buyer.")
@click.option("--provider", "provider", required=True, help="The Provider.")
@click.option("--amount", "amount", required=False, help="Amount of AIT.")
@click.option("--wallet", "wallet_name", help="Wallet name to sign the escrow lock")
@click.option("--password", help="Wallet password")
@click.pass_context
def escrow_create_cmd(ctx, job_id, buyer, provider, amount, wallet_name, password):
    """Create an on-chain escrow for a job with buyer, provider, and optional amount."""
    try:
        from decimal import Decimal as _Decimal
        from ...utils.money import wallet_amount
        from ...utils.wallet_loader import load_wallet_for_payment

        config = get_config()
        amt = _Decimal(wallet_amount(amount)) if amount is not None else None
        _, private_key, _ = load_wallet_for_payment(ctx, wallet_name=wallet_name, password=password)
        contract_id = _escrow_create(ctx, job_id, buyer, provider, amt, config, private_key=private_key)
        output(
            {"contract_id": contract_id, "job_id": job_id, "buyer": buyer, "provider": provider},
            ctx.obj.get("output_format", "table"),
        )
    except Exception as e:
        error(f"Error creating escrow: {e}")
