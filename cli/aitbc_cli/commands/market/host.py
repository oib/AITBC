"""Market IPFS hosting commands (v0.25.7 first-class IPFS)."""

from __future__ import annotations

import os
import secrets
import time
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import click
import requests

from aitbc.crypto.crypto import sign_transaction_data
from aitbc.exceptions import AITBCError
from aitbc.market.job_request_signature import jobs_request_message

from ...config import get_config
from ...utils import OUTPUT_FORMAT_OPTION, error, info, output, success, warning
from ...utils.address import to_canonical
from ...utils.error_handling import CLIError
from ...utils.http_client import AITBCHTTPClient, NetworkError, get_logger
from ...utils.output import resolve_output_format as _resolve_output_format
from ..ipfs import (
    _api_post,
    _daemon_available,
    _hub_market_client,
    _ipfs_add_file,
    _ipfs_is_pinned,
    _ipfs_object_size,
    _ipfs_pin_cid,
    _ipfs_swarm_connect,
    _ipfs_unpin_cid,
    _is_cid,
)
from ._group import market
from ._signing import signed_job_request_fields
from . import get_chain_id, get_market_wallet
from .escrow import (
    _client_auth_kwargs,
    _coordinator_base_url,
    _escrow_create,
    _get_blockchain_rpc_url,
    _post_escrow_release,
    _post_escrow_rpc,
    _resolve_escrow_node_wallet,
    refund_escrow,
)
from .jobs import _refund_orphaned_escrow, _resolve_offer, _track_coordinator_job

logger = get_logger(__name__)

# Expected failure surface for the host fallbacks below (#1860): aitbc/CLI
# error hierarchies, requests transport, and data-shape builtins.
_MARKET_HOST_ERRORS = (
    AITBCError,
    CLIError,
    OSError,
    ArithmeticError,
    ValueError,
    KeyError,
    TypeError,
    AttributeError,
    RuntimeError,
    requests.RequestException,
)

# refund_escrow signals failure with click.Abort/ClickException on top of the
# operational surface — the orphan-refund swallow must catch those too so a
# failed refund never masks the primary job error (#2340).
_HOST_REFUND_ERRORS = _MARKET_HOST_ERRORS + (click.ClickException,)


def _resolve_ipfs_api(offer: dict[str, Any]) -> str:
    """Return the HTTP API URL of the *buyer's* local IPFS daemon.

    ``offer["endpoint"]`` is the provider's loopback address and is meaningless
    to a remote buyer, so it is intentionally ignored: add/pin calls always go
    to the buyer's own daemon. The island daemon listens on 5002; the removed
    public Kubo used 5001.
    """
    env = os.environ.get("IPFS_API_URL")
    if env:
        return env
    for candidate in ("http://127.0.0.1:5002", "http://127.0.0.1:5001"):
        if _daemon_available(candidate):
            return candidate
    # Nothing reachable locally — return the island default and let the caller
    # surface the connection error.
    return "http://127.0.0.1:5002"


def _market_client() -> AITBCHTTPClient:
    """Return an HTTP client for the hub market service."""
    return _hub_market_client()


def _track_market_job(
    job_data: dict[str, Any],
) -> dict[str, Any] | None:
    """Persist a MarketJob record via the market service."""
    try:
        client = _market_client()
        result = client.post("/v1/market/jobs", json=job_data)
        if result and not result.get("error"):
            info(f"Registered market job: {result.get('job_id')}")
            return result
        warning(f"Market job registration returned: {result}")
    except NetworkError as e:
        warning(f"Could not register market job: {e}")
    return None


def _confirm_market_pin(job_id: str, size: int | None = None) -> dict[str, Any] | None:
    """Confirm a job has been pinned."""
    try:
        client = _market_client()
        return client.post(
            f"/v1/market/jobs/{job_id}/pin-confirm",
            json={"size": size},
        )
    except NetworkError as e:
        warning(f"Could not confirm market pin: {e}")
        return None


def _release_market_payment(
    ctx: click.Context,
    escrow_job_id: str,
    market_job_id: str | None = None,
) -> dict[str, Any] | None:
    """Release escrow for a completed job via the customer blockchain (hub fallback), then sync the market record.

    ``escrow_job_id`` is the on-chain escrow key — the coordinator job id on
    the durable path (#2340), the ``sw_job_*`` id on the legacy path.
    ``market_job_id`` is the market-service record to sync; defaults to
    ``escrow_job_id`` for legacy callers.
    """
    market_job_id = market_job_id or escrow_job_id
    config = get_config()
    release_result, failures = _post_escrow_release(ctx, config, escrow_job_id, timeout=20)
    if release_result is None:
        warning(f"Escrow release failed ({'; '.join(failures)}) — the escrow stays locked")
    tx_hash = release_result.get("tx_hash") if isinstance(release_result, dict) else None
    payload: dict[str, Any] = {
        "tx_hash": tx_hash,
        "released_amount": release_result.get("released_amount") if release_result else None,
    }
    # #1907: the release route is party-gated (#1893) — sign as a job party
    # when the market wallet key resolves, else the server requires the
    # operator credential.
    payload.update(signed_job_request_fields(ctx, f"/v1/market/jobs/{market_job_id}/release"))
    try:
        client = _market_client()
        return client.post(
            f"/v1/market/jobs/{market_job_id}/release",
            json=payload,
        )
    except NetworkError as e:
        warning(f"Could not sync market release: {e}")
        return None


