"""
Shared module-level helpers and constants for the market service.
Extracted verbatim from the former monolithic market_service module (#1867).
"""

import asyncio
import hashlib
import hmac
import ipaddress
import math
import os
import re
import socket
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlparse

import httpx
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from aitbc.aitbc_logging import get_logger
from aitbc.market import OfferStatus

from ...domain.market import MarketOffer, SoftwareService
from ...domain.offer_status import try_to_offer_status


logger = get_logger(__name__)


# Expected failure surface for the best-effort fallbacks below: filesystem/OS
# errors, HTTP/RPC I/O (httpx, incl. the lazily-imported health probes),
# sqlalchemy storage errors, lazy imports, request/JSON/Decimal decode
# (ValueError/InvalidOperation), and data-shape errors. RuntimeError covers
# abort-style raises a caller re-aborts with; genuine BaseExceptions still
# propagate (#1862).
_OPS_ERRORS = (
    ImportError,
    OSError,
    ValueError,
    InvalidOperation,
    KeyError,
    TypeError,
    AttributeError,
    RuntimeError,
    httpx.HTTPError,
    SQLAlchemyError,
)


# #1673: caller-supplied ttl_seconds reaches ``timedelta(seconds=...)`` when
# expires_at is derived — an unbounded value like 1e18 overflows the C long
# inside timedelta and answers 500. Jobs are short-lived by design; one year
# is the sane ceiling.
MAX_JOB_TTL_SECONDS = 31_536_000

# Same 1e15 ceiling the exchange/trading money validators use — an
# unbounded payment.amount (1e18/1e30 accepted pre-fix) has no sane
# interpretation and only risks downstream overflow (#1673-class).
MAX_PAYMENT_AMOUNT = Decimal("1000000000000000")

# Shop bearer tokens authorize in-flight work only; terminal lifecycle states
# must not admit new shop calls (#1817, #1597 residual).
_ACCESS_TOKEN_ACTIVE_STATES = frozenset({"QUEUED", "RUNNING"})

# #1835 F7: cap dispute opens per job — each open freeze stalls the sweeper,
# so unbounded re-arms are a settlement-griefing vector.
_MAX_JOB_DISPUTES = 3


def _validated_job_ttl(value: Any) -> int:
    """Normalize ``ttl_seconds`` to a bounded int, or raise ValueError (#1673).

    Accepts ints, integral floats and digit strings (the JSON body arrives as
    a plain dict, so pydantic never sees it). Rejects bools, non-integral
    floats, NaN/Infinity, non-numeric strings, and anything outside
    ``1..MAX_JOB_TTL_SECONDS``.
    """
    if isinstance(value, bool):
        raise ValueError("ttl_seconds must be an integer")
    if isinstance(value, int):
        ttl = value
    elif isinstance(value, float):
        if not math.isfinite(value) or not value.is_integer():
            raise ValueError("ttl_seconds must be a whole number of seconds")
        ttl = int(value)
    elif isinstance(value, str):
        text = value.strip()
        if not text.isdigit():
            raise ValueError("ttl_seconds must be an integer")
        ttl = int(text)
    else:
        raise ValueError("ttl_seconds must be an integer")
    if not 1 <= ttl <= MAX_JOB_TTL_SECONDS:
        raise ValueError(f"ttl_seconds must be between 1 and {MAX_JOB_TTL_SECONDS}")
    return ttl


def _finite_decimal(value: Any, field: str) -> Decimal:
    """Parse a caller-supplied decimal and require it finite (#1676-class).

    The booking/offer bodies arrive as plain dicts, so literal ``NaN`` /
    ``Infinity`` JSON floats reach here as Python floats — and
    ``Decimal(str(float("nan")))`` happily yields ``Decimal("NaN")``, which
    would otherwise be persisted on the bid/offer row and posted to the
    on-chain escrow payload. Reject non-finite values before they land.
    """
    try:
        parsed = Decimal(str(value))
    except Exception as e:
        raise ValueError(f"{field} must be a valid number") from e
    if not parsed.is_finite():
        raise ValueError(f"{field} must be finite")
    return parsed


