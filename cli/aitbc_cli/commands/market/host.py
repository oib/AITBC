"""Marketplace IPFS hosting commands (v0.25.7 first-class IPFS)."""

from __future__ import annotations

import os
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import click

from ...config import get_config
from ...utils import OUTPUT_FORMAT_OPTION, error, info, output, success, warning
from ...utils.address import to_canonical
from ...utils.http_client import AITBCHTTPClient, NetworkError, get_logger
from ...utils.output import resolve_output_format as _resolve_output_format
from ..ipfs import (
    _api_post,
    _daemon_available,
    _hub_marketplace_client,
    _ipfs_add_file,
    _ipfs_object_size,
    _ipfs_pin_cid,
    _ipfs_swarm_connect,
    _is_cid,
)
from . import get_chain_id, get_market_wallet, market
from .escrow import _escrow_create, _get_blockchain_rpc_url, _get_rpc_client
from .jobs import _resolve_offer, _track_coordinator_job

logger = get_logger(__name__)


def _resolve_ipfs_api(offer: dict[str, Any]) -> str:
    """Return the Kubo HTTP API URL to use for a given IPFS offer."""
    ipfs_api = os.environ.get("IPFS_API_URL") or offer.get("endpoint") or "http://127.0.0.1:5002"
    if not ipfs_api.startswith(("http://", "https://")):
        # The offer may advertise a p2p multiaddr as public_endpoint; the
        # actual pin/add call still goes to a local Kubo HTTP API.
        ipfs_api = "http://127.0.0.1:5002"
    return ipfs_api


def _marketplace_client() -> AITBCHTTPClient:
    """Return an HTTP client for the hub marketplace service."""
    return _hub_marketplace_client()


def _track_marketplace_job(
    job_data: dict[str, Any],
) -> dict[str, Any] | None:
    """Persist a MarketplaceJob record via the marketplace service."""
    try:
        client = _marketplace_client()
        result = client.post("/v1/marketplace/jobs", json=job_data)
        if result and not result.get("error"):
            info(f"Registered marketplace job: {result.get('job_id')}")
            return result
        warning(f"Marketplace job registration returned: {result}")
    except NetworkError as e:
        warning(f"Could not register marketplace job: {e}")
    return None


def _confirm_marketplace_pin(job_id: str, size: int | None = None) -> dict[str, Any] | None:
    """Confirm a job has been pinned."""
    try:
        client = _marketplace_client()
        return client.post(
            f"/v1/marketplace/jobs/{job_id}/pin-confirm",
            json={"size": size},
        )
    except NetworkError as e:
        warning(f"Could not confirm marketplace pin: {e}")
        return None


def _release_marketplace_payment(ctx: click.Context, job_id: str) -> dict[str, Any] | None:
    """Release escrow for a completed job via the customer blockchain, then sync the marketplace record."""
    config = get_config()
    rpc_url = _get_blockchain_rpc_url(config)
    rpc_client = _get_rpc_client(config, rpc_url, timeout=20)
    release_result: dict[str, Any] | None = None
    try:
        release_result = rpc_client.post(f"/rpc/escrow/{job_id}/release", json={})
    except Exception as e:
        warning(f"Local escrow release failed: {e}")
    tx_hash = release_result.get("tx_hash") if isinstance(release_result, dict) else None
    try:
        client = _marketplace_client()
        return client.post(
            f"/v1/marketplace/jobs/{job_id}/release",
            json={"tx_hash": tx_hash, "released_amount": release_result.get("released_amount") if release_result else None},
        )
    except NetworkError as e:
        warning(f"Could not sync marketplace release: {e}")
        return None