def _validate_ipfs_offer(offer: dict[str, Any], offer_id_or_plugin_id: str) -> None:
    """Abort unless the offer is a per-day IPFS hosting offer."""
    if offer.get("service_type") != "ipfs":
        error(f"Offer '{offer_id_or_plugin_id}' is not an IPFS hosting offer (service_type={offer.get('service_type')})")
        raise click.Abort()
    if offer.get("price_unit") != "per_day":
        error(f"IPFS offer '{offer_id_or_plugin_id}' uses price_unit '{offer.get('price_unit')}'; expected 'per_day'")
        raise click.Abort()


def _resolve_hosting_content(cid_or_file: str, ipfs_api: str) -> tuple[Path, str | None, int | None]:
    """Resolve --cid-or-file to (file_path, cid, content_size).

    A local file contributes its stat() size now and is uploaded later, after
    the quota checks; a bare CID is validated and sized via the daemon.
    """
    file_path = Path(cid_or_file)
    content_size: int | None = None
    if file_path.exists() and file_path.is_file():
        return file_path, None, file_path.stat().st_size

    cid = cid_or_file.strip()
    if not cid:
        error("CID cannot be empty")
        raise click.Abort()
    if not _is_cid(cid):
        error(f"Input '{cid_or_file}' is not a valid CID and not a local file")
        raise click.Abort()
    content_size = _ipfs_object_size(ipfs_api, cid)
    return file_path, cid, content_size


def _check_disk_quota(
    disk_quota_mb: int | None,
    content_size: int | None,
    used_bytes: int | None = None,
) -> None:
    """Abort when the content would exceed the offer's per-customer disk quota.

    With ``used_bytes=None`` only the per-item check runs (called before the
    wallet is loaded); pass the buyer's current usage to also run the
    cumulative check across their active market jobs.
    """
    if not disk_quota_mb:
        return
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
    if used_bytes is None:
        return
    if used_bytes + item_size > quota_bytes:
        error(
            f"This upload would use {item_size / (1024 * 1024):.2f} MB and exceed "
            f"the {disk_quota_mb} MB per-customer quota for this offer "
            f"(already using {used_bytes / (1024 * 1024):.2f} MB)"
        )
        raise click.Abort()


def _buyer_used_bytes(buyer: str, offer_id: str) -> int:
    """Bytes the buyer already has pinned across active market jobs."""
    try:
        used_bytes_response = _market_client().get(
            "/v1/market/jobs/usage",
            params={"buyer_address": buyer, "offer_id": offer_id},
        )
        return int(used_bytes_response.get("used_bytes", 0)) if used_bytes_response else 0
    except _MARKET_HOST_ERRORS as e:
        logger.warning("Could not query active IPFS usage: %s", e)
        return 0


def _upload_hosting_file(
    file_path: Path,
    cid: str | None,
    content_size: int | None,
    ipfs_api: str,
) -> tuple[str, int | None]:
    """Upload a local file to the buyer's daemon; return (cid, content_size)."""
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
    return cid, content_size


def _release_and_track(
    ctx: click.Context,
    escrow: dict[str, Any],
    market_job_id: str,
    cid: str,
    release_immediately: bool,
    track: bool,
    offer: dict[str, Any],
    buyer: str,
    provider: str,
    total_cost: Decimal,
) -> dict[str, Any] | None:
    """Release escrow when asked and mirror the job to the coordinator when tracking.

    ``escrow`` is the record from :func:`_lock_host_escrow`. On the durable
    path the coordinator job already exists (it carries the payment), so
    ``track`` is a no-op there — a second ``/v1/jobs`` row would duplicate
    the record the sweeper watches.

    Returns the release result (None unless ``release_immediately`` was set).
    """
    release_result: dict[str, Any] | None = None
    if release_immediately:
        release_result = _release_market_payment(ctx, escrow["escrow_job_id"], market_job_id=market_job_id)
        if release_result and not release_result.get("error"):
            success(f"Released {total_cost:.4f} AIT to provider")
        else:
            warning(f"Could not release payment immediately: {release_result}")

    if track and not escrow.get("tracked"):
        _track_coordinator_job(
            ctx,
            market_job_id,
            offer,
            buyer,
            provider,
            total_cost,
            "ipfs",
            result_hash=cid,
        )
    return release_result