def _money_decimal(value: Any, field: str) -> Decimal:
    """Finite + bounded money field: ``0 <= value <= MAX_PAYMENT_AMOUNT``.

    Same ceiling the job-payment validator and the exchange offer/book price
    bound use — a finite-but-absurd magnitude (1e30) has no sane interpretation
    and overflows Numeric(20,8) on stricter backends.
    """
    parsed = _finite_decimal(value, field)
    if parsed < 0:
        raise ValueError(f"{field} must be non-negative")
    if parsed > MAX_PAYMENT_AMOUNT:
        raise ValueError(f"{field} must not exceed {MAX_PAYMENT_AMOUNT}")
    return parsed


def _validate_booking_numbers(booking_data: dict[str, Any]) -> None:
    """Reject non-finite money/duration fields on an offer booking.

    Runs before the offer CAS claim so a bad payload cannot leave the offer
    flipped to ``booked`` with no bid behind it.
    """
    for field in ("price", "amount"):
        if booking_data.get(field) is not None:
            _money_decimal(booking_data[field], field)
    duration = booking_data.get("duration_hours")
    if duration is not None:
        try:
            hours = float(duration)
        except (TypeError, ValueError) as e:
            raise ValueError("duration_hours must be a number") from e
        if not math.isfinite(hours):
            raise ValueError("duration_hours must be finite")


def _resolve_bid_price(booking_data: dict[str, Any], offer_price: Any) -> Decimal:
    """Effective bid price for an offer booking, bounded to the offer's ask.

    #1914: ``complete_bid`` only enforces ``tx_value >= ait_to_units(bid.price)``
    # when that value is positive, so a zero (or under-ask) price lets any
    # confirmed buyer→provider tx — even a 0-value one — settle the bid and
    # delist the offer as paid. The bid price must therefore be strictly
    # positive and at least the offer's advertised price. Runs before the
    # offer CAS claim (via ``book_offer``) so a rejected price cannot strand
    # the offer ``booked`` with no bid.
    """
    price = _money_decimal(booking_data.get("price", offer_price or 0), "price")
    if price <= 0:
        raise ValueError("bid price must be positive")
    ask = _money_decimal(offer_price, "offer price") if offer_price is not None else Decimal(0)
    if price < ask:
        raise ValueError(f"bid price {price} is below the offer price {ask}")
    return price


def max_page_size() -> int:
    """Server-side ceiling for list endpoints (MARKET_MAX_PAGE_SIZE, default 500).

    Read per call so tests and env reloads take effect without a restart.
    """
    try:
        return max(1, int(os.getenv("MARKET_MAX_PAGE_SIZE", "500")))
    except ValueError:
        return 500