def _run_ipfs_hosting(
    ctx: click.Context,
    offer_id_or_plugin_id: str,
    cid_or_file: str,
    days: int,
    pin: bool,
    release_immediately: bool,
    output_format: str,
    track: bool = False,
    node_wallet: str | None = None,
) -> dict[str, Any]:
    """Run an IPFS hosting job and return the job record."""
    offer = _resolve_offer(ctx, offer_id_or_plugin_id)
    if offer.get("service_type") != "ipfs":
        error(f"Offer '{offer_id_or_plugin_id}' is not an IPFS hosting offer (service_type={offer.get('service_type')})")
        raise click.Abort()
    if offer.get("price_unit") != "per_day":
        error(f"IPFS offer '{offer_id_or_plugin_id}' uses price_unit '{offer.get('price_unit')}'; expected 'per_day'")
        raise click.Abort()

    price = Decimal(str(offer.get("price", "0")))
    total_cost = price * Decimal(days)
    provider = to_canonical(offer.get("provider_address", ""))
    if not provider:
        error("Offer has no provider_address")
        raise click.Abort()

    ipfs_api = _resolve_ipfs_api(offer)
    public_endpoint = offer.get("public_endpoint") or ""

    # Determine content and size
    file_path = Path(cid_or_file)
    content_size: int | None = None
    if file_path.exists() and file_path.is_file():
        content_size = file_path.stat().st_size
        cid: str | None = None
    else:
        cid = cid_or_file.strip()
        if not cid:
            error("CID cannot be empty")
            raise click.Abort()
        if not _is_cid(cid):
            error(f"Input '{cid_or_file}' is not a valid CID and not a local file")
            raise click.Abort()
        content_size = _ipfs_object_size(ipfs_api, cid)

    disk_quota_mb = offer.get("disk_quota_mb")
    if disk_quota_mb:
        quota_bytes = int(disk_quota_mb) * 1024 * 1024
        item_size = content_size if content_size is not None else 0
        if item_size > quota_bytes:
            if content_size is None:
                error(f"Could not determine size; offer disk quota is {disk_quota_mb} MB per customer")
            else:
                error(
                    f"Object size {item_size / (1024 * 1024):.2f} MB exceeds "
                    f"the {disk_quota_mb} MB per-customer quota for this offer"
                )
            raise click.Abort()

    buyer, private_key, wallet_id = get_market_wallet(ctx, require_private_key=True)

    # Check quota across active marketplace jobs.
    try:
        used_bytes_response = _marketplace_client().get(
            "/v1/marketplace/jobs/usage",
            params={"buyer_address": buyer, "offer_id": offer.get("offer_id", offer_id_or_plugin_id)},
        )
        used_bytes = int(used_bytes_response.get("used_bytes", 0)) if used_bytes_response else 0
    except Exception as e:
        logger.warning("Could not query active IPFS usage: %s", e)
        used_bytes = 0

    if disk_quota_mb:
        quota_bytes = int(disk_quota_mb) * 1024 * 1024
        item_size = content_size if content_size is not None else 0
        if used_bytes + item_size > quota_bytes:
            error(
                f"This upload would use {item_size / (1024 * 1024):.2f} MB and exceed "
                f"the {disk_quota_mb} MB per-customer quota for this offer "
                f"(already using {used_bytes / (1024 * 1024):.2f} MB)"
            )
            raise click.Abort()

    # Upload file to local Kubo if needed.
    if file_path.exists() and file_path.is_file():
        cid = _ipfs_add_file(ipfs_api, file_path)
        if not cid:
            error(f"Failed to add file to IPFS at {ipfs_api}")
            raise click.Abort()
        daemon_size = _ipfs_object_size(ipfs_api, cid)
        if daemon_size is not None:
            content_size = daemon_size
        success(f"Added file to IPFS: {cid}")

    if not cid:
        error("No CID available for hosting")
        raise click.Abort()

    # Attempt to connect to the provider's public multiaddr so the island can replicate.
    if public_endpoint and not public_endpoint.startswith(("http://", "https://")):
        _ipfs_swarm_connect(ipfs_api, public_endpoint)

    job_id = f"sw_job_ipfs_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"

    contract_id = _escrow_create(
        ctx,
        job_id,
        buyer,
        provider,
        total_cost,
        get_config(),
        private_key=private_key,
        node_wallet=node_wallet,
    )
    if not contract_id:
        error("Escrow creation failed; aborting IPFS job")
        raise click.Abort()

    pinned = False
    if pin:
        pinned = _ipfs_pin_cid(ipfs_api, cid)
        if not pinned:
            # Leave a pending job record so the sweeper can refund later, but tell the user.
            error(f"Failed to pin CID {cid} on {ipfs_api}. Escrow {contract_id} is locked.")
            raise click.Abort()

    if content_size is None:
        content_size = _ipfs_object_size(ipfs_api, cid)

    access_key = secrets.token_urlsafe(16)
    access_secret = secrets.token_urlsafe(32)

    expires_at = (datetime.now(UTC) + timedelta(days=days)).isoformat()

    job_data: dict[str, Any] = {
        "id": job_id,
        "offer_id": offer.get("offer_id", offer_id_or_plugin_id),
        "plugin_id": offer.get("plugin_id", ""),
        "service_type": "ipfs",
        "model": offer.get("model", ""),
        "buyer_address": buyer,
        "provider_address": provider,
        "state": "QUEUED" if not release_immediately else "QUEUED",
        "payload": {
            "cid": cid,
            "file_name": file_path.name if file_path.exists() and file_path.is_file() else None,
            "size": content_size,
            "days": days,
            "pinned": pinned,
            "ipfs_api": ipfs_api,
            "public_endpoint": public_endpoint,
            "access_key": access_key,
            "access_secret": access_secret,
        },
        "constraints": {
            "disk_quota_mb": disk_quota_mb,
        },
        "ttl_seconds": 86400 * 30,
        "expires_at": expires_at,
        "escrow_contract_id": contract_id,
        "payment": {
            "amount": str(total_cost),
            "currency": "AITBC",
            "status": "escrowed",
            "payment_method": "aitbc_token",
            "transaction_hash": None,
            "escrowed_at": datetime.now(UTC).isoformat(),
            "expires_at": expires_at,
            "meta_data": {
                "offer_id": offer.get("offer_id", offer_id_or_plugin_id),
                "offer_unit_price": str(price),
                "offer_price_unit": "per_day",
                "offer_quantity": str(days),
                "wallet_id": wallet_id,
            },
        },
        "payment_status": "escrowed",
        "payment_amount": str(total_cost),
    }

    marketplace_result = _track_marketplace_job(job_data)
    if not marketplace_result:
        error("Failed to register marketplace job; the escrow is locked but no record exists.")
        raise click.Abort()

    # Confirm pin so the job transitions to RUNNING.
    _confirm_marketplace_pin(job_id, content_size)

    if release_immediately:
        release_result = _release_marketplace_payment(ctx, job_id)
        if release_result and not release_result.get("error"):
            success(f"Released {total_cost:.4f} AIT to provider")
        else:
            warning(f"Could not release payment immediately: {release_result}")

    if track:
        _track_coordinator_job(
            ctx,
            job_id,
            offer,
            buyer,
            provider,
            total_cost,
            "ipfs",
            result_hash=cid,
        )

    output_record = release_result if release_immediately and release_result and not release_result.get("error") else marketplace_result or job_data
    output_record["cid"] = cid
    output_record["days"] = days
    output_record["escrow_contract_id"] = contract_id
    output_record["access_key"] = access_key
    output_record["access_secret"] = access_secret

    success(f"Hosted {cid} for {days} day(s); cost {total_cost:.4f} AIT; marketplace job {job_id}; escrow {contract_id}")
    output(output_record, output_format, title="IPFS Marketplace Job")
    return output_record