def _pin_hosting_cid(ipfs_api: str, cid: str) -> tuple[bool, bool]:
    """Pin ``cid`` for hosting; return ``(pinned, pin_created)``.

    ``pin_created`` is True only when this call added the pin — abort
    cleanup must never remove a pre-existing pin on the same CID
    (IPFS-PIN-LEAK-1, #1687).
    """
    was_pinned = _ipfs_is_pinned(ipfs_api, cid)
    pinned = _ipfs_pin_cid(ipfs_api, cid)
    return pinned, bool(pinned and not was_pinned)


def _coordinator_payment_client(ctx: click.Context) -> AITBCHTTPClient | None:
    """Coordinator client for the durable host-escrow path (#2340).

    Returns ``None`` when no client credential exists — the caller then
    falls back to the legacy direct lock, which leaves no ``job_payments``
    row for StuckEscrowSweeper.
    """
    if ctx is None or not getattr(ctx, "obj", None):
        return None
    auth_kwargs = _client_auth_kwargs(ctx)
    if not auth_kwargs:
        return None
    return AITBCHTTPClient(
        base_url=_coordinator_base_url(ctx),
        timeout=30,
        **auth_kwargs,
        enable_circuit_breaker=False,
    )


def _create_coordinator_host_escrow(
    ctx: click.Context,
    job_id: str,
    buyer: str,
    provider: str,
    total_cost: Decimal,
    config: Any,
    private_key: str | None,
    node_wallet: str | None,
    offer: dict[str, Any],
    days: int,
) -> dict[str, Any] | None:
    """Lock the host escrow through the coordinator payment rail (#2340).

    ``POST /v1/jobs`` (unpriced row) then ``POST /v1/payments`` with a
    locally-signed ESCROW_LOCK — the JobPayment/PaymentEscrow rows put the
    lock inside StuckEscrowSweeper's view and route refunds through
    ``/v1/payments/{id}/refund``. The on-chain escrow is keyed by the
    coordinator job id, not the ``sw_job_*`` market id.

    Returns ``None`` only for failures before any chain write (no client,
    job-create failure, lock-signing failure) — safe for the caller to fall
    back to the legacy path. Once ``/v1/payments`` has been posted the
    outcome is coordinator-owned: a failure aborts rather than risk a
    second lock.
    """
    from ...utils.escrow import create_signed_escrow_lock
    from aitbc.utils.units import units_to_ait

    client = _coordinator_payment_client(ctx)
    if client is None or not private_key:
        return None

    # #2340 respin: the coordinator job's expires_at (= created + ttl_seconds)
    # is what the refund relay and StuckEscrowSweeper gate on — a fixed 24h
    # ttl would mark the job EXPIRED mid-rental and auto-refund the escrow.
    # ttl covers the full rental plus one day of settlement slack so the
    # market settle path wins before the job can expire.
    rental_seconds = days * 86400
    job_data = {
        "payload": {
            "type": "ipfs",
            "model": offer.get("model", ""),
            "source": "market_host",
            "market_job_id": job_id,
            "offer_id": offer.get("offer_id", ""),
            "buyer_address": buyer,
            "provider_address": provider,
            "actual_cost_ait": str(round(total_cost, 6)),
        },
        "constraints": {},
        "ttl_seconds": rental_seconds + 86400,
        "payment_amount": str(total_cost),
        "payment_currency": "AITBC",
        "buyer_address": buyer,
        "provider_address": provider,
    }
    try:
        job_result = client.post("/v1/jobs", json=job_data)
    except _MARKET_HOST_ERRORS as e:
        warning(f"Coordinator job create failed ({type(e).__name__}: {e}) — no escrow locked")
        return None
    coord_job_id = job_result.get("job_id") if isinstance(job_result, dict) else None
    if not coord_job_id:
        warning(f"Coordinator job create returned no job_id: {job_result}")
        return None

    # Same minimum-lock rounding as _escrow_create: below one compute-unit
    # the chain refuses the lock.
    amount = total_cost
    min_escrow_ait = units_to_ait(1)
    if amount < min_escrow_ait:
        amount = min_escrow_ait

    try:
        node_wallet = _resolve_escrow_node_wallet(ctx, config, node_wallet)
        lock_tx, signature = create_signed_escrow_lock(
            ctx,
            _get_blockchain_rpc_url(config),
            coord_job_id,
            buyer,
            provider,
            amount,
            private_key,
            chain_id=get_chain_id(),
            node_wallet=node_wallet,
        )
    except _MARKET_HOST_ERRORS as e:
        warning(f"Escrow lock signing failed before submit ({type(e).__name__}: {e}) — no escrow locked")
        return None

    payment_payload = {
        "job_id": coord_job_id,
        "amount": str(amount),
        "currency": "AITBC",
        "payment_method": "aitbc_token",
        "buyer_address": lock_tx["from"],
        "provider_address": lock_tx["payload"]["provider"],
        "buyer_lock_signature": signature,
        "buyer_lock_nonce": lock_tx["nonce"],
        "buyer_lock_fee": lock_tx["fee"],
        # JobPaymentCreate caps escrow_timeout_seconds at 86400; the rental
        # length is used up to that cap (same scaling as market_gpu_purchase).
        # Multi-day rentals stay covered because the refund relay gates on
        # job.expires_at (the ttl above), not payment.expires_at.
        "escrow_timeout_seconds": min(rental_seconds, 86400),
        "offer_id": offer.get("offer_id", ""),
        "offer_quantity": str(days),
    }
    try:
        payment = client.post("/v1/payments", json=payment_payload)
    except _MARKET_HOST_ERRORS as e:
        error(
            f"Coordinator payment submit failed for job {coord_job_id} ({type(e).__name__}: {e}). "
            "The lock may still have landed — check `aitbc ai jobs --job-id "
            f"{coord_job_id}` / the coordinator payment before retrying; do NOT rerun market host."
        )
        raise click.Abort() from e
    status = payment.get("status") if isinstance(payment, dict) else None
    if status != "escrowed":
        error(
            f"Coordinator escrow for job {coord_job_id} did not reach escrowed state "
            f"(status={status!r}: {payment}). The payment row exists server-side — "
            "StuckEscrowSweeper covers it; do NOT rerun market host."
        )
        raise click.Abort()
    info(f"Coordinator escrow secured: job {coord_job_id} payment {payment.get('payment_id')}")
    return {
        "escrow_job_id": coord_job_id,
        "contract_id": payment.get("escrow_address") or coord_job_id,
        "payment_id": payment.get("payment_id"),
        "tracked": True,
    }