def _env_ttl_seconds(name: str, default: int) -> int:
    """Read a TTL env var in seconds; invalid values fall back to default."""
    try:
        return max(60, int(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


def bid_ttl_seconds() -> int:
    """Pending-bid lifetime before the sweeper expires it (#1554)."""
    return _env_ttl_seconds("MARKET_BID_TTL_SECONDS", 24 * 3600)


def offer_reservation_ttl_seconds() -> int:
    """Reserved/booked offer hold lifetime before release (#1554)."""
    return _env_ttl_seconds("MARKET_OFFER_RESERVATION_TTL_SECONDS", 24 * 3600)


def _pin_sample_limit() -> int:
    """Max pin/ls lines the offer health check counts (HEALTH_PIN_SAMPLE_LIMIT)."""
    try:
        return max(1, int(os.getenv("HEALTH_PIN_SAMPLE_LIMIT", "10000")))
    except ValueError:
        return 10000


async def _count_pin_lines(pin_resp: Any) -> int:
    """Count non-empty pin/ls lines as a bounded stream — never reads the body whole."""
    count = 0
    async for line in pin_resp.aiter_lines():
        if line.strip():
            count += 1
            if count >= _pin_sample_limit():
                break
    return count


_SECRET_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


def hash_access_secret(secret: str) -> str:
    """SHA-256 hex digest of an access secret — the only form stored at rest."""
    return hashlib.sha256(secret.encode()).hexdigest()


def is_hashed_secret(value: str) -> bool:
    """True when a stored access_secret is already a sha256 hexdigest.

    token_urlsafe(32) plaintext is at most 43 chars and can contain '-_',
    so a 64-char lowercase-hex value is unambiguously a digest.
    """
    return bool(_SECRET_HASH_RE.match(value or ""))


def _secret_matches(stored: str, provided: str) -> bool:
    """Constant-time secret check that tolerates pre-hash plaintext rows.

    The plaintext path is insurance for databases restored from a
    pre-migration backup — remove it at the next secret rotation.
    """
    candidate = hash_access_secret(provided) if is_hashed_secret(stored) else provided
    return hmac.compare_digest(stored, candidate)


def _rating_created_at(value: Any) -> datetime:
    """Normalize a remote rating timestamp to the column's naive-UTC convention.

    ServiceRating.created_at is stored naive (``now(UTC).replace(tzinfo=None)``).
    Remote payloads are uncontrolled: an offset-aware ISO string would make the
    ``remote_created > existing.created_at`` comparison raise TypeError and abort
    the whole sync batch.
    """
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is not None:
        dt = dt.astimezone(UTC).replace(tzinfo=None)
    return dt


def _coerce_remote_rating(value: Any) -> float:
    """Validate a remote rating before it is persisted (MKT-RATING-1, #1446).

    ``add_service_rating`` enforces ``1.0 <= rating <= 5.0`` on the local
    submit path, but ``sync_ratings_from_remote`` used to store whatever a
    peer sent — out-of-range, non-finite, or non-numeric values were folded
    straight into ``avg_rating``/``rating_count``. Remote payloads are
    uncontrolled, so the same range check runs here; the coerced float (not
    the raw value) is what gets stored, matching the column type. Raises
    ``ValueError`` so the caller counts the row as failed.
    """
    if isinstance(value, bool):
        raise ValueError(f"remote rating must be a number, got {value!r}")
    try:
        rating = float(value)
    except (TypeError, ValueError) as e:
        raise ValueError(f"remote rating is not numeric: {value!r}") from e
    if not math.isfinite(rating) or not 1.0 <= rating <= 5.0:
        raise ValueError(f"remote rating {rating!r} outside [1.0, 5.0]")
    return rating


# Keys a market job row may expose to the unauthenticated feed
# (GET /v1/market/jobs and GET /v1/market/jobs/{job_id}). An allow-list, not
# a block-list: customer file details and rental identifiers — payload.*,
# constraints.*, buyer_address, access_key, client_id/client_ref — never
# leave the service without authentication. The owner/provider views return
# the full _job_to_dict record behind auth, so fields added to the full
# serializer stay private by default.
PUBLIC_JOB_FIELDS = (
    "job_id",
    "offer_id",
    "plugin_id",
    "service_type",
    "model",
    "provider_address",
    "state",
    "ttl_seconds",
    "requested_at",
    "expires_at",
    "completed_at",
    "error",
    "result",
    "receipt",
    "payment_id",
    "payment_status",
    "payment_amount",
    "payment_token",
    "escrow_contract_id",
    "tx_hash",
    "refund_tx_hash",
    "created_at",
    "updated_at",
)

# Nested payment object: settlement hashes and status are public chain data;
# escrow_address/refund_address tie the row to the customer's wallets and
# meta_data is free-form, so all three stay out.
PUBLIC_PAYMENT_FIELDS = (
    "payment_id",
    "job_id",
    "amount",
    "currency",
    "status",
    "payment_method",
    "transaction_hash",
    "refund_transaction_hash",
    "created_at",
    "updated_at",
    "escrowed_at",
    "released_at",
    "refunded_at",
    "expires_at",
)


def coerce_offer_expires_at(value: Any) -> datetime | None:
    """Normalize a caller-supplied ``expires_at`` to naive UTC (#1554).

    The column is a plain ``DateTime``; the codebase convention is naive-UTC
    (#1575), so an aware input is converted and a bare string is parsed here
    so a malformed value fails as a 400 ValueError instead of a 500.
    """
    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if not isinstance(value, datetime):
        raise ValueError("expires_at must be an ISO-8601 datetime")
    if value.tzinfo is not None:
        return value.astimezone(UTC).replace(tzinfo=None)
    return value


def offer_listing_expired(offer: MarketOffer, now: datetime | None = None) -> bool:
    """True when an AVAILABLE-state offer is past its ``expires_at`` (#1554).

    Only the available listing lapses — booked/reserved holds have their own
    ``_reserved_until`` deadline and in_use rows run paid work.
    """
    exp = offer.expires_at
    if exp is None:
        return False
    if try_to_offer_status(offer.status) is not OfferStatus.AVAILABLE:
        return False
    if exp.tzinfo is not None:
        exp = exp.replace(tzinfo=None)
    now = now or datetime.now(UTC).replace(tzinfo=None)
    return exp < now


async def _get_by_caller_id(session: AsyncSession, model: Any, data: dict[str, Any]) -> Any | None:
    """Return the row a caller-supplied ``id`` already names (#1553).

    These create paths splat the request body into the model, so ``id`` is a
    natural idempotency key: a retry must replay the existing row, not die on
    the primary key or stack a duplicate.
    """
    rid = data.get("id")
    if rid is None:
        return None
    return await session.get(model, str(rid))


async def _replay_after_integrity_conflict(session: AsyncSession, model: Any, data: dict[str, Any]) -> Any | None:
    """Roll back a lost first-write race and return the winner's row (#1553)."""
    await session.rollback()
    return await _get_by_caller_id(session, model, data)


def public_job_view(job: dict[str, Any]) -> dict[str, Any]:
    """Redact a ``_job_to_dict`` row for the unauthenticated market feed."""
    view = {key: job[key] for key in PUBLIC_JOB_FIELDS if key in job}
    if "payment" in job:
        payment = job["payment"]
        view["payment"] = (
            {key: payment[key] for key in PUBLIC_PAYMENT_FIELDS if key in payment} if isinstance(payment, dict) else payment
        )
    return view


def _isoformat(value: Any) -> str | None:
    """ISO-format a stored timestamp, tolerating legacy non-datetime values.

    ``_job_to_dict``/``_payment_to_dict`` feed the public job routes; a row
    whose timestamp column holds a raw string (a pre-normalization write)
    must degrade to the stored string rather than 500 the read (#1449).
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


_LOOPBACK_HOSTS = {"localhost", "localhost.localdomain", "ip6-localhost"}

# Fields a provider may set on their own offer through POST /v1/market/offer.
# An allow-list, not a block-list: server-owned columns (block_*, tx_hash,
# avg_rating, rating_count, registered_at, updated_at) are filled only from
# verified chain anchors or server logic, and columns added later are safe
# by default.
_REGISTRATION_FIELDS = {
    "service_type",
    "model",
    "price",
    "price_unit",
    "offer_id",
    "endpoint",
    "public_endpoint",
    "health_url",
    "provider_address",
    "node_id",
    "gpu_name",
    "gpu_device",
    "gpu_uuid",
    "gpu_offer_id",
    "gpu_model",
    "gpu_memory_gb",
    "compute_capability",
    "description",
    "status",
    "disk_quota_mb",
}

# Which on-chain GPU registrations the default listing shows. The chain keeps a
# registration its registrant deactivated; only "active" ones are offered.
_GPU_LISTING_DEFAULT_STATUS = "active"

# An unconfirmed offer that just resolved to nothing stays unconfirmed for
# this long before another chain probe — bounds anchor RPCs per offer
# without ever hiding a late-arriving seal.
_ANCHOR_NEGATIVE_TTL_SECONDS = 120.0

# Hard cap on the shared anchor-negative map. Expired entries are dropped on
# every resolve pass; the cap bounds the burst between two passes, when many
# distinct signable registrations are probed inside one TTL window (#819).
_ANCHOR_NEGATIVES_MAX = 4096

# Health probes go to provider-registered URLs, so any wallet that can list a
# service could aim the market host at its own loopback, the LAN or the cloud
# metadata address (#819). Only hosts that resolve entirely to public addresses
# are probed. Same-host services listed with an http://localhost:<port> health
# URL need an explicit opt-in: comma-separated host:port pairs in this env var.
_HEALTH_ALLOWED_TARGETS_ENV = "MARKET_HEALTH_ALLOWED_TARGETS"
_HEALTH_REFUSED = {"healthy": False, "reason": "health_url target is not a public address"}


async def _check_health_url(url: str) -> None:
    """Raise ValueError unless *url* is http(s) and its host resolves only to
    public addresses (loopback, private, link-local, metadata and multicast are
    all refused), or is listed in ``MARKET_HEALTH_ALLOWED_TARGETS``.

    The check runs before the request and the client does not follow
    redirects, so a redirect cannot reach a non-public target either."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"scheme not allowed: {parsed.scheme or '(none)'}")
    host = parsed.hostname or ""
    if not host:
        raise ValueError("no host")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    allowed = {t.strip().lower() for t in os.environ.get(_HEALTH_ALLOWED_TARGETS_ENV, "").split(",") if t.strip()}
    if f"{host.lower()}:{port}" in allowed:
        return
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except OSError as e:
        raise ValueError(f"host does not resolve: {host}") from e
    if not infos:
        raise ValueError(f"host does not resolve: {host}")
    for info in infos:
        addr = ipaddress.ip_address(info[4][0])
        if not addr.is_global:
            raise ValueError(f"{host} resolves to a non-public address: {addr}")


def _sanitize_endpoint(url: str | None) -> str | None:
    """Strip loopback/unspecified host addresses from serialized offer dicts.

    Local endpoints (``http://localhost:8110``, ``http://127.0.0.1:8110``)
    are internal routing data and leak topology through the public API.
    LAN addresses are operator-facing and stay visible.
    """
    if not url:
        return url
    host = urlparse(url).hostname or ""
    if host in _LOOPBACK_HOSTS or host in {"::1", "0.0.0.0"} or host.startswith("127."):
        return None
    return url


def _gpu_offer_to_service_dict(offer: dict[str, Any], chain_id: str | None, hub_rpc_url: str) -> dict[str, Any]:
    """Map a /rpc/gpus GPU registration onto the software-offer shape."""
    return {
        "plugin_id": offer.get("gpu_id", offer.get("id", "unknown")),
        "service_type": "gpu_market",
        "model": offer.get("model", "unknown"),
        # str(Decimal): these dicts go straight to HTTP responses — a bare
        # Decimal is float-cast by FastAPI's jsonable_encoder, losing
        # precision on a public price field (#1635).
        "price": str(Decimal(str(offer.get("price_per_hour")))),
        "price_unit": "per_hour",
        "offer_id": offer.get("gpu_id", "unknown"),
        "endpoint": None,
        "public_endpoint": None,
        "health_url": None,
        "provider_address": offer.get("provider", offer.get("miner_id", "")),
        "registered_by": offer.get("registered_by"),
        "node_id": offer.get("miner_id", "unknown"),
        "gpu_name": offer.get("model", "N/A"),
        "gpu_device": "0",
        "gpu_uuid": offer.get("uuid") or offer.get("hardware_uuid", "N/A"),
        "gpu_offer_id": offer.get("gpu_id", "N/A"),
        "gpu_model": offer.get("model", "N/A"),
        "gpu_memory_gb": offer.get("memory_gb"),
        "compute_capability": offer.get("compute_capability", ""),
        "description": offer.get("description", ""),
        "status": offer.get("status", "active"),
        "registered_at": offer.get("registered_at") or offer.get("created_at"),
        "updated_at": offer.get("updated_at"),
        "avg_rating": 0,
        "rating_count": 0,
        "chain_id": offer.get("chain_id", chain_id),
        "disk_quota_mb": offer.get("disk_quota_mb"),
        # Blockchain verification information
        "block_height": offer.get("block_height"),
        "block_hash": offer.get("block_hash"),
        "block_timestamp": offer.get("block_timestamp"),
        "block_proposer": offer.get("block_proposer"),
        "tx_hash": offer.get("tx_hash", ""),
        "confirmed": offer.get("block_height") is not None,
    }


def _local_offer_dict(s: "SoftwareService") -> dict[str, Any]:
    """Serialize a local SoftwareService row into the public offer shape."""
    return {
        "plugin_id": s.plugin_id,
        "service_type": s.service_type,
        "model": s.model,
        "price": str(s.price),
        "price_unit": s.price_unit,
        "offer_id": s.offer_id,
        "endpoint": _sanitize_endpoint(s.endpoint),
        "public_endpoint": s.public_endpoint,
        "health_url": _sanitize_endpoint(s.health_url),
        "provider_address": s.provider_address,
        "node_id": s.node_id,
        "gpu_name": s.gpu_name,
        "gpu_device": s.gpu_device,
        "gpu_uuid": s.gpu_uuid,
        "gpu_offer_id": s.gpu_offer_id,
        "gpu_model": s.gpu_model,
        "gpu_memory_gb": s.gpu_memory_gb,
        "compute_capability": s.compute_capability,
        "description": s.description,
        "status": s.status,
        "registered_at": s.registered_at.isoformat() if s.registered_at else None,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
        "avg_rating": s.avg_rating,
        "rating_count": s.rating_count,
        "disk_quota_mb": s.disk_quota_mb,
        # Blockchain verification information
        "block_height": s.block_height,
        "block_hash": s.block_hash,
        "block_timestamp": s.block_timestamp.isoformat() if s.block_timestamp else None,
        "block_proposer": s.block_proposer,
        "tx_hash": s.tx_hash,
        "confirmed": bool(s.block_height),  # Consider confirmed if it has block info
    }