@market.command(
    name="host",
    epilog="""Examples:

  aitbc market host --offer-id-or-plugin-id ipfs-ipfs-host --cid-or-file Qm... --days 7

  aitbc market host --offer-id-or-plugin-id ipfs-ipfs-host --cid-or-file /tmp/data.txt --days 3""",
)
@click.option("--offer-id-or-plugin-id", "offer_id_or_plugin_id", required=True, help="The Offer id or plugin id.")
@click.option("--cid-or-file", "cid_or_file", required=True, help="The Cid or local file path.")
@click.option("--days", type=int, default=1, help="Rental duration in days")
@click.option("--pin/--no-pin", default=True, help="Pin the CID after paying the rental")
@click.option("--proposer-id", "proposer_id", help="Override hub proposer address for escrow")
@OUTPUT_FORMAT_OPTION
@click.pass_context
def host(
    ctx: click.Context,
    offer_id_or_plugin_id: str,
    cid_or_file: str,
    days: int,
    pin: bool,
    proposer_id: str | None,
    output_format: str,
):
    """Host IPFS content through a marketplace offer for a number of days."""
    output_format = _resolve_output_format(ctx, output_format)
    if days <= 0:
        error("--days must be a positive integer")
        raise click.Abort()

    get_chain_id()
    _run_ipfs_hosting(
        ctx,
        offer_id_or_plugin_id,
        cid_or_file,
        days,
        pin,
        release_immediately=False,
        output_format=output_format,
        track=False,
        node_wallet=proposer_id,
    )