def _lock_host_escrow(
    ctx: click.Context,
    job_id: str,
    buyer: str,
    provider: str,
    total_cost: Decimal,
    config: Any,
    private_key: str | None,
    node_wallet: str | None,
    offer: dict[str, Any],
    days: int,
) -> dict[str, Any]:
    """Lock the host escrow, preferring the coordinator payment rail (#2340).

    The coordinator path writes the JobPayment/PaymentEscrow rows that put
    the lock inside StuckEscrowSweeper's view. When no client credential is
    available it falls back to the legacy direct ``_escrow_create`` — that
    lock has no payment row and no sweeper coverage, so the fallback is
    warned loudly and flagged ``tracked=False``.
    """
    tracked = _create_coordinator_host_escrow(
        ctx, job_id, buyer, provider, total_cost, config, private_key, node_wallet, offer, days
    )
    if tracked is not None:
        return tracked
    warning(
        "Coordinator payment rail unavailable — falling back to a direct escrow lock. "
        "This lock has NO job_payments row: StuckEscrowSweeper cannot see or refund it "
        "(#2340). Run `aitbc auth login` and retry for durable coverage."
    )
    contract_id = _escrow_create(
        ctx,
        job_id,
        buyer,
        provider,
        total_cost,
        config,
        private_key=private_key,
        node_wallet=node_wallet,
    )
    if not contract_id:
        error("Escrow creation failed; aborting IPFS job")
        raise click.Abort()
    return {
        "escrow_job_id": job_id,
        "contract_id": contract_id,
        "payment_id": None,
        "tracked": False,
    }


def _refund_host_escrow(ctx: click.Context, escrow: dict[str, Any], market_job_id: str) -> None:
    """Best-effort refund for a failed host job, durable path first (#2340).

    On the coordinator path the escrow is keyed by the coordinator job id
    and ``refund_escrow`` resolves the payment row server-side; on the
    legacy path it is the ``sw_job_*`` orphan refund.
    """
    if escrow.get("tracked"):
        try:
            refund_escrow(ctx, escrow["escrow_job_id"], reason="job_failed")
        except _HOST_REFUND_ERRORS:
            warning(
                f"Coordinator refund failed for job {escrow['escrow_job_id']} — the escrow stays locked; "
                f"retry manually with `aitbc market escrow refund --job-id {escrow['escrow_job_id']} --reason job_failed`"
            )
        return
    _refund_orphaned_escrow(ctx, market_job_id, escrow.get("contract_id"))


