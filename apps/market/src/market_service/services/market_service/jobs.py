"""
MarketService market-job lifecycle, escrow and settlement mixin.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import update
from sqlmodel import col, select

from aitbc.aitbc_logging import get_logger
from aitbc.crypto.signature_recovery import canonical_address
from aitbc.market import OfferFSM, OfferStatus
from aitbc.utils.chain_id import resolve_chain_id
from aitbc.utils.units import ait_to_units

from ...config import settings
from ...domain.market import Bid, MarketJob, MarketJobPayment, MarketOffer, SoftwareService
from ...domain.offer_status import to_offer_status


logger = get_logger(__name__)

# #1996: payload keys the server owns — delivery evidence and the
# buyer-acceptance window start written only by ``_pin_payload`` on a
# provider-signed confirm. A caller seeding them at creation lets
# ``setdefault`` keep a backdated ``provider_confirmed_at`` and pass the
# #1976 release-window gate immediately. ``size`` stays caller-writable:
# it is the declared content size, overwritten by pin-confirm.
_PAYLOAD_SERVER_KEYS = frozenset({"provider_confirmed", "provider_confirmed_at", "pinned", "pin_tx_hash"})

from .shared import (
    MAX_JOB_TTL_SECONDS,
    MAX_PAYMENT_AMOUNT,
    _ACCESS_TOKEN_ACTIVE_STATES,
    _HEALTH_REFUSED,
    _MAX_JOB_DISPUTES,
    _OPS_ERRORS,
    _check_health_url,
    _count_pin_lines,
    _isoformat,
    _secret_matches,
    _validated_job_ttl,
    active_rental_token_covers,
    hash_access_secret,
    is_hashed_secret,
    max_page_size,
)

from .core import _CoreMixin


class _JobsMixin(_CoreMixin):
    if TYPE_CHECKING:
        # Provided by _OffersMixin/_JobsSettlementMixin via MarketService MRO; declared for mypy.
        async def get_offer(self, offer_id: str) -> MarketOffer | None: ...
        # Provided by _JobsSettlementMixin via MarketService MRO; declared for mypy.
        async def _cas_payment_status(
            self, payment_id: str, from_statuses: frozenset[str] | str, values: dict[str, Any]
        ) -> bool: ...
        # Provided by _JobsSettlementMixin via MarketService MRO; declared for mypy.
        async def _job_token_escrow_verified(self, job: MarketJob, payment: MarketJobPayment | None) -> bool: ...

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
        # #1914: fail closed on non-positive bid prices — _create_bid now
        # rejects them, but a legacy/corrupt row must not skip the minimum.
        if required_value <= 0:
            raise ValueError(f"Bid {bid.id} has no positive price to verify against")
        if tx_value < required_value:
            raise ValueError(f"Transaction value {tx_value} compute-units is less than required {required_value}")

        # #1914: sender/recipient/value alone do not bind the tx to THIS bid —
        # any confirmed buyer→provider payment of sufficient size used to
        # complete it. The sealed tx must reference the bid or its offer in
        # the payload. Accepted refs: bid_id/offer_id/order_id (the chain's
        # order_id index convention) plus job_id — the escrow convention
        # keys payload.job_id to the same id the market registers escrows
        # under, so existing escrow-flow payments already carry it.
        payload = tx.get("payload")
        if not isinstance(payload, dict):
            payload = {}
        refs = {str(payload.get(k)) for k in ("bid_id", "offer_id", "order_id", "job_id") if payload.get(k) is not None}
        if bid.id not in refs and offer.id not in refs:
            raise ValueError(f"Transaction {tx_hash} is not bound to bid {bid.id} or offer {offer.id}")

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

        from ...domain.market import IpfsRentalToken

        try:
            access_key, data = self._normalize_ipfs_token_data(data)

            # #2348: derive the settlement clock from the market job. The
            # writable allowlist strips ``expires_at`` (service-owned), but
            # a token without it never expires and the rental sweeper can
            # never settle the escrow. ``rental_id`` is the market job id —
            # look it up and inherit its expiry. ``escrow_contract_id``
            # stays unset on purpose: the sweeper falls back to
            # ``rental_id`` (the on-chain escrow key for market jobs), and
            # accepting a caller-supplied escrow id would let a provider
            # steer settlement at a foreign escrow (#815).
            rental_id = data.get("rental_id")
            if rental_id:
                job = await self.session.get(MarketJob, str(rental_id))
                if job is not None and job.expires_at is not None:
                    data["expires_at"] = job.expires_at

            stmt = select(IpfsRentalToken).where(IpfsRentalToken.access_key == access_key)  # type: ignore[arg-type]
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

    def _normalize_ipfs_token_data(self, data: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        """Validate and normalize caller-supplied token fields; returns
        ``(access_key, writable_data)`` with settlement-owned columns
        stripped."""
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
        return access_key, {k: v for k, v in data.items() if k in _TOKEN_WRITABLE}

    async def get_ipfs_rental_token(self, access_key: str, access_secret: str) -> dict[str, Any] | None:
        """Validate an IPFS rental token and return its details."""
        from datetime import UTC, datetime

        from sqlalchemy import select

        from ...domain.market import IpfsRentalToken

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
        from ...domain.market import SoftwareService

        stmt = select(SoftwareService).where((SoftwareService.offer_id == offer_id) | (SoftwareService.plugin_id == offer_id))
        if (await self.session.execute(stmt)).scalars().first() is not None:
            return
        # On-chain fallbacks, same sources the listing merges: a GPU offer by
        # id, then a software offer anchored as a sealed GPU_MARKET tx whose
        # payload carries this offer_id.
        try:
            if await self._rpc_client.get_offer(offer_id):
                return
        except _OPS_ERRORS as e:
            logger.warning("GPU offer lookup for %s failed on chain RPC: %s", offer_id, e)
        try:
            txs = await self._rpc_client.query_transactions(transaction_type="GPU_MARKET", order_id=offer_id, limit=1)
            if txs:
                return
        except _OPS_ERRORS as e:
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

            replay = await self._market_job_replay(data, job_id)
            if replay is not None:
                return replay

            job = await self._prepare_market_job(data, job_id)
            payment = self._build_market_job_payment(data.get("payment") or {}, job)

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

    async def _market_job_replay(self, data: dict[str, Any], job_id: str) -> dict[str, Any] | None:
        """Idempotent-replay lookups for ``create_market_job``; returns the
        replay response dict or None when this is a genuinely new job."""
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
                return await self._replay_market_job_response(existing)

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
                return await self._replay_market_job_response(replay)
        return None

    async def _replay_market_job_response(self, job: MarketJob) -> dict[str, Any]:
        """Serialized replay response for an already-existing job."""
        payment = await self.session.get(MarketJobPayment, job.payment_id) if job.payment_id else None
        return {
            **self._job_to_dict(job),
            "payment": self._payment_to_dict(payment) if payment else None,
            "deduplicated": True,
        }

    async def _prepare_market_job(self, data: dict[str, Any], job_id: str) -> MarketJob:
        """Validate, normalize and allow-list ``data`` into a MarketJob with
        its lifecycle defaults applied (pre-payment fields only)."""
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
            data["payload"] = {k: v for k, v in payload.items() if k not in _PAYLOAD_SERVER_KEYS}

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
        self._apply_job_defaults(job)
        # #2326 MARKET-ESCROW-SQUAT-1: a caller-supplied expires_at reached
        # year 2100 unchecked — an active-state job holds its escrow-key
        # claim until expiry, so an unbounded value squats the key forever.
        # ttl_seconds is already capped; expires_at gets the same ceiling,
        # anchored at the server-set requested_at (not caller-writable).
        if job.expires_at is not None and job.expires_at > job.requested_at + timedelta(seconds=MAX_JOB_TTL_SECONDS):
            raise ValueError(f"expires_at must not exceed {MAX_JOB_TTL_SECONDS} seconds after requested_at")
        return job

    @staticmethod
    def _apply_job_defaults(job: MarketJob) -> None:
        """Fill server-owned timestamp/expiry defaults on a fresh job."""
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

    @staticmethod
    def _build_market_job_payment(payment_data: dict[str, Any], job: MarketJob) -> MarketJobPayment:
        """Build the pending MarketJobPayment for ``job``; validates the
        caller-supplied amount (lifecycle fields are never taken from the
        request — a caller-set "escrowed" row is what the sweeper steering
        relied on, #815)."""
        try:
            payment_amount = Decimal(str(payment_data.get("amount", payment_data.get("payment_amount", 0))))
        except Exception as e:
            raise ValueError("payment amount must be a valid number") from e
        if not payment_amount.is_finite() or payment_amount < 0:
            raise ValueError("payment amount must be a finite non-negative number")
        if payment_amount > MAX_PAYMENT_AMOUNT:
            raise ValueError(f"payment amount must not exceed {MAX_PAYMENT_AMOUNT}")
        return MarketJobPayment(
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
            # #1835 F7: a dispute only freezes live escrow — a paymentless or
            # already-settled job has nothing to freeze, so disputing it is
            # pure griefing. Re-arms after resolve are capped so dispute/
            # resolve cycles cannot freeze settlement forever.
            payment = await self.session.get(MarketJobPayment, job.payment_id) if job.payment_id else None
            if payment is None or payment.status not in {"escrowed", "refund_pending"}:
                raise ValueError(f"Job {job_id} has no escrowed payment to dispute")
            now = datetime.now(UTC).replace(tzinfo=None)
            if job.disputed_at is None or job.dispute_cleared_at is not None:
                receipt = dict(job.receipt or {})
                dispute_count = int(receipt.get("_dispute_count", 0) or 0)
                if dispute_count >= _MAX_JOB_DISPUTES:
                    raise ValueError(f"Job {job_id} has reached the dispute limit ({_MAX_JOB_DISPUTES})")
                receipt["_dispute_count"] = dispute_count + 1
                job.disputed_at = now
                job.dispute_reason = (reason or "")[:500] or None
                job.dispute_cleared_at = None
                job.receipt = receipt
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
                    # #2348: except when an active IpfsRentalToken covers the
                    # job — the rental sweeper owns that escrow's settlement.
                    if job.payment_id:
                        payment = await self.session.get(MarketJobPayment, job.payment_id)
                        covered = (
                            payment is not None
                            and payment.status == "escrowed"
                            and await active_rental_token_covers(self.session, job.id)
                        )
                        if payment is not None and payment.status == "escrowed" and not covered:
                            payment.status = "refund_pending"
                            payment.updated_at = datetime.now(UTC).replace(tzinfo=None)
                            self.session.add(payment)
                            job.payment_status = "refund_pending"
                    await self.session.commit()
                return None

            # #2322 MARKET-TOKEN-ESCROW-BIND-1: the token buys shop work only
            # while the job's escrow is locked on-chain. payment.status
            # "pending" — every freshly registered job — used to pass, so any
            # market-key holder could mint shop tokens with no escrow at all.
            payment = await self.session.get(MarketJobPayment, job.payment_id) if job.payment_id else None
            if not await self._job_token_escrow_verified(job, payment):
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
                    except _OPS_ERRORS:
                        logger.debug("IPFS pin listing for %s failed", health_url, exc_info=True)

                    return {
                        "healthy": True,
                        "service_type": "ipfs",
                        "version": version,
                        "peer_id": peer_id,
                        "pinned_count": pinned_count,
                        "disk_usage_bytes": None,
                        "quota_mb": service.disk_quota_mb,
                    }
                except _OPS_ERRORS as e:
                    return {"healthy": False, "service_type": "ipfs", "reason": str(e)}

            # Generic HTTP health for other services
            try:
                import httpx

                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.get(health_url)
                    resp.raise_for_status()
                return {"healthy": True, "service_type": service.service_type, "status_code": resp.status_code}
            except _OPS_ERRORS as e:
                return {"healthy": False, "service_type": service.service_type, "reason": str(e)}
        except _OPS_ERRORS as e:
            logger.error("Error in check_software_offer_health: %s: %s", type(e).__name__, e)
            raise