@market.command(
    name="download",
    epilog="""Examples:

  aitbc market download --rental-id <job-id>

  aitbc market download --access-key <k> --access-secret <s> --output-path /tmp/data.txt""",
)
@click.option("--rental-id", "rental_id", help="Marketplace job ID for a paid rental")
@click.option("--access-key", "access_key", help="Rental access key")
@click.option("--access-secret", "access_secret", help="Rental access secret")
@click.option("--cid", "cid", help="Free CID retrieval (bypasses access token)")
@click.option("--output-path", "output_path", type=click.Path(), help="Write retrieved content to this path")
@click.option("--wait", is_flag=True, default=False, help="Wait for the CID to become available on the network")
@OUTPUT_FORMAT_OPTION
@click.pass_context
def download(
    ctx: click.Context,
    rental_id: str | None,
    access_key: str | None,
    access_secret: str | None,
    cid: str | None,
    output_path: str | None,
    wait: bool,
    output_format: str,
):
    """Download IPFS content by marketplace job, access token, or free CID."""
    output_format = _resolve_output_format(ctx, output_format)

    ipfs_api = os.environ.get("IPFS_API_URL") or "http://127.0.0.1:5002"

    if rental_id:
        try:
            result = _marketplace_client().get(f"/v1/marketplace/jobs/{rental_id}/access")
            if result and not result.get("error"):
                cid = result.get("cid") or cid
                ipfs_api = result.get("ipfs_api") or ipfs_api
        except NetworkError as e:
            warning(f"Could not resolve rental {rental_id}: {e}")

    if access_key and access_secret and not cid:
        try:
            result = _marketplace_client().get(f"/v1/marketplace/access/{access_key}", params={"access_secret": access_secret})
            if result and not result.get("error"):
                cid = result.get("cid") or cid
                ipfs_api = result.get("ipfs_api") or ipfs_api
        except NetworkError as e:
            warning(f"Could not resolve access token: {e}")

    if not cid:
        error("Provide a CID, --rental-id, or --access-key/--access-secret")
        raise click.Abort()

    if not _daemon_available(ipfs_api):
        error(f"No reachable Kubo daemon at {ipfs_api}")
        raise click.Abort()

    data: bytes | None = None
    try:
        for _attempt in range(1, 60 if wait else 1):
            response = _api_post("/api/v0/cat", params={"arg": cid}, timeout=30, ipfs_api=ipfs_api)
            if response.status_code == 200:
                break
            if not wait:
                response.raise_for_status()
                break
            import time

            time.sleep(2)
        else:
            response = _api_post("/api/v0/cat", params={"arg": cid}, timeout=30, ipfs_api=ipfs_api)
        response.raise_for_status()
        data = response.content
    except Exception as e:
        warning(f"Could not retrieve CID {cid}: {e}")

    if data is None and not output_path:
        error(f"CID not retrievable and no filesystem fallback: {cid}")
        raise click.Abort()

    if data is None:
        error(f"Could not retrieve CID {cid}")
        raise click.Abort()

    if output_path:
        out_path = Path(output_path)
        out_path.write_bytes(data)
        file_path = str(out_path)
    else:
        import tempfile

        with tempfile.NamedTemporaryFile(delete=False, mode="wb") as tmp:
            tmp.write(data)
            file_path = tmp.name

    output({"cid": cid, "file_path": file_path, "size": len(data)}, output_format, title="IPFS Download")