def _register_ipfs_market_job(
    ctx: click.Context,
    job_data: dict[str, Any],
    *,
    ipfs_api: str,
    cid: str,
    pin_created: bool,
    job_id: str,
    escrow: dict[str, Any],
) -> dict[str, Any]:
    """Register the market job, undoing pin+escrow on any failure (#1687).

    An abort after a successful pin used to leave the pin in place AND the
    escrow locked with no market job record for any sweeper to find. On the
    coordinator path (#2340) the refund goes through the payment row, so a
    stranded lock is also visible to StuckEscrowSweeper.
    """
    try:
        market_result = _track_market_job(job_data)
    except Exception:
        if pin_created:
            _ipfs_unpin_cid(ipfs_api, cid)
        _refund_host_escrow(ctx, escrow, job_id)
        raise
    if not market_result:
        if pin_created:
            _ipfs_unpin_cid(ipfs_api, cid)
        _refund_host_escrow(ctx, escrow, job_id)
        error("Failed to register market job; pin and escrow cleaned up (best-effort).")
        raise click.Abort()
    return market_result


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
    _validate_ipfs_offer(offer, offer_id_or_plugin_id)

    price = Decimal(str(offer.get("price", "0")))
    total_cost = price * Decimal(days)
    provider = to_canonical(offer.get("provider_address", ""))
    if not provider:
        error("Offer has no provider_address")
        raise click.Abort()

    ipfs_api = _resolve_ipfs_api(offer)
    public_endpoint = offer.get("public_endpoint") or ""

    # Determine content and size; a local file is uploaded only after the quota checks.
    file_path, cid, content_size = _resolve_hosting_content(cid_or_file, ipfs_api)

    disk_quota_mb = offer.get("disk_quota_mb")
    _check_disk_quota(disk_quota_mb, content_size)

    buyer, private_key, wallet_id = get_market_wallet(ctx, require_private_key=True)

    # Check quota across active market jobs.
    used_bytes = _buyer_used_bytes(buyer, offer.get("offer_id", offer_id_or_plugin_id))
    _check_disk_quota(disk_quota_mb, content_size, used_bytes)

    # Upload file to local Kubo if needed.
    cid, content_size = _upload_hosting_file(file_path, cid, content_size, ipfs_api)

    # Attempt to connect to the provider's public multiaddr so the island can replicate.
    if public_endpoint and not public_endpoint.startswith(("http://", "https://")):
        _ipfs_swarm_connect(ipfs_api, public_endpoint)

    # Pin BEFORE any escrow lock (#2340): the incident shape was lock-then-pin-
    # fail, which stranded the escrow. Pinning first means unreachable content
    # aborts with nothing locked; a later failure still refunds via
    # _refund_host_escrow and unpins only a pin this run created.
    pinned = False
    pin_created = False
    if pin:
        pinned, pin_created = _pin_hosting_cid(ipfs_api, cid)
        if not pinned:
            error(
                f"Failed to pin CID {cid} on {ipfs_api} — aborting before the escrow lock. "
                "The content must be reachable/pinnable on this node's daemon first."
            )
            raise click.Abort()

    job_id = f"sw_job_ipfs_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"

    escrow = _lock_host_escrow(
        ctx,
        job_id,
        buyer,
        provider,
        total_cost,
        get_config(),
        private_key,
        node_wallet,
        offer,
        days,
    )
    escrow_job_id = escrow["escrow_job_id"]
    contract_id = escrow["contract_id"]

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

    market_result = _register_ipfs_market_job(
        ctx,
        job_data,
        ipfs_api=ipfs_api,
        cid=cid,
        pin_created=pin_created,
        job_id=job_id,
        escrow=escrow,
    )

    # Confirm pin so the job transitions to RUNNING.
    _confirm_market_pin(job_id, content_size)

    release_result = _release_and_track(
        ctx, escrow, job_id, cid, release_immediately, track, offer, buyer, provider, total_cost
    )

    output_record = (
        release_result
        if release_immediately and release_result and not release_result.get("error")
        else market_result or job_data
    )
    output_record["cid"] = cid
    output_record["days"] = days
    output_record["escrow_contract_id"] = contract_id
    output_record["escrow_job_id"] = escrow_job_id
    output_record["payment_id"] = escrow.get("payment_id")
    output_record["escrow_tracked"] = bool(escrow.get("tracked"))
    output_record["access_key"] = access_key
    output_record["access_secret"] = access_secret

    success(
        f"Hosted {cid} for {days} day(s); cost {total_cost:.4f} AIT; market job {job_id} "
        f"(escrow job {escrow_job_id} — informational only; escrow commands take the job_id)"
    )
    output(output_record, output_format, title="IPFS Market Job")
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
@click.option("--pin/--no-pin", default=True, help="Pin the CID before locking escrow (unreachable content aborts unpaid)")
@click.option(
    "--proposer-id",
    "proposer_id",
    help="Override the escrow node-wallet address (defaults to the node wallet advertised at /health)",
)
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
    """Host IPFS content through a market offer for a number of days."""
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


