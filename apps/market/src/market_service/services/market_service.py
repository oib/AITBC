"""
Market service for managing market operations
"""

import asyncio
import hashlib
import hmac
import ipaddress
import math
import os
import re
import socket
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from aitbc.aitbc_logging import get_logger
from aitbc.crypto.signature_recovery import canonical_address
from aitbc.market import BlockchainRPCClient, OfferFSM, OfferStatus
from aitbc.market.offer_registration import verify_offer_registration
from aitbc.utils.chain_id import resolve_chain_id
from aitbc.utils.units import ait_to_units, units_to_ait

from ..config import settings
from ..domain.market import Bid, MarketJob, MarketJobPayment, MarketOffer, OfferAnchor, ServiceRating, SoftwareService
from ..domain.offer_status import spellings_of, to_offer_status, try_to_offer_status

logger = get_logger(__name__)


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


class MarketService:
    # Shared across per-request service instances: (namespaced anchor key,
    # binding identity) -> monotonic deadline before which that pair is not
    # probed on chain again. The binding is part of the key so a negative
    # cached for one provider identity can't suppress re-resolution when the
    # offer's binding changes (e.g. registered_by appears after an upgrade).
    _anchor_negatives: dict[tuple[str, str], float] = {}

    @classmethod
    def _evict_anchor_negatives(cls, now: float) -> None:
        """Drop every entry whose deadline has passed (#819: they were only
        filtered at read time, so the shared map only ever grew)."""
        for stale in [key for key, deadline in cls._anchor_negatives.items() if deadline <= now]:
            del cls._anchor_negatives[stale]

    @classmethod
    def _remember_anchor_negative(cls, key: tuple[str, str], deadline: float) -> None:
        """Record a negative and hold the map at ``_ANCHOR_NEGATIVES_MAX``,
        dropping the entries closest to expiry first."""
        cls._anchor_negatives[key] = deadline
        excess = len(cls._anchor_negatives) - _ANCHOR_NEGATIVES_MAX
        if excess > 0:
            for oldest in sorted(cls._anchor_negatives, key=cls._anchor_negatives.__getitem__)[:excess]:
                del cls._anchor_negatives[oldest]

    def __init__(self, session: AsyncSession):
        self.session = session
        self._rpc_client = BlockchainRPCClient(
            rpc_url=settings.blockchain_rpc_url,
            api_key=settings.blockchain_rpc_api_key,
        )

    async def list_offers(
        self,
        status: str | None = None,
        region: str | None = None,
        gpu_model: str | None = None,
        chain_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """List market offers (v0.6.6: with optional chain_id filter)"""
        try:
            logger.info(
                "list_offers called with filters: status=%s, region=%s, gpu_model=%s, chain_id=%s",
                status,
                region,
                gpu_model,
                chain_id,
            )
            stmt = select(MarketOffer)
            if status:
                # Matched by state, not by spelling. Filtering on the literal string meant
                # `?status=available` did not return the offer stored as "open" and
                # `?status=booked` did not return the one stored as "reserved" -- the same
                # offer was visible or invisible depending on which word the caller happened
                # to use, with nothing to tell them there was another (V23-83).
                stmt = stmt.where(MarketOffer.status.in_(spellings_of(to_offer_status(status))))  # type: ignore[attr-defined]
            if region:
                stmt = stmt.where(MarketOffer.region == region)
            if gpu_model:
                stmt = stmt.where(MarketOffer.gpu_model == gpu_model)
            if chain_id:
                stmt = stmt.where(MarketOffer.chain_id == chain_id)
            stmt = stmt.limit(max_page_size())
            logger.info("Executing database query for offers")
            result = list((await self.session.execute(stmt)).all())
            logger.info("Retrieved %s offers", len(result))
            offers_list = []
            for row in result:
                offer = row[0] if row else None
                # #1554 lazy expiry: a past-due available listing is hidden
                # even before the sweeper flips its status.
                if offer and not offer_listing_expired(offer):
                    offers_list.append(
                        {
                            "id": offer.id,
                            "provider": offer.provider,
                            "capacity": offer.capacity,
                            # str(Decimal): public price fields must not be
                            # float-cast by jsonable_encoder (#1635).
                            "price": str(offer.price),
                            "sla": offer.sla,
                            "status": offer.status,
                            "created_at": offer.created_at.isoformat() if offer.created_at else None,
                            "attributes": offer.attributes,
                            "gpu_model": offer.gpu_model,
                            "gpu_memory_gb": offer.gpu_memory_gb,
                            "gpu_count": offer.gpu_count,
                            "cuda_version": offer.cuda_version,
                            "price_per_hour": str(offer.price_per_hour) if offer.price_per_hour is not None else None,
                            "region": offer.region,
                            "chain_id": offer.chain_id,
                        }
                    )
            logger.info("Converted %s offers to dictionaries", len(offers_list))
            return offers_list
        except Exception as e:
            logger.error("Error in list_offers: %s: %s", type(e).__name__, str(e))
            raise

    async def update_offer_status(self, offer_id: str, new_status: str) -> dict[str, Any]:
        """Update offer status with FSM validation (v0.6.6).

        Uses OfferFSM to validate state transitions. Rejects invalid transitions.

        Both status words go through `to_offer_status` rather than `OfferFSM.from_string`.
        The strict parser only accepts the five `OfferStatus` values, and neither of the two
        words this method is actually called with is one of them: the stored status is
        "booked" or "open", and the requested status is "cancelled". Every call therefore
        raised, and the only caller -- `cancel_offer` -- had no handler, so the endpoint
        answered 500 for every offer in the database (V23-83).
        """
        try:
            stmt = select(MarketOffer).where(MarketOffer.id == offer_id)
            result = (await self.session.execute(stmt)).first()
            offer = result[0] if result else None
            if not offer:
                raise ValueError(f"Offer not found: {offer_id}")

            # Validate transition via OfferFSM
            current = to_offer_status(offer.status)
            fsm = OfferFSM(current)
            fsm.transition(to_offer_status(new_status))

            offer.status = new_status
            await self.session.commit()
            logger.info("Offer %s status updated: %s", offer_id, new_status)
            return {"id": offer_id, "status": new_status}
        except ValueError:
            raise
        except Exception as e:
            logger.error("Error in update_offer_status: %s: %s", type(e).__name__, str(e))
            raise

    async def get_offer(self, offer_id: str) -> MarketOffer | None:
        """Get a specific market offer"""
        try:
            logger.info("get_offer called with offer_id=%s", offer_id)
            stmt = select(MarketOffer).where(MarketOffer.id == offer_id)
            result = (await self.session.execute(stmt)).first()
            offer = result[0] if result else None
            logger.info("Retrieved offer: %s, found: %s", offer_id, offer is not None)
            return offer
        except Exception as e:
            logger.error("Error in get_offer: %s: %s", type(e).__name__, str(e))
            raise

    async def book_offer(self, offer_id: str, booking_data: dict[str, Any]) -> dict[str, Any]:
        """Book/purchase a market offer"""
        try:
            logger.info("book_offer called with offer_id=%s, data keys: %s", offer_id, booking_data.keys())
            offer = await self.get_offer(offer_id)
            if not offer:
                logger.error("Offer not found: %s", offer_id)
                raise ValueError(f"Offer not found: {offer_id}")
            # By state rather than by spelling, so the offer stored as "open" is bookable --
            # it is available, it just says so in coordinator-api's word (V23-83).
            current = to_offer_status(offer.status)
            if current is not OfferStatus.AVAILABLE:
                raise ValueError(f"Offer {offer_id} is not available (status={offer.status})")
            # #1554 lazy expiry: an available offer past expires_at is dead
            # even before the sweeper's next pass — flip it and refuse the
            # booking rather than sell an expired listing.
            if offer_listing_expired(offer):
                offer.status = OfferStatus.EXPIRED.value
                self.session.add(offer)
                await self.session.commit()
                raise ValueError(f"Offer {offer_id} has expired")
            # Non-finite money fields (literal NaN/Infinity JSON) must die
            # here — before the CAS claim flips the offer to 'booked'.
            _validate_booking_numbers(booking_data)
            # Booking is the one transition this service performed without asking the FSM:
            # it assigned "booked" directly, which is how a status the FSM cannot parse came
            # to be in the database in the first place. Validated before the bid is created,
            # so a rejected transition does not leave a bid behind.
            OfferFSM(current).transition(OfferStatus.RESERVED)

            # CAS claim (#1424 item 6): the AVAILABLE check above and the status
            # write used to be separated by the bid insert's awaits, so two
            # concurrent bookings could both pass and both persist a bid. The
            # conditional UPDATE ... WHERE status IN (available spellings) is
            # the compare-and-swap — rowcount != 1 means another booking (or a
            # cancel) won the row first. It shares _create_bid's commit, so the
            # claim and the bid land atomically: no window with the offer
            # 'booked' and no bid, and none with a bid on a still-available
            # offer. The #1554 reservation deadline rides in the same write
            # so the sweeper TTL cannot be lost between commits.
            booked_attrs = dict(offer.attributes or {})
            booked_attrs["_reserved_until"] = (
                datetime.now(UTC) + timedelta(seconds=offer_reservation_ttl_seconds())
            ).isoformat()
            claim = await self.session.execute(
                update(MarketOffer)
                .where(
                    col(MarketOffer.id) == offer_id,
                    col(MarketOffer.status).in_(spellings_of(OfferStatus.AVAILABLE)),
                )
                .values(status="booked", attributes=booked_attrs)
            )
            if getattr(claim, "rowcount", 0) != 1:
                raise ValueError(f"Offer {offer_id} is not available (status={offer.status})")

            bid = await self._create_bid(offer_id, booking_data, offer)
            await self.session.refresh(offer)  # _create_bid's commit expired it (#820)
            provider = offer.provider
            # The CAS claim already wrote status='booked' and the #1554
            # _reserved_until deadline atomically with the bid; the ORM row
            # is refreshed below so no second write is needed here.
            await self.session.refresh(bid)
            logger.info("Created bid for offer %s: %s", offer_id, bid.id)
            return {
                "bid_id": bid.id,
                "offer_id": offer_id,
                "provider": provider,
                "status": "pending",
                "message": "Bid created successfully",
                "escrow_contract_id": None,
            }
        except Exception as e:
            logger.error("Error in book_offer: %s: %s", type(e).__name__, str(e))
            raise

    async def create_offer(self, offer_data: dict[str, Any]) -> MarketOffer:
        """Create a new market offer"""
        try:
            logger.info("create_offer called with data keys: %s", offer_data.keys())
            if "wallet" in offer_data and "provider" not in offer_data:
                offer_data["provider"] = offer_data["wallet"]
                logger.info("Mapped wallet '%s' to provider", offer_data["wallet"])
            # `status` is a plain string on the model and this method splats the request body
            # straight into it, so until now a caller could create an offer in any state they
            # could spell -- including one no part of this service understands, which then
            # made every later transition on that offer fail. That is how the deployed
            # database came to hold an offer whose status is "open" (V23-83). Validating here
            # is what makes "every stored status parses" true rather than aspirational.
            if "status" in offer_data:
                to_offer_status(offer_data["status"])
            if "expires_at" in offer_data:
                # #1554: normalize to naive UTC before the model sees it.
                offer_data["expires_at"] = coerce_offer_expires_at(offer_data["expires_at"])
            # Money columns are Numeric — a literal NaN/Infinity in the dict
            # body would persist Decimal('NaN') and poison every later
            # aggregate/booking that reads it.
            for price_field in ("price", "price_per_hour"):
                if offer_data.get(price_field) is not None:
                    offer_data[price_field] = _money_decimal(offer_data[price_field], price_field)
            existing: MarketOffer | None = await _get_by_caller_id(self.session, MarketOffer, offer_data)
            if existing is not None:
                return existing
            offer = MarketOffer(**offer_data)
            self.session.add(offer)
            try:
                await self.session.commit()
            except IntegrityError:
                replay: MarketOffer | None = await _replay_after_integrity_conflict(self.session, MarketOffer, offer_data)
                if replay is not None:
                    return replay
                raise
            await self.session.refresh(offer)
            logger.info("Created offer with id: %s", offer.id)
            return offer
        except Exception as e:
            await self.session.rollback()
            logger.error("Error in create_offer: %s: %s", type(e).__name__, str(e))
            raise

    async def get_analytics(self, period_type: str = "daily") -> dict[str, Any]:
        """Get market analytics"""
        from sqlalchemy import func, select

        offer_count_stmt = select(func.count()).select_from(MarketOffer)
        offer_count_result = await self.session.execute(offer_count_stmt)
        total_offers = offer_count_result.scalar() or 0
        avg_price_stmt = select(func.avg(MarketOffer.price_per_hour)).where(MarketOffer.price_per_hour.isnot(None))  # type: ignore[union-attr]
        avg_price_result = await self.session.execute(avg_price_stmt)
        avg_price = (
            avg_price_result.scalar() or 0.0
        )  # not-money: ratio, threshold or configuration default — not an amount of money
        capacity_stmt = select(func.sum(MarketOffer.capacity))
        capacity_result = await self.session.execute(capacity_stmt)
        total_capacity = capacity_result.scalar() or 0
        return {
            "period_type": period_type,
            "total_offers": total_offers,
            "total_capacity": total_capacity,
            "average_price": str(Decimal(avg_price).quantize(Decimal("0.01"))) if avg_price else "0",
        }

    async def list_plugins(self, plugin_type: str | None = None, status: str = "approved") -> list[dict[str, Any]]:
        """List plugins from database"""
        from sqlalchemy import select

        from ..domain.market import Plugin

        try:
            stmt = select(Plugin)
            if plugin_type:
                stmt = stmt.where(Plugin.type == plugin_type)  # type: ignore[arg-type]
            if status:
                stmt = stmt.where(Plugin.status == status)  # type: ignore[arg-type]
            stmt = stmt.order_by(Plugin.created_at.desc())  # type: ignore[attr-defined]
            stmt = stmt.limit(max_page_size())
            result = await self.session.execute(stmt)
            plugins = result.scalars().all()
            return [
                {
                    "id": p.id,
                    "name": p.name,
                    "description": p.description,
                    "author": p.author,
                    "type": p.type,
                    "version": p.version,
                    "ipfs_cid": p.ipfs_cid,
                    "status": p.status,
                    "download_count": p.download_count,
                    "rating": p.rating,
                    "created_at": p.created_at.isoformat() if p.created_at else None,
                }
                for p in plugins
            ]
        except Exception as e:
            logger.error("Error in list_plugins: %s: %s", e.__class__.__name__, e)
            raise

    async def register_plugin(self, plugin_data: dict[str, Any]) -> dict[str, Any]:
        """Register a new plugin"""
        from ..domain.market import Plugin

        try:
            # #1553: a caller-supplied id is the natural idempotency key — a
            # retry replays the existing row instead of dying on the PK.
            plugin_id = plugin_data.get("id")
            if plugin_id:
                existing = await self.session.get(Plugin, str(plugin_id))
                if existing is not None:
                    return {
                        "id": existing.id,
                        "name": existing.name,
                        "status": existing.status,
                        "deduplicated": True,
                    }
            plugin = Plugin(**plugin_data)
            self.session.add(plugin)
            await self.session.commit()
            await self.session.refresh(plugin)
            logger.info("Registered plugin with id: %s", plugin.id)
            return {"id": plugin.id, "name": plugin.name, "status": plugin.status}
        except IntegrityError:
            # Concurrent first-write with the same caller id: the winner's
            # row is the replay target (#1553).
            await self.session.rollback()
            plugin_id = plugin_data.get("id")
            if plugin_id:
                existing = await self.session.get(Plugin, str(plugin_id))
                if existing is not None:
                    return {
                        "id": existing.id,
                        "name": existing.name,
                        "status": existing.status,
                        "deduplicated": True,
                    }
            raise
        except Exception as e:
            await self.session.rollback()
            logger.error("Error in register_plugin: %s: %s", type(e).__name__, str(e))
            raise

    async def list_software_services(
        self, service_type: str | None = None, status: str | None = None, chain_id: str | None = None
    ) -> list[dict[str, Any]]:
        """List software services with optional filters - aggregates from blockchain and local database

        v0.6.6: Uses BlockchainRPCClient for blockchain queries with chain_id filter.
        """
        from sqlalchemy import select

        from ..domain.market import SoftwareService

        try:
            # First, try to get offers from blockchain via RPC (v0.6.6: uses BlockchainRPCClient)
            blockchain_offers = []
            try:
                # Query GPU offers from blockchain with chain_id filter. A GPU its
                # registrant took out of service (GPU_DEREGISTER) stays on the chain
                # as "deactivated"; the default listing leaves it out, and asking
                # for a status explicitly still shows it.
                offers = await self._rpc_client.query_offers(
                    chain_id=chain_id,
                    status=status if status else _GPU_LISTING_DEFAULT_STATUS,
                )
                for offer in offers:
                    # #1566: a GPU holding open on-chain allocations stays
                    # status='active' but is spoken for — an allocation does
                    # not touch gpu.status. The chain RPC reports the count;
                    # nodes predating the field yield 0 and keep old behavior.
                    if int(offer.get("active_allocations") or 0) > 0:
                        logger.info(
                            "Skipping allocated GPU offer %s (active_allocations=%s)",
                            offer.get("gpu_id", offer.get("id", "unknown")),
                            offer.get("active_allocations"),
                        )
                        continue
                    price_per_hour = offer.get("price_per_hour")
                    if price_per_hour is None:
                        logger.warning(
                            "Skipping blockchain offer %s: missing price_per_hour",
                            offer.get("gpu_id", offer.get("id", "unknown")),
                        )
                        continue
                    try:
                        blockchain_offers.append(_gpu_offer_to_service_dict(offer, chain_id, settings.hub_rpc_url))
                    except Exception as e:
                        logger.warning("Failed to parse blockchain offer: %s", e)
                        continue

                logger.info("Retrieved %s offers from blockchain RPC (chain_id=%s)", len(blockchain_offers), chain_id)
                # The RPC page is unbounded — cap it before the merge so a
                # large on-chain offer set cannot be materialised and
                # re-merged in full (#1543 residual).
                blockchain_offers = blockchain_offers[: max_page_size()]
            except Exception as e:
                logger.warning("Failed to get offers from blockchain RPC: %s", e)

            # Second, get offers from local database
            query = select(SoftwareService)
            if service_type:
                query = query.where(SoftwareService.service_type == service_type)  # type: ignore[arg-type]
            if status:
                query = query.where(SoftwareService.status == status)  # type: ignore[arg-type]
            query = query.limit(max_page_size())
            result = await self.session.execute(query)
            local_services = result.scalars().all()

            local_offers = [_local_offer_dict(s) for s in local_services]

            # Merge blockchain and local offers, preferring blockchain
            seen_plugin_ids = set()
            merged_offers = []

            # Add blockchain offers first
            for offer in blockchain_offers:
                plugin_id = offer["plugin_id"]
                if plugin_id not in seen_plugin_ids:
                    merged_offers.append(offer)
                    seen_plugin_ids.add(plugin_id)

            # Add local offers that aren't in blockchain
            for offer in local_offers:
                plugin_id = offer["plugin_id"]
                if plugin_id not in seen_plugin_ids:
                    merged_offers.append(offer)
                    seen_plugin_ids.add(plugin_id)

            local_rows = {s.plugin_id: s for s in local_services}
            await self._resolve_offer_anchors(merged_offers, chain_id, local_rows)

            # The merge can exceed the page ceiling (blockchain page + local
            # page); the public list contract is one bounded page (#1543).
            merged_offers = merged_offers[: max_page_size()]

            logger.info(
                "Returning %s total offers (%s from blockchain, %s from local)",
                len(merged_offers),
                len(blockchain_offers),
                len(local_offers),
            )

            return merged_offers
        except Exception as e:
            logger.error("Error in list_software_services: %s: %s", type(e).__name__, str(e))
            raise

    @staticmethod
    def _anchor_belongs_to_provider(anchor_tx: dict[str, Any], offer: dict[str, Any], is_gpu: bool) -> bool:
        """Bind an anchor tx to the offer's provider.

        GPU offers bind on the registrant wallet when ``registered_by`` is
        available — the register tx's authenticated ``sender`` must be that
        wallet, which node labels (``miner_id``) can't prove. Older rows
        without the field fall back to ``payload.miner_id`` matching the
        offer's provider id. Software offers carry the provider's wallet
        address, matching the anchor tx's authenticated ``sender``. Anything
        that can't be bound to the claimed provider is not this offer's
        anchor — an attacker copying an offer_id can't borrow someone else's
        seal.
        """
        provider = offer.get("provider_address") or ""
        if not provider:
            return False
        payload = anchor_tx.get("payload") or {}
        if is_gpu:
            sender = anchor_tx.get("sender") or ""
            registered_by = offer.get("registered_by") or ""
            if registered_by:
                return bool(sender) and canonical_address(sender) == canonical_address(registered_by)
            return payload.get("miner_id") == provider
        sender = anchor_tx.get("sender") or ""
        return bool(sender) and canonical_address(sender) == canonical_address(provider)

    @staticmethod
    def _anchor_binding_key(offer: dict[str, Any], is_gpu: bool) -> str:
        """The offer-side identity an anchor must bind to — what
        ``_anchor_belongs_to_provider`` requires the tx's authenticated
        sender (or, pre-``registered_by``, the miner label) to equal. Stored
        on ``OfferAnchor`` rows: a changed binding forces live re-resolution
        instead of replaying a stale confirmation."""
        provider = str(offer.get("provider_address") or "")
        if is_gpu:
            registered_by = offer.get("registered_by") or ""
            return canonical_address(registered_by) if registered_by else provider
        return canonical_address(provider)

    @staticmethod
    def _anchor_timestamp(anchor_tx: dict[str, Any]) -> tuple[str | None, datetime | None]:
        """Return (iso string for the offer dict, naive datetime for columns).

        Transaction.timestamp is already a string column; numeric only if a
        serializer emitted epoch seconds."""
        ts = anchor_tx.get("timestamp")
        if ts is None:
            return None, None
        if isinstance(ts, str):
            try:
                return ts, datetime.fromisoformat(ts).replace(tzinfo=None)
            except ValueError:
                return ts, None
        dt = datetime.fromtimestamp(ts, UTC)
        return dt.isoformat(), dt.replace(tzinfo=None)

    def _persist_anchor(
        self,
        dbkey: str,
        offer: dict[str, Any],
        is_gpu: bool,
        anchor_tx: dict[str, Any],
        block_ts: datetime | None,
        existing_row: OfferAnchor | None,
        local_rows: dict[str, SoftwareService] | None,
    ) -> bool:
        """Store a verified anchor so later listings skip chain probes.

        Offers backed by a local ``SoftwareService`` take confirmation on the
        row's ``block_*`` columns — which is what ``_local_offer_dict`` reads
        and what the registration allow-list keeps providers from forging.
        On-chain-only offers (GPU bundles) get an ``OfferAnchor`` row keyed
        under the same namespace, bound to the provider identity verified
        now. Returns True when something was written.
        """
        row = local_rows.get(str(offer.get("plugin_id") or "")) if local_rows else None
        if row is not None:
            changed = False
            for attr, value in (
                ("tx_hash", anchor_tx.get("tx_hash")),
                ("block_height", anchor_tx.get("block_height")),
                ("block_hash", anchor_tx.get("block_hash")),
                ("block_proposer", anchor_tx.get("block_proposer")),
                ("block_timestamp", block_ts),
            ):
                if value is not None and getattr(row, attr) != value:
                    setattr(row, attr, value)
                    changed = True
            return changed
        anchor = existing_row if existing_row is not None else OfferAnchor(key=dbkey)
        if existing_row is None:
            self.session.add(anchor)
        anchor.tx_hash = anchor_tx.get("tx_hash") or ""
        anchor.block_height = anchor_tx.get("block_height")
        anchor.block_hash = anchor_tx.get("block_hash")
        anchor.block_proposer = anchor_tx.get("block_proposer")
        ts = anchor_tx.get("timestamp")
        anchor.block_timestamp = ts if isinstance(ts, str) else (datetime.fromtimestamp(ts, UTC).isoformat() if ts else None)
        anchor.registered_at = anchor_tx.get("created_at") or anchor.block_timestamp
        anchor.bound_provider = self._anchor_binding_key(offer, is_gpu)
        anchor.resolved_at = datetime.now(UTC).replace(tzinfo=None)
        return True

    async def _resolve_offer_anchors(
        self,
        offers: list[dict[str, Any]],
        chain_id: str | None,
        local_rows: dict[str, SoftwareService] | None = None,
    ) -> None:
        """Mark offers as confirmed by joining them to sealed anchor txs.

        GPU bundle offers anchor as GPU_REGISTER (payload.gpu_id) and software
        bundle offers as GPU_MARKET (payload.offer_id); the
        state-table endpoints (e.g. /rpc/gpus) do not expose the sealing
        block, so confirmation is derived from the sealed transaction itself.
        Anchors are namespaced per tx type — a GPU_REGISTER seal can never
        confirm a software offer — and bound to the offer's provider, so a tx
        from another sender can't take over or fake an anchor.

        Verified confirmations are stored (SoftwareService.block_* for local
        rows, OfferAnchor otherwise), so a fully-confirmed listing costs no
        chain RPCs; unconfirmed offers are re-probed at most once per
        ``_ANCHOR_NEGATIVE_TTL_SECONDS``. Mutates ``offers`` in place; RPC
        failure degrades to unconfirmed.
        """
        pending = [o for o in offers if not o.get("confirmed")]
        if not pending:
            return
        try:
            # Namespaced keys: the tx-type split applied live applies to
            # stored rows too, so a stored GPU_REGISTER seal can never
            # confirm a software offer.
            wanted: dict[str, tuple[dict[str, Any], bool, str]] = {}
            for offer in pending:
                is_gpu = offer.get("service_type") == "gpu_market"
                raw = offer.get("offer_id") or offer.get("plugin_id")
                if raw:
                    wanted[f"{'gpu' if is_gpu else 'offer'}:{raw}"] = (offer, is_gpu, str(raw))
            if not wanted:
                return

            rows = (
                (
                    await self.session.execute(
                        select(OfferAnchor).where(OfferAnchor.key.in_(list(wanted)))  # type: ignore[attr-defined]
                    )
                )
                .scalars()
                .all()
            )
            stored = {row.key: row for row in rows}
            live: dict[str, tuple[dict[str, Any], bool, str, str]] = {}
            for dbkey, (offer, is_gpu, raw) in wanted.items():
                binding = self._anchor_binding_key(offer, is_gpu)
                row = stored.get(dbkey)
                if row is not None and row.block_height is not None and row.bound_provider and row.bound_provider == binding:
                    offer["confirmed"] = True
                    offer["tx_hash"] = offer.get("tx_hash") or row.tx_hash or None
                    offer["block_height"] = row.block_height
                    offer["block_hash"] = offer.get("block_hash") or row.block_hash
                    offer["block_proposer"] = offer.get("block_proposer") or row.block_proposer
                    if row.block_timestamp and not offer.get("block_timestamp"):
                        offer["block_timestamp"] = row.block_timestamp
                    if row.registered_at and not offer.get("registered_at"):
                        offer["registered_at"] = row.registered_at
                else:
                    live[dbkey] = (offer, is_gpu, raw, binding)
            now = time.monotonic()
            self._evict_anchor_negatives(now)
            live = {k: v for k, v in live.items() if self._anchor_negatives.get((k, v[3]), 0.0) <= now}
            if not live:
                return

            # key -> anchor candidates, newest-first. Keeping every candidate
            # per key lets a skipped foreign tx fall through to the offer's
            # own older anchor instead of shadowing it.
            gpu_anchors: dict[str, list[dict[str, Any]]] = {}
            offer_anchors: dict[str, list[dict[str, Any]]] = {}
            for tx_type, anchors, field in (
                ("GPU_MARKET", offer_anchors, "offer_id"),
                ("GPU_REGISTER", gpu_anchors, "gpu_id"),
            ):
                for tx in await self._rpc_client.query_transactions(transaction_type=tx_type, chain_id=chain_id, limit=1000):
                    try:
                        key = (tx.get("payload") or {}).get(field)
                    except AttributeError:
                        continue  # malformed tx poisons only itself
                    if key:
                        anchors.setdefault(key, []).append(tx)
            changed = False
            for dbkey, (offer, is_gpu, raw, binding) in live.items():
                candidates = (gpu_anchors if is_gpu else offer_anchors).get(raw) or []
                anchor_tx = next(
                    (tx for tx in candidates if self._anchor_belongs_to_provider(tx, offer, is_gpu)),
                    None,
                )
                if anchor_tx is None:
                    self._remember_anchor_negative((dbkey, binding), now + _ANCHOR_NEGATIVE_TTL_SECONDS)
                    continue
                ts_str, ts_dt = self._anchor_timestamp(anchor_tx)
                offer["confirmed"] = True
                offer["tx_hash"] = offer.get("tx_hash") or anchor_tx.get("tx_hash")
                offer["block_height"] = anchor_tx.get("block_height")
                offer["block_hash"] = offer.get("block_hash") or anchor_tx.get("block_hash")
                offer["block_proposer"] = offer.get("block_proposer") or anchor_tx.get("block_proposer")
                if ts_str and not offer.get("block_timestamp"):
                    offer["block_timestamp"] = ts_str
                if not offer.get("registered_at"):
                    offer["registered_at"] = anchor_tx.get("created_at") or offer.get("block_timestamp")
                changed |= self._persist_anchor(dbkey, offer, is_gpu, anchor_tx, ts_dt, stored.get(dbkey), local_rows)
            if changed:
                await self.session.commit()
        except Exception as e:  # noqa: BLE001 - anchor resolution is best-effort enrichment
            logger.warning("Failed to resolve on-chain offer anchors: %s", e)

    async def get_software_service(self, plugin_id: str) -> dict[str, Any] | None:
        """Get a specific software service (local row or on-chain GPU offer)"""
        from sqlalchemy import select

        from ..domain.market import SoftwareService

        try:
            query = select(SoftwareService).where(SoftwareService.plugin_id == plugin_id)  # type: ignore[arg-type]
            result = await self.session.execute(query)
            service = result.scalar_one_or_none()
            data = _local_offer_dict(service) if service else None
            if data is None:
                # GPU bundle offers live only on-chain (GPURegistration state
                # table); fall back so /v1/market/offer/{gpu_id} resolves too.
                try:
                    gpu = await self._rpc_client.get_offer(plugin_id)
                except Exception:  # noqa: BLE001 - chain probe: unreachable RPC means no on-chain offer
                    gpu = None
                if gpu is not None:
                    # Same visibility rule as the list path (#1566): a GPU its
                    # registrant deactivated (or any non-"active" status) must
                    # not resolve as a bookable offer, and a row without a
                    # price cannot be priced — Decimal(str(None)) would 500.
                    gpu_status = gpu.get("status")
                    if (
                        (gpu_status is not None and gpu_status != _GPU_LISTING_DEFAULT_STATUS)
                        or gpu.get("price_per_hour") is None
                        # #1566: open allocations mean the GPU is spoken for —
                        # same visibility rule as the list path.
                        or int(gpu.get("active_allocations") or 0) > 0
                    ):
                        gpu = None
                if gpu:
                    data = _gpu_offer_to_service_dict(gpu, None, settings.hub_rpc_url)
            if data is None:
                return None
            local_rows = {service.plugin_id: service} if service else None
            await self._resolve_offer_anchors([data], None, local_rows)
            return data
        except Exception as e:
            logger.error("Error in get_software_service: %s: %s", type(e).__name__, str(e))
            raise

    async def register_software_service(self, data: dict[str, Any]) -> dict[str, Any]:
        """Register or update a software service"""
        from datetime import UTC, datetime

        from sqlalchemy import select

        from ..domain.market import SoftwareService

        try:
            plugin_id = data.get("plugin_id")
            if not plugin_id:
                # The signed message covers plugin_id, so a body without one
                # can never verify — reject plainly instead of deriving a key
                # the client did not sign.
                raise ValueError("plugin_id is required")
            # POST /v1/market/offer is public: the claimed provider_address
            # must prove itself with a fresh, chain-scoped signature before a
            # row is written — otherwise any caller could squat a provider's
            # plugin_id and inherit its anchors.
            data["plugin_id"] = plugin_id
            auth_error, signer = verify_offer_registration(data, settings.default_chain_id or resolve_chain_id())
            if auth_error:
                raise PermissionError(auth_error)
            # Ephemeral proof fields are not service columns.
            for ephemeral in ("signature", "issued_at", "chain_id"):
                data.pop(ephemeral, None)
            # Allow-list, not block-list: only provider-owned fields reach the
            # row. block_*/tx_hash come only from verified anchors, ratings and
            # timestamps only from the server — a signed registration can no
            # longer write its own confirmation or reputation.
            data = {key: value for key, value in data.items() if key in _REGISTRATION_FIELDS}
            query = select(SoftwareService).where(SoftwareService.plugin_id == plugin_id)
            result = await self.session.execute(query)
            existing = result.scalar_one_or_none()
            if existing:
                # Ownership gate (the GPU_REGISTER check one layer up): a
                # valid signature proves who is asking, not who owns the row.
                # Updating an existing offer requires the row's provider —
                # anyone else's valid signature gets 403, not a takeover.
                if not existing.provider_address:
                    raise PermissionError(f"offer {plugin_id} has no provider on record; updates are not permitted")
                if canonical_address(existing.provider_address) != canonical_address(signer or ""):
                    raise PermissionError(f"offer {plugin_id} belongs to provider {existing.provider_address}")
                data.pop("provider_address", None)  # ownership never changes via update
                for key, value in data.items():
                    if hasattr(existing, key) and value is not None:
                        setattr(existing, key, value)
                existing.updated_at = datetime.now(UTC).replace(tzinfo=None)
                await self.session.commit()
                await self.session.refresh(existing)
                logger.info("Updated software service: %s", plugin_id)
            else:
                data["plugin_id"] = plugin_id
                service = SoftwareService(**data)
                self.session.add(service)
                await self.session.commit()
                await self.session.refresh(service)
                existing = service
                logger.info("Registered software service: %s", plugin_id)
            return {
                "plugin_id": existing.plugin_id,
                "service_type": existing.service_type,
                "model": existing.model,
                "status": existing.status,
            }
        except PermissionError:
            raise
        except Exception as e:
            logger.error("Error in register_software_service: %s: %s", type(e).__name__, str(e))
            raise

    async def unregister_software_service(self, plugin_id: str, proof: dict[str, Any]) -> Any:
        """Unregister a software service.

        DELETE /v1/market/offer/{plugin_id} is public, and it used to delete
        any row for any caller; with the same plugin_id free again, anyone
        could register it under their own address and be resolved as the
        provider (the CLI trusts the row's provider_address and endpoint).
        Removal now needs the same proof registration does -- a fresh,
        chain-scoped signature -- scoped by ``action="unregister"`` so a
        captured registration cannot be replayed as a removal, plus the
        ownership gate: the signer must be the row's provider.
        """
        from sqlalchemy import select

        from ..domain.market import SoftwareService

        try:
            data = {
                "plugin_id": plugin_id,
                "provider_address": proof.get("provider_address"),
                "chain_id": proof.get("chain_id"),
                "issued_at": proof.get("issued_at"),
                "signature": proof.get("signature"),
            }
            auth_error, signer = verify_offer_registration(
                data, settings.default_chain_id or resolve_chain_id(), action="unregister"
            )
            if auth_error:
                raise PermissionError(auth_error)
            query = select(SoftwareService).where(SoftwareService.plugin_id == plugin_id)  # type: ignore[arg-type]
            result = await self.session.execute(query)
            service = result.scalar_one_or_none()
            if not service:
                # Raise rather than return an HTTP-shaped tuple: this is the service layer,
                # and the tuple was serialized by FastAPI as a 200 with the status buried in
                # a JSON array. Matches list_offers/update_offer_status above.
                raise ValueError(f"Service not found: {plugin_id}")
            if not service.provider_address:
                raise PermissionError(f"offer {plugin_id} has no provider on record; removal is not permitted")
            if canonical_address(service.provider_address) != canonical_address(signer or ""):
                raise PermissionError(f"offer {plugin_id} belongs to provider {service.provider_address}")
            await self.session.delete(service)
            await self.session.commit()
            logger.info("Unregistered software service: %s", plugin_id)
            return {"plugin_id": plugin_id, "status": "unregistered"}
        except PermissionError:
            raise
        except Exception as e:
            logger.error("Error in unregister_software_service: %s: %s", type(e).__name__, str(e))
            raise

    async def create_graph(self, graph_data: dict[str, Any]) -> dict[str, Any]:
        """Create a new knowledge graph"""
        from ..domain.market import KnowledgeGraph

        try:
            existing = await _get_by_caller_id(self.session, KnowledgeGraph, graph_data)
            if existing is not None:
                return {"id": existing.id, "name": existing.name, "status": existing.status, "deduplicated": True}
            graph = KnowledgeGraph(**graph_data)
            self.session.add(graph)
            try:
                await self.session.commit()
            except IntegrityError:
                replay = await _replay_after_integrity_conflict(self.session, KnowledgeGraph, graph_data)
                if replay is not None:
                    return {"id": replay.id, "name": replay.name, "status": replay.status, "deduplicated": True}
                raise
            await self.session.refresh(graph)
            logger.info("Created graph with id: %s", graph.id)
            return {"id": graph.id, "name": graph.name, "status": graph.status}
        except Exception as e:
            await self.session.rollback()
            logger.error("Error in create_graph: %s: %s", type(e).__name__, str(e))
            raise

    async def add_node(self, node_data: dict[str, Any]) -> dict[str, Any]:
        """Add a node to a knowledge graph"""
        from ..domain.market import GraphNode

        try:
            existing = await _get_by_caller_id(self.session, GraphNode, node_data)
            if existing is not None:
                return {
                    "id": existing.id,
                    "graph_id": existing.graph_id,
                    "label": existing.label,
                    "deduplicated": True,
                }
            node = GraphNode(**node_data)
            self.session.add(node)
            try:
                await self.session.commit()
            except IntegrityError:
                replay = await _replay_after_integrity_conflict(self.session, GraphNode, node_data)
                if replay is not None:
                    return {
                        "id": replay.id,
                        "graph_id": replay.graph_id,
                        "label": replay.label,
                        "deduplicated": True,
                    }
                raise
            await self.session.refresh(node)
            logger.info("Added node with id: %s to graph: %s", node.id, node.graph_id)
            return {"id": node.id, "graph_id": node.graph_id, "label": node.label}
        except Exception as e:
            await self.session.rollback()
            logger.error("Error in add_node: %s: %s", type(e).__name__, str(e))
            raise

    async def add_edge(self, edge_data: dict[str, Any]) -> dict[str, Any]:
        """Add an edge to a knowledge graph"""
        from ..domain.market import GraphEdge

        try:
            existing = await _get_by_caller_id(self.session, GraphEdge, edge_data)
            if existing is not None:
                return {
                    "id": existing.id,
                    "graph_id": existing.graph_id,
                    "source_node_id": existing.source_node_id,
                    "target_node_id": existing.target_node_id,
                    "deduplicated": True,
                }
            edge = GraphEdge(**edge_data)
            self.session.add(edge)
            try:
                await self.session.commit()
            except IntegrityError:
                replay = await _replay_after_integrity_conflict(self.session, GraphEdge, edge_data)
                if replay is not None:
                    return {
                        "id": replay.id,
                        "graph_id": replay.graph_id,
                        "source_node_id": replay.source_node_id,
                        "target_node_id": replay.target_node_id,
                        "deduplicated": True,
                    }
                raise
            await self.session.refresh(edge)
            logger.info("Added edge with id: %s to graph: %s", edge.id, edge.graph_id)
            return {
                "id": edge.id,
                "graph_id": edge.graph_id,
                "source_node_id": edge.source_node_id,
                "target_node_id": edge.target_node_id,
            }
        except Exception as e:
            await self.session.rollback()
            logger.error("Error in add_edge: %s: %s", type(e).__name__, str(e))
            raise

    async def query_graph(self, graph_id: str) -> dict[str, Any]:
        """Query a knowledge graph (get all nodes and edges)"""
        from sqlalchemy import select

        from ..domain.market import GraphEdge, GraphNode

        try:
            node_stmt = (
                select(GraphNode)
                .where(GraphNode.graph_id == graph_id)  # type: ignore[arg-type]
                .limit(max_page_size())
            )
            node_result = await self.session.execute(node_stmt)
            nodes = node_result.scalars().all()
            edge_stmt = (
                select(GraphEdge)
                .where(GraphEdge.graph_id == graph_id)  # type: ignore[arg-type]
                .limit(max_page_size())
            )
            edge_result = await self.session.execute(edge_stmt)
            edges = edge_result.scalars().all()
            return {
                "graph_id": graph_id,
                "nodes": [{"id": n.id, "node_type": n.node_type, "label": n.label, "properties": n.properties} for n in nodes],
                "edges": [
                    {
                        "id": e.id,
                        "source_node_id": e.source_node_id,
                        "target_node_id": e.target_node_id,
                        "edge_type": e.edge_type,
                        "weight": e.weight,
                        "properties": e.properties,
                    }
                    for e in edges
                ],
            }
        except Exception as e:
            logger.error("Error in query_graph: %s: %s", type(e).__name__, str(e))
            raise

    async def _create_bid(self, offer_id: str, booking_data: dict[str, Any], offer: MarketOffer) -> Bid:
        """Create and persist a bid record for a market offer booking."""
        from sqlmodel import col

        try:
            # A buyer identity is mandatory (#816): 'unknown' can never match
            # an on-chain sender in complete_bid, which stranded the offer.
            buyer = booking_data.get("wallet") or booking_data.get("buyer")
            if not buyer:
                raise ValueError("booking requires a buyer identity (wallet or buyer)")
            # #1553: booking commits the bid before the offer flips to
            # "booked" — a crash or concurrent retry in that window must
            # replay the pending bid this buyer already holds, not stack a
            # second bid (each booking can spawn its own escrow).
            existing = (
                (await self.session.execute(select(Bid).where(col(Bid.offer_id) == offer_id, col(Bid.status) == "pending")))
                .scalars()
                .all()
            )
            canonical_buyer = self._canonical_address(str(buyer))
            for pending in existing:
                if self._canonical_address(str(pending.buyer)) == canonical_buyer:
                    logger.info("Replaying existing pending bid %s for offer %s buyer %s", pending.id, offer_id, buyer)
                    return pending
            # Same bounds as the job payment path (#1634): an unbounded or
            # negative price is worse here — complete_bid only enforces
            # tx_value >= ait_to_units(bid.price) when that value is positive,
            # so a negative/NaN price skips the on-chain minimum entirely and
            # a "completed" bid settles for dust.
            price = _money_decimal(booking_data.get("price", offer.price or 0), "price")
            capacity = float(booking_data.get("duration_hours", 1.0))
            bid = Bid(
                offer_id=offer_id,
                provider=offer.provider or "unknown",
                buyer=buyer,
                capacity=capacity,
                price=price,
                status="pending",
                # #1554: pending bids expire — the sweeper flips them and the
                # offer reservation TTL releases the hold.
                expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(seconds=bid_ttl_seconds()),
            )
            self.session.add(bid)
            await self.session.commit()
            # commit() expires ORM attrs; refresh before touching bid.id (#820)
            await self.session.refresh(bid)
            logger.info("Created bid %s for offer %s", bid.id, offer_id)
            return bid
        except Exception as e:
            logger.error("Error in _create_bid: %s: %s", type(e).__name__, str(e))
            raise

    def get_current_timestamp(self) -> int:
        """Get current Unix timestamp"""
        return int(time.time())

    # Job states that prove a paid interaction completed — a rating is only
    # accepted from a reviewer who reached one of these with this service.
    _RATING_PROVEN_STATES = frozenset({"RELEASED", "COMPLETED"})

    async def _require_local_rating_binding(self, service_id: str, service: dict[str, Any] | None, reviewer_id: str) -> None:
        """Bind a locally-submitted rating to a real counterparty interaction (#1584).

        ``reviewer_id`` is caller-supplied, so without a check any caller
        could stuff a service's rating or bomb it with fake reviews. A local
        rating now requires the reviewer to be an address that completed a
        job or bid for this service, one rating per reviewer per service,
        and never the provider rating its own service. Remote-synced ratings
        keep their peer-trust model (cross-node proof is a separate problem).
        """
        from sqlalchemy import or_, select
        from sqlmodel import col

        reviewer = self._canonical_address(reviewer_id)
        provider = self._canonical_address(str((service or {}).get("provider_address") or ""))
        if provider and reviewer == provider:
            raise ValueError("Service provider cannot rate its own service")

        # One rating per reviewer per service — compare canonically so case or
        # whitespace variants of the same address cannot bypass it.
        existing_rows = (
            (await self.session.execute(select(ServiceRating).where(col(ServiceRating.service_id) == service_id)))
            .scalars()
            .all()
        )
        if any(self._canonical_address(str(r.reviewer_id)) == reviewer for r in existing_rows):
            raise ValueError("Reviewer has already rated this service")

        service = service or {}
        keys = {k for k in {service_id, service.get("plugin_id"), service.get("offer_id")} if k}

        def _buyer_proven(buyer: Any, state: str | None, completed_states: frozenset[str]) -> bool:
            return bool(buyer) and state in completed_states and self._canonical_address(str(buyer)) == reviewer

        job_rows = (
            (
                await self.session.execute(
                    select(MarketJob)
                    .where(or_(col(MarketJob.offer_id).in_(keys), col(MarketJob.plugin_id).in_(keys)))
                    .where(col(MarketJob.buyer_address).isnot(None))
                    .limit(200)
                )
            )
            .scalars()
            .all()
        )
        for job in job_rows:
            if _buyer_proven(job.buyer_address, job.state, self._RATING_PROVEN_STATES):
                return
        bid_rows = (
            (
                await self.session.execute(
                    select(Bid).where(col(Bid.offer_id).in_(keys), col(Bid.status) == "completed").limit(200)
                )
            )
            .scalars()
            .all()
        )
        for bid in bid_rows:
            if _buyer_proven(bid.buyer, bid.status, frozenset({"completed"})):
                return
        raise ValueError("reviewer_id has no completed job or bid for this service")

    async def add_service_rating(
        self,
        service_id: str,
        rating: float,
        reviewer_id: str,
        comment: str = "",
        source_node: str = "local",
        service: dict[str, Any] | None = None,
    ) -> ServiceRating:
        """Add a service rating and update service average rating"""
        try:
            if not 1.0 <= rating <= 5.0:
                raise ValueError("Rating must be between 1.0 and 5.0")
            if source_node == "local":
                if service is None:
                    service = await self.get_software_service(service_id) or await self.get_service_by_offer_id(service_id)
                if service is None:
                    raise ValueError(f"Service not found: {service_id}")
                await self._require_local_rating_binding(service_id, service, reviewer_id)
            service_rating = ServiceRating(
                service_id=service_id, rating=rating, reviewer_id=reviewer_id, comment=comment, source_node=source_node
            )
            self.session.add(service_rating)
            await self.session.commit()
            await self.session.refresh(service_rating)
            logger.info("Added rating %s for service %s by reviewer %s from %s", rating, service_id, reviewer_id, source_node)
            await self._update_service_rating(service_id)
            return service_rating
        except Exception as e:
            logger.error("Error in add_service_rating: %s: %s", type(e).__name__, str(e))
            raise

    async def get_service_ratings(self, service_id: str, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        """Get ratings for a specific service"""
        try:
            from sqlalchemy import select

            # Caller limits are clamped to the server page ceiling — a
            # negative or huge ?limit= must not become an unbounded read (#1543).
            limit = min(max(int(limit), 1), max_page_size())
            offset = max(int(offset), 0)
            stmt = select(ServiceRating).where(ServiceRating.service_id == service_id)  # type: ignore[arg-type]
            stmt = stmt.order_by(ServiceRating.created_at.desc())  # type: ignore[attr-defined]
            stmt = stmt.limit(limit).offset(offset)
            result = await self.session.execute(stmt)
            ratings = result.scalars().all()
            return [
                {
                    "id": r.id,
                    "service_id": r.service_id,
                    "rating": r.rating,
                    "reviewer_id": r.reviewer_id,
                    "comment": r.comment,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "source_node": r.source_node,
                }
                for r in ratings
            ]
        except Exception as e:
            logger.error("Error in get_service_ratings: %s: %s", type(e).__name__, str(e))
            raise

    async def get_unsynced_ratings(self, limit: int = 100) -> list[dict[str, Any]]:
        """Get ratings that haven't been synced yet"""
        try:
            from sqlalchemy import select

            # Same ceiling as the sibling list paths — ?limit= was unchecked (#1543).
            limit = min(max(int(limit), 1), max_page_size())
            stmt = (
                select(ServiceRating)
                .where(ServiceRating.synced_at.is_(None))  # type: ignore[union-attr]
                .limit(limit)
            )
            result = await self.session.execute(stmt)
            ratings = result.scalars().all()
            return [
                {
                    "id": r.id,
                    "service_id": r.service_id,
                    "rating": r.rating,
                    "reviewer_id": r.reviewer_id,
                    "comment": r.comment,
                    "created_at": r.created_at.isoformat(),
                    "source_node": r.source_node,
                }
                for r in ratings
            ]
        except Exception as e:
            logger.error("Error in get_unsynced_ratings: %s: %s", type(e).__name__, str(e))
            raise

    async def mark_ratings_synced(self, rating_ids: list[str]) -> int:
        """Mark ratings as synced"""
        try:
            from datetime import UTC, datetime

            from sqlalchemy import select

            stmt = select(ServiceRating).where(ServiceRating.id.in_(rating_ids))  # type: ignore[attr-defined]
            result = await self.session.execute(stmt)
            ratings = result.scalars().all()
            for rating in ratings:
                rating.synced_at = datetime.now(UTC).replace(tzinfo=None)
            await self.session.commit()
            logger.info("Marked %s ratings as synced", len(ratings))
            return len(ratings)
        except Exception as e:
            logger.error("Error in mark_ratings_synced: %s: %s", type(e).__name__, str(e))
            raise

    async def sync_ratings_from_remote(self, remote_ratings: list[dict[str, Any]]) -> dict[str, Any]:
        """Sync ratings from remote node"""
        try:
            from datetime import UTC, datetime

            from sqlalchemy import func, select

            synced_count = 0
            updated_count = 0
            skipped_count = 0
            failed_count = 0
            touched_services: set[str] = set()
            # Bound the batch like every other list path (#1634) — the route
            # is API-key gated but the payload size was caller-controlled.
            batch = remote_ratings[: max_page_size()]
            if len(remote_ratings) > len(batch):
                logger.warning("ratings/sync batch truncated to %s rows", len(batch))
            for remote_rating in batch:
                try:
                    # Same 1-5 range the local submit path enforces — a
                    # malformed peer payload must not poison avg_rating (#1446).
                    rating_value = float(remote_rating["rating"])
                    if not 1.0 <= rating_value <= 5.0:
                        raise ValueError(f"rating out of range: {remote_rating['rating']!r}")
                    remote_created = _rating_created_at(remote_rating["created_at"])
                    rating_value = _coerce_remote_rating(remote_rating["rating"])
                    # Dedup case-insensitively: "0xAbC" and "0xabc" are the
                    # same reviewer and must not become two ratings (#1634).
                    stmt = select(ServiceRating).where(
                        ServiceRating.service_id == remote_rating["service_id"],
                        func.lower(ServiceRating.reviewer_id) == str(remote_rating["reviewer_id"]).strip().lower(),
                    )
                    result = await self.session.execute(stmt)
                    existing = result.scalar_one_or_none()
                    if existing:
                        if remote_created > existing.created_at:
                            existing.rating = rating_value
                            existing.comment = remote_rating["comment"]
                            existing.synced_at = datetime.now(UTC).replace(tzinfo=None)
                            updated_count += 1
                        else:
                            skipped_count += 1
                    else:
                        new_rating = ServiceRating(
                            id=remote_rating["id"],
                            service_id=remote_rating["service_id"],
                            rating=rating_value,
                            reviewer_id=remote_rating["reviewer_id"],
                            comment=remote_rating["comment"],
                            created_at=remote_created,
                            synced_at=datetime.now(UTC).replace(tzinfo=None),
                            # source_node is caller-supplied provenance —
                            # sanitize it rather than trusting the raw value
                            # (#1634).
                            source_node=str(remote_rating.get("source_node") or "remote").strip()[:128] or "remote",
                        )
                        self.session.add(new_rating)
                        synced_count += 1
                    touched_services.add(remote_rating["service_id"])
                except Exception as e:
                    failed_count += 1
                    logger.warning("Skipping malformed remote rating %s: %s", remote_rating.get("id", "?"), e)
            await self.session.commit()
            logger.info(
                "Synced %s new, updated %s, skipped %s, failed %s ratings",
                synced_count,
                updated_count,
                skipped_count,
                failed_count,
            )
            for service_id in touched_services:
                await self._update_service_rating(service_id)
            return {
                "synced": synced_count,
                "updated": updated_count,
                "skipped": skipped_count,
                "failed": failed_count,
            }
        except Exception as e:
            logger.error("Error in sync_ratings_from_remote: %s: %s", type(e).__name__, str(e))
            raise

    async def _update_service_rating(self, service_id: str) -> None:
        """Calculate and update service average rating"""
        try:
            from sqlalchemy import func, select

            stmt = select(func.avg(ServiceRating.rating), func.count(ServiceRating.id))  # type: ignore[arg-type]
            stmt = stmt.where(ServiceRating.service_id == service_id)  # type: ignore[arg-type]
            result = await self.session.execute(stmt)
            avg_rating, count = result.first()
            service_stmt = select(SoftwareService).where(SoftwareService.plugin_id == service_id)  # type: ignore[arg-type]
            service_result = await self.session.execute(service_stmt)
            service = service_result.scalar_one_or_none()
            if not service:
                service_stmt = select(SoftwareService).where(SoftwareService.offer_id == service_id)  # type: ignore[arg-type]
                service_result = await self.session.execute(service_stmt)
                service = service_result.scalar_one_or_none()
            if service:
                service.avg_rating = float(avg_rating) if avg_rating else 0.0
                service.rating_count = int(count) if count else 0
                await self.session.commit()
                logger.info(
                    "Updated service %s rating: avg=%s, count=%s", service_id, service.avg_rating, service.rating_count
                )
        except Exception as e:
            logger.error("Error in _update_service_rating: %s: %s", type(e).__name__, str(e))
            raise

    def _canonical_address(self, address: str) -> str:
        """Return the canonical 0x spelling for address comparison.

        The chain stores EIP-55 secp256k1/EVM addresses, so comparing the
        canonical `0x` form produced by :func:`canonical_address` removes
        formatting differences without accepting legacy `ait1`/`aitbc1` spellings.
        """
        return canonical_address(address or "")

    async def complete_bid(
        self,
        bid_id: str,
        tx_hash: str,
        chain_id: str | None = None,
    ) -> dict[str, Any]:
        """Complete a market bid after confirming the on-chain payment."""
        try:
            logger.info("complete_bid called with bid_id=%s, tx_hash=%s", bid_id, tx_hash)
            stmt = select(Bid).where(Bid.id == bid_id)
            result = (await self.session.execute(stmt)).first()
            bid = result[0] if result else None
            if not bid:
                raise ValueError(f"Bid not found: {bid_id}")

            offer = await self.get_offer(bid.offer_id)
            if not offer:
                raise ValueError(f"Offer not found: {bid.offer_id}")
            offer_id = offer.id  # read pre-commit; later commits expire it (#820)

            if bid.status == "completed":
                return {
                    "bid_id": bid_id,
                    "offer_id": offer.id,
                    "tx_hash": tx_hash,
                    "status": "completed",
                    "message": "Bid already completed",
                }

            # #1554: a pending bid past its TTL can no longer be paid — expire
            # it here so a late tx_hash cannot complete a stale booking (the
            # sweeper also expires these on its interval).
            if bid.status == "pending" and bid.expires_at is not None:
                expires_at = bid.expires_at
                if expires_at.tzinfo is not None:
                    expires_at = expires_at.replace(tzinfo=None)
                if expires_at < datetime.now(UTC).replace(tzinfo=None):
                    bid.status = "expired"
                    self.session.add(bid)
                    await self.session.commit()
                    raise ValueError(f"Bid {bid_id} has expired")

            # Spent-hash check (#817): the tx must not already settle another
            # bid — verification proves payment, not that it was paid for THIS
            # bid, so the hash is recorded on completion and reuse refused.
            stmt = select(Bid).where(Bid.tx_hash == tx_hash)
            spent = (await self.session.execute(stmt)).scalars().first()
            if spent is not None and spent.id != bid_id:
                raise ValueError(f"Transaction {tx_hash} already settled bid {spent.id}")

            resolved_chain_id = chain_id or settings.default_chain_id or resolve_chain_id()
            tx = await self._rpc_client.get_transaction(tx_hash, chain_id=resolved_chain_id)
            self._verify_bid_payment_tx(bid, offer, tx, tx_hash, resolved_chain_id)

            bid.status = "completed"
            bid.tx_hash = tx_hash
            self.session.add(bid)

            # Transition offer reserved -> in_use -> delisted (closed/sold)
            current = to_offer_status(offer.status)
            fsm1 = OfferFSM(current)
            fsm1.transition(OfferStatus.IN_USE)
            offer.status = "in_use"
            self.session.add(offer)
            await self.session.commit()

            fsm2 = OfferFSM(OfferStatus.IN_USE)
            fsm2.transition(OfferStatus.DELISTED)
            offer.status = "delisted"
            self.session.add(offer)
            await self.session.commit()

            logger.info("Bid %s completed; offer %s delisted", bid_id, offer_id)
            return {
                "bid_id": bid_id,
                "offer_id": offer_id,
                "tx_hash": tx_hash,
                "status": "completed",
                "message": "Bid completed successfully",
            }
        except ValueError:
            raise
        except Exception as e:
            logger.error("Error in complete_bid: %s: %s", type(e).__name__, str(e))
            raise

    def _verify_bid_payment_tx(
        self,
        bid: Any,
        offer: Any,
        tx: dict[str, Any] | None,
        tx_hash: str,
        resolved_chain_id: str,
    ) -> None:
        """Raise ValueError unless the tx confirms the bid payment to the provider."""
        if not tx:
            raise ValueError(f"Transaction {tx_hash} not found on chain {resolved_chain_id}")
        if tx.get("status") != "confirmed":
            raise ValueError(f"Transaction {tx_hash} is not confirmed")

        tx_sender = self._canonical_address(str(tx.get("sender", "")))
        tx_recipient = self._canonical_address(str(tx.get("recipient", "")))
        expected_sender = self._canonical_address(bid.buyer)
        expected_recipient = self._canonical_address(offer.provider or "")

        if expected_sender and tx_sender != expected_sender:
            raise ValueError(f"Transaction sender {tx_sender} does not match buyer {expected_sender}")
        if expected_recipient and tx_recipient != expected_recipient:
            raise ValueError(f"Transaction recipient {tx_recipient} does not match provider {expected_recipient}")

        # price is stored in AIT; on-chain value is in compute-units (1 AIT = 36_000_000)
        required_value = ait_to_units(bid.price)
        tx_value = int(tx.get("value", 0) or 0)
        if required_value > 0 and tx_value < required_value:
            raise ValueError(f"Transaction value {tx_value} compute-units is less than required {required_value}")

    async def get_service_by_offer_id(self, offer_id: str) -> dict[str, Any] | None:
        """Get a software service by offer_id"""
        from sqlalchemy import select

        try:
            stmt = select(SoftwareService).where(SoftwareService.offer_id == offer_id)  # type: ignore[arg-type]
            result = await self.session.execute(stmt)
            service = result.scalar_one_or_none()
            if not service:
                return None
            return {
                "plugin_id": service.plugin_id,
                "service_type": service.service_type,
                "model": service.model,
                "price": str(service.price),
                "price_unit": service.price_unit,
                "offer_id": service.offer_id,
                "endpoint": service.endpoint,
                "public_endpoint": service.public_endpoint,
                "health_url": service.health_url,
                "provider_address": service.provider_address,
                "node_id": service.node_id,
                "gpu_name": service.gpu_name,
                "gpu_device": service.gpu_device,
                "gpu_uuid": service.gpu_uuid,
                "gpu_offer_id": service.gpu_offer_id,
                "gpu_model": service.gpu_model,
                "gpu_memory_gb": service.gpu_memory_gb,
                "compute_capability": service.compute_capability,
                "description": service.description,
                "status": service.status,
                "registered_at": service.registered_at.isoformat() if service.registered_at else None,
                "updated_at": service.updated_at.isoformat() if service.updated_at else None,
                "avg_rating": service.avg_rating,
                "rating_count": service.rating_count,
            }
        except Exception as e:
            logger.error("Error in get_service_by_offer_id: %s: %s", type(e).__name__, str(e))
            raise

    def _parse_iso_dt(self, value: Any) -> Any:
        """Parse an ISO 8601 datetime string into a naive UTC datetime."""
        from datetime import UTC, datetime

        if value is None:
            return None
        if isinstance(value, datetime):
            if value.tzinfo is not None:
                # Convert aware datetimes to naive UTC for consistent storage.
                return value.astimezone(UTC).replace(tzinfo=None)
            return value
        if isinstance(value, str):
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is not None:
                parsed = parsed.astimezone(UTC).replace(tzinfo=None)
            return parsed
        raise ValueError(f"Invalid datetime value: {value!r}")

    async def register_ipfs_rental_token(self, data: dict[str, Any]) -> dict[str, Any]:
        """Register an access token for a paid IPFS rental."""
        from datetime import UTC, datetime

        from sqlalchemy import select

        from ..domain.market import IpfsRentalToken

        try:
            access_key = data.get("access_key")
            if not access_key:
                raise ValueError("access_key is required")

            # Store only the digest — a DB leak must not hand out working credentials.
            if data.get("access_secret") and not is_hashed_secret(data["access_secret"]):
                data["access_secret"] = hash_access_secret(data["access_secret"])

            # v0.25.x: canonicalize secp256k1/EVM addresses at registration so
            # the market DB always stores 0x EIP-55 addresses, regardless
            # of what the CLI or offer data sent.
            for addr_field in ("buyer_address", "provider_address"):
                if addr_field in data and data[addr_field]:
                    data[addr_field] = canonical_address(str(data[addr_field]))

            # A token is only registered after the provider successfully pins the CID.
            # Default to pinned=True so that normal rentals pay the provider at expiration.
            data["pinned"] = bool(data.get("pinned", True))

            # Normalize string timestamps into datetime objects for SQLite.
            for field in ("created_at", "updated_at", "expires_at"):
                if field in data:
                    data[field] = self._parse_iso_dt(data[field])

            # Column allowlist: settlement state (status, pinned, expires_at,
            # tx_hash, timestamps) is service-owned — a caller writing it could
            # steer the rental sweeper at a victim escrow (#815).
            _TOKEN_WRITABLE = {
                "access_key",
                "access_secret",
                "rental_id",
                "offer_id",
                "cid",
                "buyer_address",
                "provider_address",
                "ipfs_api",
                "public_endpoint",
                "disk_quota_mb",
                "size",
            }
            data = {k: v for k, v in data.items() if k in _TOKEN_WRITABLE}

            stmt = select(IpfsRentalToken).where(IpfsRentalToken.access_key == access_key)
            result = await self.session.execute(stmt)
            existing = result.scalar_one_or_none()
            if existing:
                for k, v in data.items():
                    if k in {"access_key", "rental_id"} or v is None:
                        continue
                    setattr(existing, k, v)
                existing.updated_at = datetime.now(UTC).replace(tzinfo=None)
                await self.session.commit()
                await self.session.refresh(existing)
                logger.info("Updated IPFS rental token: %s", access_key)
                return self._ipfs_token_to_dict(existing)
            token = IpfsRentalToken(**data)
            if not token.created_at:
                token.created_at = datetime.now(UTC).replace(tzinfo=None)
            if not token.updated_at:
                token.updated_at = datetime.now(UTC).replace(tzinfo=None)
            self.session.add(token)
            await self.session.commit()
            await self.session.refresh(token)
            logger.info("Registered IPFS rental token: %s", access_key)
            return self._ipfs_token_to_dict(token)
        except ValueError:
            raise
        except Exception as e:
            logger.error("Error in register_ipfs_rental_token: %s: %s", type(e).__name__, str(e))
            raise

    async def get_ipfs_rental_token(self, access_key: str, access_secret: str) -> dict[str, Any] | None:
        """Validate an IPFS rental token and return its details."""
        from datetime import UTC, datetime

        from sqlalchemy import select

        from ..domain.market import IpfsRentalToken

        try:
            stmt = select(IpfsRentalToken).where(IpfsRentalToken.access_key == access_key)  # type: ignore[arg-type]
            result = await self.session.execute(stmt)
            token = result.scalar_one_or_none()
            if not token:
                return None
            if not _secret_matches(token.access_secret, access_secret):
                return None
            if token.status != "active":
                return None
            # Compare naive UTC datetimes; SQLite returns naive values.
            if token.expires_at and token.expires_at < datetime.now(UTC).replace(tzinfo=None):
                token.status = "expired"
                await self.session.commit()
                return None
            return self._ipfs_token_to_dict(token)
        except Exception as e:
            logger.error("Error in get_ipfs_rental_token: %s: %s", type(e).__name__, str(e))
            raise

    def _ipfs_token_to_dict(self, token: Any) -> dict[str, Any]:
        """Serialize an IpfsRentalToken."""
        return {
            "access_key": token.access_key,
            "rental_id": token.rental_id,
            "offer_id": token.offer_id,
            "cid": token.cid,
            "buyer_address": token.buyer_address,
            "provider_address": token.provider_address,
            "escrow_contract_id": token.escrow_contract_id,
            "ipfs_api": token.ipfs_api,
            "public_endpoint": token.public_endpoint,
            "disk_quota_mb": token.disk_quota_mb,
            "size": token.size,
            "pinned": token.pinned,
            "status": token.status,
            "tx_hash": token.tx_hash,
            "created_at": token.created_at.isoformat() if token.created_at else None,
            "expires_at": token.expires_at.isoformat() if token.expires_at else None,
        }

    # -------------------------------------------------------------------------
    # MarketJob / MarketJobPayment (v0.25.7 first-class IPFS)
    # -------------------------------------------------------------------------

    def _job_to_dict(self, job: MarketJob) -> dict[str, Any]:
        """Serialize a MarketJob."""
        return {
            "job_id": job.id,
            "client_id": job.client_id,
            "client_ref": job.client_ref,
            "offer_id": job.offer_id,
            "plugin_id": job.plugin_id,
            "service_type": job.service_type,
            "model": job.model,
            "buyer_address": job.buyer_address,
            "provider_address": job.provider_address,
            "state": job.state,
            "payload": job.payload,
            "constraints": job.constraints,
            "ttl_seconds": job.ttl_seconds,
            "requested_at": _isoformat(job.requested_at),
            "expires_at": _isoformat(job.expires_at),
            "completed_at": _isoformat(job.completed_at),
            "error": job.error,
            "result": job.result,
            "receipt": job.receipt,
            "access_key": job.access_key,
            "payment_id": job.payment_id,
            "payment_status": job.payment_status,
            "payment_amount": str(job.payment_amount) if job.payment_amount is not None else None,
            "payment_token": job.payment_token,
            "escrow_contract_id": job.escrow_contract_id,
            "tx_hash": job.tx_hash,
            "refund_tx_hash": job.refund_tx_hash,
            "disputed_at": _isoformat(job.disputed_at),
            "dispute_reason": job.dispute_reason,
            "dispute_cleared_at": _isoformat(job.dispute_cleared_at),
            "created_at": _isoformat(job.created_at),
            "updated_at": _isoformat(job.updated_at),
        }

    def _payment_to_dict(self, payment: MarketJobPayment) -> dict[str, Any]:
        """Serialize a MarketJobPayment."""
        return {
            "payment_id": payment.id,
            "job_id": payment.job_id,
            "amount": str(payment.amount),
            "currency": payment.currency,
            "status": payment.status,
            "payment_method": payment.payment_method,
            "escrow_address": payment.escrow_address,
            "refund_address": payment.refund_address,
            "transaction_hash": payment.transaction_hash,
            "refund_transaction_hash": payment.refund_transaction_hash,
            "created_at": _isoformat(payment.created_at),
            "updated_at": _isoformat(payment.updated_at),
            "escrowed_at": _isoformat(payment.escrowed_at),
            "released_at": _isoformat(payment.released_at),
            "refunded_at": _isoformat(payment.refunded_at),
            "expires_at": _isoformat(payment.expires_at),
            "meta_data": payment.meta_data,
        }

    # Reuse _parse_iso_dt from the IPFS rental token helpers above.

    async def _require_known_offer(self, offer_id: str) -> None:
        """#1564: a job may only reference an offer the market actually lists.

        Resolution mirrors what buyers see in ``list_software_services``: a
        local ``SoftwareService`` row matched on its live ``offer_id`` or
        ``plugin_id``, else an on-chain GPU offer via ``GET /rpc/gpu/info/{id}``.
        Anything else raises — previously ``create_market_job`` persisted any
        caller-supplied ``offer_id`` unchecked.
        """
        from ..domain.market import SoftwareService

        stmt = select(SoftwareService).where((SoftwareService.offer_id == offer_id) | (SoftwareService.plugin_id == offer_id))
        if (await self.session.execute(stmt)).scalars().first() is not None:
            return
        # On-chain fallbacks, same sources the listing merges: a GPU offer by
        # id, then a software offer anchored as a sealed GPU_MARKET tx whose
        # payload carries this offer_id.
        try:
            if await self._rpc_client.get_offer(offer_id):
                return
        except Exception as e:
            logger.warning("GPU offer lookup for %s failed on chain RPC: %s", offer_id, e)
        try:
            txs = await self._rpc_client.query_transactions(transaction_type="GPU_MARKET", order_id=offer_id, limit=1)
            if txs:
                return
        except Exception as e:
            logger.warning("GPU_MARKET anchor lookup for %s failed on chain RPC: %s", offer_id, e)
        raise ValueError(f"Unknown offer_id: {offer_id}")

    async def create_market_job(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a MarketJob and MarketJobPayment for a software job."""
        try:
            # Canonicalize addresses at creation so the DB always stores 0x EIP-55.
            for addr_field in ("buyer_address", "provider_address"):
                if data.get(addr_field):
                    data[addr_field] = canonical_address(str(data[addr_field]))

            job_id = data.get("id") or uuid4().hex
            if not job_id:
                raise ValueError("job_id is required")

            # #1553/#1634: a caller-supplied job id is a natural idempotency
            # key for clients that do not use client_ref — a retry replays the
            # existing row instead of dying on the PK. The replay is scoped to
            # the same buyer/client so one tenant cannot probe another's job
            # id; an id held by a different party is a conflict, not a replay.
            if data.get("id"):
                existing = await self.session.get(MarketJob, job_id)
                if existing is not None:
                    same_buyer = bool(data.get("buyer_address")) and existing.buyer_address == data.get("buyer_address")
                    same_client = bool(data.get("client_id")) and existing.client_id == data.get("client_id")
                    if not (same_buyer or same_client):
                        raise ValueError(f"Job id already exists: {job_id}")
                    logger.info("Replaying existing market job %s (caller-supplied id)", existing.id)
                    payment = await self.session.get(MarketJobPayment, existing.payment_id) if existing.payment_id else None
                    return {
                        **self._job_to_dict(existing),
                        "payment": self._payment_to_dict(payment) if payment else None,
                        "deduplicated": True,
                    }

            # #1553: client_ref is the caller's idempotency handle — a retry
            # of the same creation must replay the in-flight job, not stack a
            # duplicate MarketJob+MarketJobPayment pair. Scoped to the buyer
            # (or client_id when no buyer address is given) so two customers
            # may reuse the same ref string. Only QUEUED/RUNNING jobs replay:
            # a finished job under the same ref is a new job, not a retry.
            client_ref = data.get("client_ref")
            if client_ref:
                replay = await self._find_inflight_job_by_client_ref(str(client_ref), data)
                if replay is not None:
                    logger.info("Replaying existing market job %s for client_ref %s", replay.id, client_ref)
                    payment = await self.session.get(MarketJobPayment, replay.payment_id) if replay.payment_id else None
                    return {
                        **self._job_to_dict(replay),
                        "payment": self._payment_to_dict(payment) if payment else None,
                        "deduplicated": True,
                    }

            # #1564: a job may only reference an offer the market actually
            # lists — the old code persisted any caller-supplied offer_id.
            offer_id = data.get("offer_id")
            if offer_id:
                await self._require_known_offer(str(offer_id))

            # #1673: bound ttl_seconds before it reaches timedelta() below —
            # 1e18 used to OverflowError into a 500.
            if data.get("ttl_seconds") is not None:
                data["ttl_seconds"] = _validated_job_ttl(data["ttl_seconds"])

            # Normalize timestamps
            for field in ("requested_at", "expires_at", "created_at", "updated_at"):
                if field in data:
                    data[field] = self._parse_iso_dt(data[field])

            # Store only the digest of the payload access secret.
            payload = data.get("payload")
            if isinstance(payload, dict):
                secret = payload.get("access_secret")
                if secret and not is_hashed_secret(secret):
                    payload["access_secret"] = hash_access_secret(secret)

            # Column allowlist: lifecycle/settlement columns (state, escrow ids,
            # tx hashes, payment denormalization, service timestamps) are
            # service-owned — a caller writing them seeds the job sweeper
            # against a victim escrow (#815).
            _JOB_WRITABLE = {
                "client_id",
                "client_ref",
                "offer_id",
                "plugin_id",
                "service_type",
                "model",
                "buyer_address",
                "provider_address",
                "payload",
                "constraints",
                "ttl_seconds",
                "expires_at",
                "payment",
            }
            job_data = {k: v for k, v in data.items() if k in _JOB_WRITABLE}
            job = MarketJob(**job_data)
            job.id = job_id
            # #1634: the column was write-never — persist the chain escrow
            # binding at creation. The on-chain escrow for a market job is
            # keyed by the market job id itself, so that is the linkage value
            # (release/refund/sweeper all resolve /rpc/escrow/{job.id}).
            job.escrow_contract_id = job.id
            if not job.requested_at:
                job.requested_at = datetime.now(UTC).replace(tzinfo=None)
            # Derive expires_at from ttl_seconds when the caller did not set
            # one (#1554): ttl was stored but never enforced, so jobs without
            # an explicit expiry could hold escrowed funds forever.
            if job.expires_at is None and job.ttl_seconds:
                job.expires_at = job.requested_at + timedelta(seconds=int(job.ttl_seconds))
            if not job.created_at:
                job.created_at = datetime.now(UTC).replace(tzinfo=None)
            if not job.updated_at:
                job.updated_at = datetime.now(UTC).replace(tzinfo=None)

            payment_data = data.get("payment") or {}
            # Payment lifecycle fields (status, tx hashes, escrowed/released/
            # refunded timestamps) are written by the payment path, never from
            # the request — a caller-set "escrowed" row is what the sweeper
            # steering relied on (#815).
            try:
                payment_amount = Decimal(str(payment_data.get("amount", payment_data.get("payment_amount", 0))))
            except Exception as e:
                raise ValueError("payment amount must be a valid number") from e
            if not payment_amount.is_finite() or payment_amount < 0:
                raise ValueError("payment amount must be a finite non-negative number")
            if payment_amount > MAX_PAYMENT_AMOUNT:
                raise ValueError(f"payment amount must not exceed {MAX_PAYMENT_AMOUNT}")
            payment = MarketJobPayment(
                id=payment_data.get("id") or uuid4().hex,
                job_id=job.id,
                amount=payment_amount,
                currency=payment_data.get("currency", "AITBC"),
                status="pending",
                payment_method=payment_data.get("payment_method", "aitbc_token"),
                escrow_address=payment_data.get("escrow_address"),
                refund_address=payment_data.get("refund_address"),
                meta_data=payment_data.get("meta_data"),
                created_at=datetime.now(UTC).replace(tzinfo=None),
                updated_at=datetime.now(UTC).replace(tzinfo=None),
                expires_at=job.expires_at,
            )

            job.access_key = (job.payload or {}).get("access_key")
            job.payment_id = payment.id
            job.payment_amount = payment.amount
            job.payment_status = payment.status

            self.session.add(job)
            self.session.add(payment)
            await self.session.commit()
            await self.session.refresh(job)
            await self.session.refresh(payment)

            logger.info("Created market job %s", job.id)
            return {
                **self._job_to_dict(job),
                "payment": self._payment_to_dict(payment),
            }
        except Exception as e:
            await self.session.rollback()
            logger.error("Error in create_market_job: %s: %s", type(e).__name__, e)
            raise

    async def _find_inflight_job_by_client_ref(self, client_ref: str, data: dict[str, Any]) -> MarketJob | None:
        """Return the in-flight job a ``client_ref`` retry refers to (#1553).

        The natural key is ``client_ref`` scoped to the caller's identity —
        ``buyer_address`` when present (canonicalised, since addresses are
        stored EIP-55), else ``client_id``. With neither identity field the
        ref is too weak to dedup on and ``None`` is returned.
        """
        from sqlmodel import col

        buyer = data.get("buyer_address")
        client_id = data.get("client_id")
        if not buyer and not client_id:
            return None
        stmt = (
            select(MarketJob)
            .where(col(MarketJob.client_ref) == client_ref)
            .where(col(MarketJob.state).in_({"QUEUED", "RUNNING"}))
            .order_by(col(MarketJob.created_at).desc())
            .limit(20)
        )
        candidates = (await self.session.execute(stmt)).scalars().all()
        if buyer:
            canonical = canonical_address(str(buyer))
            for job in candidates:
                if job.buyer_address and canonical_address(str(job.buyer_address)) == canonical:
                    return job
            return None
        for job in candidates:
            if job.client_id == client_id:
                return job
        return None

    async def get_market_job(self, job_id: str) -> dict[str, Any] | None:
        """Get a MarketJob by ID, including its payment."""
        try:
            job = await self.session.get(MarketJob, job_id)
            if not job:
                return None

            payment: MarketJobPayment | None = None
            if job.payment_id:
                payment = await self.session.get(MarketJobPayment, job.payment_id)

            return {
                **self._job_to_dict(job),
                "payment": self._payment_to_dict(payment) if payment else None,
            }
        except Exception as e:
            logger.error("Error in get_market_job: %s: %s", type(e).__name__, e)
            raise

    async def list_market_jobs(
        self,
        buyer_address: str | None = None,
        provider_address: str | None = None,
        service_type: str | None = None,
        state: str | None = None,
        offer_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
        owner_address: str | None = None,
    ) -> list[dict[str, Any]]:
        """List market jobs with optional filters.

        ``owner_address`` scopes to jobs where the address is a party (buyer
        or provider); it is the verified-signer path for authenticated
        owner/provider views, not a public filter.
        """
        try:
            from sqlmodel import col, or_

            stmt = select(MarketJob)
            if owner_address:
                owner = canonical_address(owner_address)
                stmt = stmt.where(
                    or_(
                        col(MarketJob.buyer_address) == owner,
                        col(MarketJob.provider_address) == owner,
                    )
                )
            if buyer_address:
                stmt = stmt.where(col(MarketJob.buyer_address) == canonical_address(buyer_address))
            if provider_address:
                stmt = stmt.where(col(MarketJob.provider_address) == canonical_address(provider_address))
            if service_type:
                stmt = stmt.where(col(MarketJob.service_type) == service_type)
            if state:
                stmt = stmt.where(col(MarketJob.state) == state)
            if offer_id:
                stmt = stmt.where(col(MarketJob.offer_id) == offer_id)
            # Floor at 1: SQLite treats LIMIT < 0 as unlimited. OFFSET is
            # floored at 0 for the same reason (negative offsets error).
            stmt = (
                stmt.order_by(col(MarketJob.created_at).desc())
                .offset(max(offset, 0))
                .limit(min(max(limit, 1), max_page_size()))
            )

            result = await self.session.execute(stmt)
            jobs = list(result.scalars().all())

            payment_ids = [job.payment_id for job in jobs if job.payment_id]
            payments: dict[str, MarketJobPayment] = {}
            if payment_ids:
                pres = await self.session.execute(select(MarketJobPayment).where(col(MarketJobPayment.id).in_(payment_ids)))
                payments = {p.id: p for p in pres.scalars().all()}

            return [
                {
                    **self._job_to_dict(job),
                    "payment": self._payment_to_dict(payments[job.payment_id]) if job.payment_id in payments else None,
                }
                for job in jobs
            ]
        except Exception as e:
            logger.error("Error in list_market_jobs: %s: %s", type(e).__name__, e)
            raise

    async def cancel_market_job(self, job_id: str, reason: str = "") -> dict[str, Any]:
        """Cancel a market job and mark its payment for refund."""
        try:
            job = await self.session.get(MarketJob, job_id)
            if not job:
                raise ValueError(f"Job not found: {job_id}")

            if job.state in {"CANCELED", "REFUNDED", "RELEASED", "COMPLETED"}:
                return self._job_to_dict(job)

            now = datetime.now(UTC).replace(tzinfo=None)

            # #1790: payment flip is a CAS too — only an escrowed payment
            # moves to refund_pending; rowcount is the truth, not the read.
            payment_flipped = False
            if job.payment_id:
                payment_flipped = await self._cas_payment_status(
                    job.payment_id, "escrowed", {"status": "refund_pending", "updated_at": now}
                )

            # #1790: CAS the lifecycle write — the state predicate in WHERE
            # is the compare-and-swap. A concurrent cancel/settle that
            # committed first makes rowcount 0; roll back (reverting the
            # payment flip) and report the state that actually won.
            claim = await self.session.execute(
                update(MarketJob)
                .where(
                    col(MarketJob.id) == job_id,
                    col(MarketJob.state).notin_({"CANCELED", "REFUNDED", "RELEASED", "COMPLETED"}),
                )
                .values(
                    state="CANCELED",
                    receipt={"reason": reason or "buyer_requested"},
                    error=None,
                    payment_status="refund_pending" if payment_flipped else job.payment_status,
                    updated_at=now,
                )
                .execution_options(synchronize_session=False)
            )
            if getattr(claim, "rowcount", 0) != 1:
                await self.session.rollback()
                job = await self.session.get(MarketJob, job_id)
                return self._job_to_dict(job) if job else {}

            await self.session.commit()
            await self.session.refresh(job)

            return self._job_to_dict(job)
        except Exception as e:
            await self.session.rollback()
            logger.error("Error in cancel_market_job: %s: %s", type(e).__name__, e)
            raise

    async def dispute_market_job(self, job_id: str, reason: str = "") -> dict[str, Any]:
        """#1783: open a dispute freeze on a market job's escrow settlement.

        While ``disputed_at`` is set and ``dispute_cleared_at`` is not, the
        sweeper skips both the release and refund passes for this job.
        """
        try:
            job = await self.session.get(MarketJob, job_id)
            if not job:
                raise ValueError(f"Job not found: {job_id}")
            now = datetime.now(UTC).replace(tzinfo=None)
            if job.disputed_at is None or job.dispute_cleared_at is not None:
                job.disputed_at = now
                job.dispute_reason = (reason or "")[:500] or None
                job.dispute_cleared_at = None
                job.updated_at = now
                self.session.add(job)
                await self.session.commit()
                await self.session.refresh(job)
            return self._job_to_dict(job)
        except Exception as e:
            await self.session.rollback()
            logger.error("Error in dispute_market_job: %s: %s", type(e).__name__, e)
            raise

    async def resolve_market_job_dispute(self, job_id: str) -> dict[str, Any]:
        """#1783: clear the dispute freeze so the sweeper can settle/refund."""
        try:
            job = await self.session.get(MarketJob, job_id)
            if not job:
                raise ValueError(f"Job not found: {job_id}")
            if job.disputed_at is not None and job.dispute_cleared_at is None:
                job.dispute_cleared_at = datetime.now(UTC).replace(tzinfo=None)
                job.updated_at = job.dispute_cleared_at
                self.session.add(job)
                await self.session.commit()
                await self.session.refresh(job)
            return self._job_to_dict(job)
        except Exception as e:
            await self.session.rollback()
            logger.error("Error in resolve_market_job_dispute: %s: %s", type(e).__name__, e)
            raise

    @staticmethod
    def _pin_payload(job: MarketJob, size: int | None, pin_tx_hash: str | None, provider_confirmed: bool) -> dict[str, Any]:
        payload = dict(job.payload or {})
        payload["pinned"] = True
        if size is not None:
            payload["size"] = size
        if pin_tx_hash:
            payload["pin_tx_hash"] = pin_tx_hash
        if provider_confirmed:
            payload["provider_confirmed"] = True
        return payload

    async def _cas_payment_status(self, payment_id: str, from_status: str, values: dict[str, Any]) -> bool:
        """#1790: conditional payment-status write — the from_status predicate
        in WHERE is the compare-and-swap; True iff this call won the flip."""
        claim = await self.session.execute(
            update(MarketJobPayment)
            .where(col(MarketJobPayment.id) == payment_id, col(MarketJobPayment.status) == from_status)
            .values(**values)
            .execution_options(synchronize_session=False)
        )
        return getattr(claim, "rowcount", 0) == 1

    @staticmethod
    def _addresses_match(left: Any, right: Any) -> bool:
        """Best-effort address equality: canonical EIP-55 when both parse,
        case-insensitive string compare otherwise."""
        if not left or not right:
            return False
        try:
            return canonical_address(str(left)) == canonical_address(str(right))
        except Exception:
            return str(left).strip().lower() == str(right).strip().lower()

    async def _require_locked_escrow(self, job: MarketJob, payment: MarketJobPayment) -> None:
        """#1564: the pending->escrowed flip needs on-chain escrow proof.

        The chain escrow is keyed by the market job id (``/rpc/escrow/{job_id}``),
        so proof is: the escrow row exists, it is in a locked state (not
        created/released/refunded/expired), and — where the response and the
        job both name them — the locked amount and the buyer/provider parties
        match this job's payment record. Anything less used to flip the
        payment to ``escrowed`` on an HTTP call alone.
        """
        escrow = await self._rpc_client.verify_escrow(job.id)
        if not escrow:
            raise ValueError(f"No on-chain escrow found for job {job.id}; payment cannot be marked escrowed")
        # Whitelist, not blacklist: the node reports contract states
        # (created/funded/job_started/job_completed/disputed/resolved/released/
        # refunded/expired) or the escrow row status (locked/released/refunded/
        # settlement_failed). Only the states where funds are actually locked
        # qualify — anything else (created-but-unfunded, settlement_failed,
        # terminal) must not flip the payment.
        state = str(escrow.get("state") or "").lower()
        if state not in {"funded", "locked", "job_started", "job_completed", "disputed", "resolved"}:
            raise ValueError(f"On-chain escrow for job {job.id} is not locked (state={state or 'unknown'})")
        amount = escrow.get("amount")
        if amount is not None:
            try:
                locked = Decimal(str(amount))
            except Exception as e:
                raise ValueError(f"On-chain escrow for job {job.id} has an unreadable amount") from e
            if not locked.is_finite() or locked != payment.amount:
                raise ValueError(f"On-chain escrow amount {locked} does not match job payment amount {payment.amount}")
        for field, expected in (("buyer", job.buyer_address), ("provider", job.provider_address)):
            actual = escrow.get(field)
            if actual and expected and not self._addresses_match(actual, expected):
                raise ValueError(f"On-chain escrow {field} does not match job {job.id}")

    async def confirm_market_job_pin(
        self,
        job_id: str,
        size: int | None = None,
        pin_tx_hash: str | None = None,
        provider_confirmed: bool = False,
    ) -> dict[str, Any]:
        """Confirm a job has been pinned and optionally transition to RUNNING."""
        try:
            job = await self.session.get(MarketJob, job_id)
            if not job:
                raise ValueError(f"Job not found: {job_id}")

            if job.state not in {"QUEUED", "RUNNING"}:
                return self._job_to_dict(job)

            payment = None
            if job.payment_id:
                payment = await self.session.get(MarketJobPayment, job.payment_id)
            # #1564: pending->escrowed is a settlement claim — it requires the
            # escrow to exist on-chain with matching amount and parties. The
            # check runs before any mutation so a failed proof leaves the job
            # untouched and the provider can retry once the lock lands.
            if payment is not None and payment.status == "pending":
                await self._require_locked_escrow(job, payment)

            # payload is a plain JSON column: reassign, don't mutate in place,
            # or SQLAlchemy never sees the change and the update is dropped.
            payload = self._pin_payload(job, size, pin_tx_hash, provider_confirmed)

            now = datetime.now(UTC).replace(tzinfo=None)

            # #1790: pending->escrowed is a CAS — rowcount decides, and the
            # proof above already ran so a lost race cannot skip it.
            payment_flipped = False
            if payment is not None and payment.status == "pending":
                payment_flipped = await self._cas_payment_status(
                    payment.id, "pending", {"status": "escrowed", "escrowed_at": now, "updated_at": now}
                )

            # #1790: CAS the QUEUED/RUNNING -> RUNNING transition. A
            # concurrent cancel that committed first yields rowcount 0 —
            # roll back (reverting the payment flip) and return the state
            # that actually won instead of overwriting it.
            claim = await self.session.execute(
                update(MarketJob)
                .where(col(MarketJob.id) == job_id, col(MarketJob.state).in_({"QUEUED", "RUNNING"}))
                .values(
                    state="RUNNING",
                    payload=payload,
                    payment_status="escrowed" if payment_flipped else job.payment_status,
                    updated_at=now,
                )
                .execution_options(synchronize_session=False)
            )
            if getattr(claim, "rowcount", 0) != 1:
                await self.session.rollback()
                job = await self.session.get(MarketJob, job_id)
                return self._job_to_dict(job) if job else {}

            await self.session.commit()
            await self.session.refresh(job)

            return self._job_to_dict(job)
        except Exception as e:
            await self.session.rollback()
            logger.error("Error in confirm_market_job_pin: %s: %s", type(e).__name__, e)
            raise

    async def _require_confirmed_settle_tx(self, tx_hash: str, job: MarketJob, expected_type: str) -> dict[str, Any]:
        """Refuse a caller-supplied settle hash that is not THIS job's escrow settlement.

        A caller-supplied hash is evidence, not authority: verify it on-chain
        like complete_bid does before trusting the state flip (#814), and bind
        it to this job — any confirmed transaction used to count (#1564). The
        chain escrow is keyed by the market job id (``/rpc/escrow/{job_id}``),
        so the sealed tx must be an ``expected_type`` transaction whose payload
        ``job_id`` is this job's id.

        #1584 extends the binding to the parties: the payload's
        ``buyer_escrow_addr``/``provider_escrow_addr`` must match the job's
        recorded addresses when present, and the tx recipient must be the
        escrow payee (provider on release, buyer on refund). Returns the
        verified tx so callers can derive settlement amounts from the
        on-chain ``value`` instead of trusting caller-supplied figures.
        """
        chain_id = settings.default_chain_id or resolve_chain_id()
        tx = await self._rpc_client.get_transaction(tx_hash, chain_id=chain_id)
        if not tx or tx.get("status") != "confirmed":
            raise ValueError(f"Supplied tx_hash {tx_hash} is not a confirmed on-chain transaction")
        tx_type = tx.get("type") or tx.get("transaction_type")
        if tx_type != expected_type:
            raise ValueError(f"Transaction {tx_hash} is type {tx_type!r}, not {expected_type}")
        payload = tx.get("payload") or {}
        if payload.get("job_id") != job.id:
            raise ValueError(f"Transaction {tx_hash} is not bound to escrow for job {job.id}")

        is_release = expected_type == "ESCROW_RELEASE"
        payee_field = "provider_escrow_addr" if is_release else "buyer_escrow_addr"
        counterparty_field = "buyer_escrow_addr" if is_release else "provider_escrow_addr"
        job_payee = job.provider_address if is_release else job.buyer_address
        job_counterparty = job.buyer_address if is_release else job.provider_address
        expected_payee = self._canonical_address(str(job_payee or ""))
        expected_counterparty = self._canonical_address(str(job_counterparty or ""))
        payload_payee = payload.get(payee_field)
        payload_counterparty = payload.get(counterparty_field)
        if expected_payee and payload_payee and self._canonical_address(str(payload_payee)) != expected_payee:
            raise ValueError(f"Transaction {tx_hash} payload {payee_field} does not match job {job.id} payee {expected_payee}")
        if (
            expected_counterparty
            and payload_counterparty
            and self._canonical_address(str(payload_counterparty)) != expected_counterparty
        ):
            raise ValueError(
                f"Transaction {tx_hash} payload {counterparty_field} does not match job {job.id} counterparty {expected_counterparty}"
            )
        # The sealed row spells it `recipient`; a mempool-shaped dict uses `to`.
        tx_recipient = self._canonical_address(str(tx.get("recipient") or tx.get("to") or ""))
        effective_payee = self._canonical_address(str(payload_payee)) if payload_payee else expected_payee
        if effective_payee and tx_recipient and tx_recipient != effective_payee:
            raise ValueError(
                f"Transaction {tx_hash} pays {tx_recipient}, not the escrow payee {effective_payee} for job {job.id}"
            )
        return tx

    @staticmethod
    def _settled_amount_ait(tx: dict[str, Any]) -> Decimal | None:
        """AIT value a verified settle tx moved, from its on-chain ``value``.

        The sealed row spells it ``value``; a mempool-shaped dict uses
        ``amount``. Returns None when the tx carries no readable amount —
        callers then leave the settlement amount unset rather than storing a
        caller-supplied figure (#1584).
        """
        raw = tx.get("value", tx.get("amount"))
        if raw is None:
            return None
        try:
            return units_to_ait(int(raw))
        except (TypeError, ValueError):
            return None

    def _guard_release_settlement(
        self, job: MarketJob, payment: MarketJobPayment | None, job_id: str
    ) -> dict[str, Any] | None:
        """#1564 release state guards.

        Only an escrowed payment on a job that is not already
        refunded/cancelled/failed may be released. An already-released pair
        replays idempotently (returns the job dict); anything else raises.
        """
        if payment is None or payment.status not in {"escrowed", "released"}:
            raise ValueError(f"Job {job_id} has no escrowed payment to release")
        if payment.status == "released" and job.state == "RELEASED":
            return self._job_to_dict(job)
        if job.state in {"CANCELED", "FAILED", "REFUNDED"}:
            raise ValueError(f"Cannot release escrow for job {job_id} in state {job.state}")
        # Release pays the provider for delivered work. Legitimate callers
        # reach it from RUNNING (pin-confirm is the delivery proof for IPFS
        # rentals) or COMPLETED; QUEUED has no delivery at all and EXPIRED is
        # owned by the refund path — releasing there would race the buyer's
        # refund and could pay the provider for undelivered work (#v11 item
        # 10 residual).
        if job.state not in {"RUNNING", "COMPLETED"}:
            raise ValueError(
                f"Cannot release escrow for job {job_id} in state {job.state}; only RUNNING/COMPLETED jobs release"
            )
        return None

    def _guard_refund_settlement(self, job: MarketJob, payment: MarketJobPayment | None, job_id: str) -> dict[str, Any] | None:
        """#1564 refund state guards.

        Refund only escrowed (or already refund-pending) payments, never a
        released one, and never a job that is still queued/running unless
        cancel already flagged the payment refund_pending. An
        already-refunded pair replays idempotently (returns the job dict).
        """
        if payment is None or payment.status not in {"escrowed", "refund_pending", "refunded"}:
            raise ValueError(f"Job {job_id} has no refundable escrowed payment")
        if payment.status == "refunded" and job.state == "REFUNDED":
            return self._job_to_dict(job)
        if payment.status == "released" or job.state in {"RELEASED", "COMPLETED"}:
            raise ValueError(f"Cannot refund escrow for job {job_id}: payment already released")
        if job.state in {"QUEUED", "RUNNING"} and payment.status != "refund_pending":
            raise ValueError(f"Cannot refund escrow for job {job_id} in state {job.state}; cancel it first")
        return None

    async def release_market_job_payment(self, job_id: str, release_data: dict[str, Any] | None = None) -> dict[str, Any]:
        """Release the escrow for a completed market job."""
        try:
            release_data = release_data or {}
            job = await self.session.get(MarketJob, job_id)
            if not job:
                raise ValueError(f"Job not found: {job_id}")

            payment: MarketJobPayment | None = None
            if job.payment_id:
                payment = await self.session.get(MarketJobPayment, job.payment_id)

            replay = self._guard_release_settlement(job, payment, job_id)
            if replay is not None:
                return replay

            tx_hash = release_data.get("tx_hash")
            released_amount = release_data.get("released_amount")
            if tx_hash:
                tx = await self._require_confirmed_settle_tx(tx_hash, job, "ESCROW_RELEASE")
                # The caller's released_amount is a claim, not evidence: store
                # the amount the verified transaction actually moved (#1584).
                released_amount = self._settled_amount_ait(tx)
            else:
                # The chain escrow is keyed by job_id — the market job id is
                # the escrow's job_id (the buyer CLI escrows under it).
                # escrow_contract_id now persists that same job.id at
                # creation (#1634) but remains informational only — the RPC
                # path key is always job.id, never the column (#1564).
                result = await self._rpc_client.release_escrow(job.id)
                if not (result and result.get("success")):
                    raise ValueError(f"Escrow release failed for job {job_id}: {result}")
                tx_hash = str(result.get("tx_hash", ""))
                released_amount = result.get("released_amount")

            job.state = "RELEASED"
            job.payment_status = "released"
            job.tx_hash = tx_hash
            job.completed_at = datetime.now(UTC).replace(tzinfo=None)
            job.updated_at = datetime.now(UTC).replace(tzinfo=None)

            if payment:
                payment.status = "released"
                payment.transaction_hash = tx_hash
                payment.released_at = datetime.now(UTC).replace(tzinfo=None)
                payment.updated_at = datetime.now(UTC).replace(tzinfo=None)
                if released_amount is not None:
                    payment.released_amount = Decimal(str(released_amount))
                self.session.add(payment)

            self.session.add(job)
            await self.session.commit()
            await self.session.refresh(job)

            return self._job_to_dict(job)
        except Exception as e:
            await self.session.rollback()
            logger.error("Error in release_market_job_payment: %s: %s", type(e).__name__, e)
            raise

    async def refund_market_job_payment(
        self, job_id: str, reason: str = "", refund_data: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Refund the escrow for a failed or canceled market job."""
        try:
            refund_data = refund_data or {}
            job = await self.session.get(MarketJob, job_id)
            if not job:
                raise ValueError(f"Job not found: {job_id}")

            payment: MarketJobPayment | None = None
            if job.payment_id:
                payment = await self.session.get(MarketJobPayment, job.payment_id)

            replay = self._guard_refund_settlement(job, payment, job_id)
            if replay is not None:
                return replay

            tx_hash = refund_data.get("tx_hash")
            refunded_amount = refund_data.get("refunded_amount")
            if tx_hash:
                tx = await self._require_confirmed_settle_tx(tx_hash, job, "ESCROW_REFUND")
                # Same rule as release: the on-chain value is authoritative,
                # never the caller-supplied figure (#1584).
                refunded_amount = self._settled_amount_ait(tx)
            else:
                # Same canonical binding as release: the escrow path key is
                # the market job id, not escrow_contract_id (#1564).
                result = await self._rpc_client.refund_escrow(job.id)
                if not (result and result.get("success")):
                    raise ValueError(f"Escrow refund failed for job {job_id}: {result}")
                tx_hash = str(result.get("tx_hash", ""))
                refunded_amount = result.get("refunded_amount")

            job.state = "REFUNDED"
            job.payment_status = "refunded"
            job.refund_tx_hash = tx_hash
            if reason:
                job.receipt = {"reason": reason}
            job.updated_at = datetime.now(UTC).replace(tzinfo=None)

            if payment:
                payment.status = "refunded"
                payment.refund_transaction_hash = tx_hash
                payment.refunded_at = datetime.now(UTC).replace(tzinfo=None)
                payment.updated_at = datetime.now(UTC).replace(tzinfo=None)
                if refunded_amount is not None:
                    payment.refunded_amount = Decimal(str(refunded_amount))
                self.session.add(payment)

            self.session.add(job)
            await self.session.commit()
            await self.session.refresh(job)

            return self._job_to_dict(job)
        except Exception as e:
            await self.session.rollback()
            logger.error("Error in refund_market_job_payment: %s: %s", type(e).__name__, e)
            raise

    async def get_market_job_access_token(self, access_key: str, access_secret: str) -> dict[str, Any] | None:
        """Validate an access token and return the job details."""
        from sqlmodel import col

        try:
            stmt = select(MarketJob).where(col(MarketJob.access_key) == access_key)
            result = await self.session.execute(stmt)
            job = result.scalar_one_or_none()
            if not job:
                return None

            if not _secret_matches((job.payload or {}).get("access_secret") or "", access_secret):
                return None

            if job.state not in _ACCESS_TOKEN_ACTIVE_STATES:
                return None

            if job.expires_at and job.expires_at < datetime.now(UTC).replace(tzinfo=None):
                # Only unfinished jobs expire — mirror _expire_stale_jobs.
                # A COMPLETED job past its TTL keeps its terminal state:
                # flipping it to EXPIRED would flip its escrowed payment to
                # refund_pending and pay the buyer for finished work (and a
                # RELEASED job would regress to EXPIRED). Access is still
                # denied past expiry either way (#v11 item 6).
                if job.state in {"QUEUED", "RUNNING"}:
                    job.state = "EXPIRED"
                    # Mirror _expire_stale_jobs: an escrowed payment on an expired
                    # (unfinished) job must go to the buyer, not sit escrowed
                    # where the sweeper's release pass could pay the provider.
                    if job.payment_id:
                        payment = await self.session.get(MarketJobPayment, job.payment_id)
                        if payment is not None and payment.status == "escrowed":
                            payment.status = "refund_pending"
                            payment.updated_at = datetime.now(UTC).replace(tzinfo=None)
                            self.session.add(payment)
                            job.payment_status = "refund_pending"
                    await self.session.commit()
                return None

            return {
                "job_id": job.id,
                "cid": job.payload.get("cid"),
                "ipfs_api": job.payload.get("ipfs_api"),
                "public_endpoint": job.payload.get("public_endpoint"),
                "expires_at": _isoformat(job.expires_at),
                "size": job.payload.get("size"),
                # The paid model — shop gates bind the request body's model
                # to it (APIGW-OLLAMA-DEPTH2-1, #1613). Column first, payload
                # fallback for rows that only recorded it in the payload.
                "model": job.model or (job.payload or {}).get("model"),
            }
        except Exception as e:
            logger.error("Error in get_market_job_access_token: %s: %s", type(e).__name__, e)
            raise

    async def get_market_job_usage(self, buyer_address: str, offer_id: str) -> int:
        """Return the total bytes of active IPFS storage for a buyer/offer pair."""
        from sqlmodel import col

        try:
            stmt = (
                select(MarketJob)
                .where(col(MarketJob.buyer_address) == canonical_address(buyer_address))
                .where(col(MarketJob.offer_id) == offer_id)
                .where(col(MarketJob.service_type) == "ipfs")
                .where(col(MarketJob.state).in_({"QUEUED", "RUNNING"}))
                # Bounded scan: the endpoint returns a scalar but still
                # materialises every matching row (#1543). A buyer/offer pair
                # with more active jobs than the page ceiling under-reports —
                # accepted trade-off vs an unbounded read.
                .limit(max_page_size())
            )
            result = await self.session.execute(stmt)
            jobs = list(result.scalars().all())
            # payload.size is caller-influenced (pin-confirm) and legacy rows
            # predate the non-negative-int validation (#1449): a non-numeric
            # or negative value must not 500 or corrupt the usage total.
            total = 0
            for j in jobs:
                payload = j.payload if isinstance(j.payload, dict) else {}
                try:
                    size = int(payload.get("size", 0) or 0)
                except (TypeError, ValueError):
                    continue
                total += max(size, 0)
            return total
        except Exception as e:
            logger.error("Error in get_market_job_usage: %s: %s", type(e).__name__, e)
            raise

    async def check_software_offer_health(self, plugin_id: str) -> dict[str, Any]:
        """Check the health of a software offer."""
        try:
            from sqlmodel import col

            stmt = select(SoftwareService).where(col(SoftwareService.plugin_id) == plugin_id)
            result = await self.session.execute(stmt)
            service = result.scalar_one_or_none()
            if not service:
                raise ValueError(f"Service not found: {plugin_id}")

            health_url = service.health_url or ""
            if not health_url:
                return {"healthy": False, "reason": "no health_url configured"}

            try:
                await _check_health_url(health_url)
            except ValueError as e:
                # The detail stays in the log: a resolved address in the reply
                # would turn this route into an internal-DNS oracle.
                logger.warning("Refused health_url of %s: %s", plugin_id, e)
                return dict(_HEALTH_REFUSED)

            if service.service_type == "ipfs" and "api/v0/version" in health_url:
                try:
                    import httpx

                    async with httpx.AsyncClient(timeout=10.0) as client:
                        resp = await client.post(health_url)
                        resp.raise_for_status()
                        data = resp.json()

                    peer_id = data.get("ID") or data.get("PeerID") or data.get("id") or ""
                    version = data.get("Version") or data.get("version") or ""

                    pinned_count = None
                    try:
                        pin_url = health_url.replace("/api/v0/version", "/api/v0/pin/ls")
                        async with httpx.AsyncClient(timeout=10.0) as client:
                            pin_resp = await client.post(pin_url, params={"stream": "true"}, timeout=10.0)
                            if pin_resp.status_code == 200:
                                pinned_count = await _count_pin_lines(pin_resp)
                    except Exception:
                        pass

                    return {
                        "healthy": True,
                        "service_type": "ipfs",
                        "version": version,
                        "peer_id": peer_id,
                        "pinned_count": pinned_count,
                        "disk_usage_bytes": None,
                        "quota_mb": service.disk_quota_mb,
                    }
                except Exception as e:
                    return {"healthy": False, "service_type": "ipfs", "reason": str(e)}

            # Generic HTTP health for other services
            try:
                import httpx

                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.get(health_url)
                    resp.raise_for_status()
                return {"healthy": True, "service_type": service.service_type, "status_code": resp.status_code}
            except Exception as e:
                return {"healthy": False, "service_type": service.service_type, "reason": str(e)}
        except Exception as e:
            logger.error("Error in check_software_offer_health: %s: %s", type(e).__name__, e)
            raise