@market.command(
    name="cancel",
    epilog="""Examples:

  aitbc market cancel --job-id <job-id> --reason 'buyer_requested'""",
)
@click.option("--job-id", "job_id", required=True, help="Marketplace job ID to cancel")
@click.option("--reason", default="buyer_requested", help="Reason for cancellation")
@OUTPUT_FORMAT_OPTION
@click.pass_context
def cancel(
    ctx: click.Context,
    job_id: str,
    reason: str,
    output_format: str,
):
    """Cancel an active marketplace job and request a refund."""
    output_format = _resolve_output_format(ctx, output_format)
    try:
        result = _marketplace_client().post(f"/v1/marketplace/jobs/{job_id}/cancel", json={"reason": reason})
        if result and not result.get("error"):
            success(f"Canceled marketplace job {job_id}")
        else:
            error(f"Could not cancel job {job_id}: {result}")
            raise click.Abort()
    except NetworkError as e:
        error(f"Marketplace cancel request failed: {e}")
        raise click.Abort() from None

    # Attempt an immediate on-chain refund through the customer blockchain and sync state.
    config = get_config()
    rpc_url = _get_blockchain_rpc_url(config)
    rpc_client = _get_rpc_client(config, rpc_url, timeout=20)
    refund_result: dict[str, Any] | None = None
    try:
        refund_result = rpc_client.post(f"/rpc/escrow/{job_id}/refund", json={"reason": reason})
    except Exception as e:
        warning(f"Local escrow refund failed (sweeper will retry): {e}")

    tx_hash = (refund_result.get("tx_hash") or refund_result.get("refund_tx_hash")) if isinstance(refund_result, dict) else None
    if not tx_hash:
        warning(f"Escrow refund did not return a tx_hash yet (job canceled; sweeper will retry): {refund_result}")
    else:
        try:
            _marketplace_client().post(
                f"/v1/marketplace/jobs/{job_id}/refund",
                json={
                    "tx_hash": tx_hash,
                    "refunded_amount": refund_result.get("refunded_amount") if refund_result else None,
                    "reason": reason,
                },
            )
        except NetworkError as e:
            warning(f"Could not sync marketplace refund: {e}")

    # Re-fetch the job to show the latest payment state.
    try:
        final = _marketplace_client().get(f"/v1/marketplace/jobs/{job_id}")
    except NetworkError:
        final = result
    output(final or result, output_format, title="Canceled Marketplace Job")


@market.command(
    name="jobs",
    epilog="""Examples:

  aitbc market jobs --service-type ipfs --state active

  aitbc market jobs --output json""",
)
@click.option("--service-type", "service_type", help="Filter by service type (e.g. ipfs)")
@click.option("--state", "state", help="Filter by job state")
@click.option("--buyer-address", "buyer_address", help="Filter by buyer address")
@click.option("--offer-id", "offer_id", help="Filter by offer ID")
@click.option("--limit", default=100, help="Maximum jobs to return")
@OUTPUT_FORMAT_OPTION
@click.pass_context
def jobs(
    ctx: click.Context,
    service_type: str | None,
    state: str | None,
    buyer_address: str | None,
    offer_id: str | None,
    limit: int,
    output_format: str,
):
    """List marketplace jobs."""
    output_format = _resolve_output_format(ctx, output_format)
    try:
        params: dict[str, Any] = {"limit": limit}
        if service_type:
            params["service_type"] = service_type
        if state:
            params["state"] = state
        if buyer_address:
            params["buyer_address"] = buyer_address
        if offer_id:
            params["offer_id"] = offer_id
        result = _marketplace_client().get("/v1/marketplace/jobs", params=params)
        output(result, output_format, title="Marketplace Jobs")
    except NetworkError as e:
        error(f"Could not list marketplace jobs: {e}")
        raise click.Abort() from e