def _apply_access_result(ipfs_api: str, result: dict[str, Any] | None, cid: str | None) -> str | None:
    """Take the CID from a market access response and swarm-connect to the provider."""
    if result and not result.get("error"):
        cid = result.get("cid") or cid
        public_endpoint = result.get("public_endpoint") or ""
        if public_endpoint and not public_endpoint.startswith(("http://", "https://")):
            _ipfs_swarm_connect(ipfs_api, public_endpoint)
    return cid


def _resolve_download_cid(
    ipfs_api: str,
    rental_id: str | None,
    access_key: str | None,
    access_secret: str | None,
    cid: str | None,
) -> str | None:
    """Resolve the CID to download from a market rental or access token."""
    if rental_id:
        try:
            result = _market_client().get(f"/v1/market/jobs/{rental_id}/access")
            cid = _apply_access_result(ipfs_api, result, cid)
        except NetworkError as e:
            warning(f"Could not resolve rental {rental_id}: {e}")

    if access_key and access_secret and not cid:
        try:
            # Secret rides the header, not the URL query — keeps it out of
            # market access logs (APIGW-OLLAMA-DEPTH2-1, #1613).
            result = _market_client().get(f"/v1/market/access/{access_key}", headers={"X-Access-Secret": access_secret})
            cid = _apply_access_result(ipfs_api, result, cid)
        except NetworkError as e:
            warning(f"Could not resolve access token: {e}")
    return cid


def _cat_ipfs(ipfs_api: str, cid: str, wait: bool) -> bytes | None:
    """Retrieve CID content from the local daemon, optionally polling until it appears."""
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
        return response.content
    except _MARKET_HOST_ERRORS as e:
        warning(f"Could not retrieve CID {cid}: {e}")
        return None


def _write_download(data: bytes, output_path: str | None) -> str:
    """Write retrieved content to --output-path or a fresh temp file; return the path."""
    if output_path:
        out_path = Path(output_path)
        out_path.write_bytes(data)
        return str(out_path)
    import tempfile

    with tempfile.NamedTemporaryFile(delete=False, mode="wb") as tmp:
        tmp.write(data)
        return tmp.name


@market.command(
    name="download",
    epilog="""Examples:

  aitbc market download --rental-id <job-id>

  aitbc market download --access-key <k> --access-secret <s> --output-path /tmp/data.txt""",
)
@click.option("--rental-id", "rental_id", help="Market job ID for a paid rental")
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
    """Download IPFS content by market job, access token, or free CID."""
    output_format = _resolve_output_format(ctx, output_format)

    # Retrieval always happens on the buyer's local daemon — the recorded
    # ipfs_api may be the provider's loopback address or a stale endpoint.
    ipfs_api = _resolve_ipfs_api({})

    cid = _resolve_download_cid(ipfs_api, rental_id, access_key, access_secret, cid)

    if not cid:
        error("Provide a CID, --rental-id, or --access-key/--access-secret")
        raise click.Abort()

    if not _daemon_available(ipfs_api):
        error(f"No reachable Kubo daemon at {ipfs_api}")
        raise click.Abort()

    data = _cat_ipfs(ipfs_api, cid, wait)

    if data is None and not output_path:
        error(f"CID not retrievable and no filesystem fallback: {cid}")
        raise click.Abort()

    if data is None:
        error(f"Could not retrieve CID {cid}")
        raise click.Abort()

    file_path = _write_download(data, output_path)

    output({"cid": cid, "file_path": file_path, "size": len(data)}, output_format, title="IPFS Download")


@market.command(
    name="cancel",
    epilog="""Examples:

  aitbc market cancel --job-id <job-id> --reason 'buyer_requested'""",
)
@click.option("--job-id", "job_id", required=True, help="Market job ID to cancel")
@click.option("--reason", default="buyer_requested", help="Reason for cancellation")
@OUTPUT_FORMAT_OPTION
@click.pass_context
def cancel(
    ctx: click.Context,
    job_id: str,
    reason: str,
    output_format: str,
):
    """Cancel an active market job and request a refund."""
    output_format = _resolve_output_format(ctx, output_format)
    # #1634: sign the cancel as a job party when the market wallet key is
    # resolvable — the market verifies the proof and rejects foreign
    # signers. #1893: without a key the cancel is rejected (403) — the
    # user-tier API key alone is not a party credential; only the operator
    # key bypasses signing, and the CLI does not hold it.
    payload: dict[str, Any] = {"reason": reason}
    try:
        wallet_address, private_key, _ = get_market_wallet(ctx, require_private_key=False)
        chain_id = get_chain_id()
        if private_key and wallet_address and chain_id:
            issued_at = int(time.time())
            message = jobs_request_message(wallet_address, chain_id, issued_at, f"/v1/market/jobs/{job_id}/cancel")
            payload.update(
                {
                    "signer_address": wallet_address,
                    "chain_id": chain_id,
                    "issued_at": issued_at,
                    "signature": sign_transaction_data(message, private_key),
                }
            )
    except Exception as e:  # noqa: BLE001 - unsigned cancel is rejected server-side (#1893)
        warning(f"Could not sign market cancel request: {e}")
    try:
        result = _market_client().post(f"/v1/market/jobs/{job_id}/cancel", json=payload)
        if result and not result.get("error"):
            success(f"Canceled market job {job_id}")
        else:
            error(f"Could not cancel job {job_id}: {result}")
            raise click.Abort()
    except NetworkError as e:
        error(f"Market cancel request failed: {e}")
        raise click.Abort() from None

    # Attempt an immediate on-chain refund through the customer blockchain and sync state.
    config = get_config()
    refund_result, refund_failures = _post_escrow_rpc(config, f"/rpc/escrow/{job_id}/refund", {"reason": reason}, timeout=20)
    if refund_result is None:
        warning(f"Escrow refund failed locally and on the hub (sweeper will retry): {'; '.join(refund_failures)}")

    tx_hash = (
        (refund_result.get("tx_hash") or refund_result.get("refund_tx_hash")) if isinstance(refund_result, dict) else None
    )
    if not tx_hash:
        warning(f"Escrow refund did not return a tx_hash yet (job canceled; sweeper will retry): {refund_result}")
    else:
        refund_payload: dict[str, Any] = {
            "tx_hash": tx_hash,
            "refunded_amount": refund_result.get("refunded_amount") if refund_result else None,
            "reason": reason,
        }
        # #1907: the refund route is party-gated (#1893) — sign as a job
        # party when the market wallet key resolves.
        refund_payload.update(signed_job_request_fields(ctx, f"/v1/market/jobs/{job_id}/refund"))
        try:
            _market_client().post(
                f"/v1/market/jobs/{job_id}/refund",
                json=refund_payload,
            )
        except NetworkError as e:
            warning(f"Could not sync market refund: {e}")

    # Re-fetch the job to show the latest payment state.
    try:
        final = _market_client().get(f"/v1/market/jobs/{job_id}")
    except NetworkError:
        final = result
    output(final or result, output_format, title="Canceled Market Job")


def _provider_pin_attestation(
    ctx: click.Context,
    job_id: str,
    cid: str,
    size: int | None,
    wallet_address: str,
    private_key: str,
) -> dict[str, Any]:
    """POST the signed ``provider_confirmed`` pin-confirm for ``job_id``.

    The signature binds the route, the wallet, the chain id, a freshness
    timestamp and the ``{"cid", "size"}`` binding — the market verifies it
    against the job's stored CID and reported size (#1922).
    """
    chain_id = get_chain_id()
    issued_at = int(time.time())
    binding = {"cid": cid, "size": size}
    route = f"/v1/market/jobs/{job_id}/pin-confirm"
    message = jobs_request_message(wallet_address, chain_id, issued_at, route, binding=binding)
    signature = sign_transaction_data(message, private_key)
    return _market_client().post(
        route,
        json={
            "size": size,
            "provider_confirmed": True,
            "binding": binding,
            "signer_address": wallet_address,
            "chain_id": chain_id,
            "issued_at": issued_at,
            "signature": signature,
        },
    )


def _register_ipfs_rental_token(
    job: dict[str, Any],
    job_id: str,
    cid: str,
    size: int | None,
    ipfs_api: str,
) -> dict[str, Any] | None:
    """Register the IpfsRentalToken that puts the escrow on the rental rail.

    The token sweeper releases the escrow to the provider at expiry (or
    refunds a flagged/undelivered rental); without it the market job's
    expiry would refund the buyer even after delivery. Settlement fields
    are service-owned — the market derives ``expires_at`` from the job.
    """
    payload = job.get("payload") or {}
    constraints = job.get("constraints") or {}
    token_data = {
        "access_key": payload.get("access_key"),
        "access_secret": payload.get("access_secret"),
        "rental_id": job_id,
        "offer_id": job.get("offer_id"),
        "cid": cid,
        "buyer_address": job.get("buyer_address"),
        "provider_address": job.get("provider_address"),
        "ipfs_api": ipfs_api,
        "public_endpoint": payload.get("public_endpoint"),
        "disk_quota_mb": constraints.get("disk_quota_mb"),
        "size": size,
        "pinned": True,
    }
    if not token_data["access_key"] or not token_data["access_secret"]:
        warning("Job payload carries no access_key/access_secret — rental token not registered")
        return None
    try:
        return _market_client().post("/v1/market/ipfs/rental-token", json=token_data)
    except NetworkError as e:
        warning(f"Could not register IPFS rental token: {e}")
        return None


def _provider_pin_fetch_job(job_id: str) -> dict[str, Any]:
    """GET the market job and enforce the provider-pin preconditions."""
    try:
        job = _market_client().get(f"/v1/market/jobs/{job_id}")
    except NetworkError as e:
        error(f"Could not fetch market job {job_id}: {e}")
        raise click.Abort() from e
    if not isinstance(job, dict) or job.get("error"):
        error(f"Market job not found: {job_id}")
        raise click.Abort()
    if job.get("service_type") != "ipfs":
        error(f"Job {job_id} is not an IPFS rental (service_type={job.get('service_type')})")
        raise click.Abort()
    if job.get("state") not in {"QUEUED", "RUNNING"}:
        error(f"Job {job_id} is {job.get('state')}; only QUEUED/RUNNING rentals can be pinned")
        raise click.Abort()
    return job


def _provider_pin_cid(job: dict[str, Any], job_id: str) -> str:
    cid = (job.get("payload") or {}).get("cid")
    if not cid:
        error(f"Job {job_id} has no CID in its payload")
        raise click.Abort()
    return str(cid)


def _provider_pin_wallet(ctx: click.Context, job: dict[str, Any]) -> tuple[str, str]:
    """Resolve the provider wallet and prove it owns this job's provider_address."""
    provider = to_canonical(job.get("provider_address") or "")
    wallet_address, private_key, _wallet_name = get_market_wallet(ctx, require_private_key=True)
    if not provider or to_canonical(wallet_address) != provider:
        error(
            f"Wallet {wallet_address} is not this job's provider ({provider or 'unset'}) — "
            "run provider-pin with --wallet selecting the provider wallet"
        )
        raise click.Abort()
    return wallet_address, cast(str, private_key)


def _provider_pin_size(ipfs_api: str, cid: str, payload: dict[str, Any]) -> int | None:
    size = _ipfs_object_size(ipfs_api, cid)
    if size is not None:
        return size
    raw = payload.get("size")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


@market.command(
    name="provider-pin",
    epilog="""Examples:

  aitbc market provider-pin --job-id sw_job_ipfs_20261120210000_ab12cd34

Runs on the PROVIDER node: pins the rental CID on the local island daemon
(fetched over the private swarm from the buyer's pin), registers the
rental token that owns escrow settlement, and submits the signed
provider_confirmed pin-confirm that moves the job to RUNNING.""",
)
@click.option("--job-id", "job_id", required=True, help="Market job ID of the IPFS rental to pin and attest")
@OUTPUT_FORMAT_OPTION
@click.pass_context
def provider_pin(
    ctx: click.Context,
    job_id: str,
    output_format: str,
):
    """Provider side of a paid IPFS rental: pin the CID locally and attest delivery."""
    output_format = _resolve_output_format(ctx, output_format)

    job = _provider_pin_fetch_job(job_id)
    cid = _provider_pin_cid(job, job_id)
    wallet_address, private_key = _provider_pin_wallet(ctx, job)

    # The pin runs on the PROVIDER's local daemon — the private-swarm
    # island daemon fetches the CID from the buyer's pin over bitswap.
    ipfs_api = _resolve_ipfs_api({})
    if not _daemon_available(ipfs_api):
        error(f"No reachable IPFS daemon at {ipfs_api} — the provider pin needs the local island daemon")
        raise click.Abort()
    if not _ipfs_pin_cid(ipfs_api, cid):
        error(f"Failed to pin CID {cid} on {ipfs_api} — is the buyer's daemon reachable on the swarm?")
        raise click.Abort()
    success(f"Pinned {cid} on {ipfs_api}")

    size = _provider_pin_size(ipfs_api, cid, job.get("payload") or {})
    token_result = _register_ipfs_rental_token(job, job_id, cid, size, ipfs_api)

    try:
        result = _provider_pin_attestation(ctx, job_id, cid, size, wallet_address, private_key)
    except NetworkError as e:
        error(f"Pin-confirm attestation failed: {e}")
        raise click.Abort() from e
    if isinstance(result, dict) and result.get("error"):
        error(f"Pin-confirm rejected: {result}")
        raise click.Abort()

    success(f"Provider pin attested for job {job_id} (state -> RUNNING); rental token registered")
    record = result if isinstance(result, dict) else {}
    record["cid"] = cid
    record["size"] = size
    record["rental_token"] = token_result
    output(record, output_format, title="Provider Pin")


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
    """List market jobs."""
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
        # GET /v1/market/jobs returns a bare JSON array; get() narrows via
        # expect_object and raises TypeError on non-object bodies.
        result = _market_client().get_json("/v1/market/jobs", params=params)
        output(result, output_format, title="Market Jobs")
    except NetworkError as e:
        error(f"Could not list market jobs: {e}")
        raise click.Abort() from e
