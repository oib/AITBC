"""
MarketService market-job lifecycle, escrow and settlement mixin.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import or_, update
from sqlmodel import col, select

from aitbc.aitbc_logging import get_logger
from aitbc.crypto.signature_recovery import canonical_address
from aitbc.market import OfferFSM, OfferStatus
from aitbc.utils.chain_id import resolve_chain_id
from aitbc.utils.units import ait_to_units, units_to_ait

from ...config import settings
from ...domain.market import Bid, MarketJob, MarketJobPayment, MarketOffer, SoftwareService
from ...domain.offer_status import to_offer_status


logger = get_logger(__name__)

from .shared import (
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
    hash_access_secret,
    is_hashed_secret,
    max_page_size,
)

from .core import _CoreMixin


class _JobsMixin(_CoreMixin):
    if TYPE_CHECKING:
        # Provided by _OffersMixin via MarketService MRO; declared for mypy.
        async def get_offer(self, offer_id: str) -> MarketOffer | None: ...

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
        # the payload, the same order-reference convention the chain's
        # order_id index (_ORDER_ID_PAYLOAD_FIELDS) already resolves.
        payload = tx.get("payload") or {}
        refs = {str(payload.get(k)) for k in ("bid_id", "offer_id", "order_id") if payload.get(k) is not None}
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

    async def _cas_payment_status(self, payment_id: str, from_statuses: frozenset[str] | str, values: dict[str, Any]) -> bool:
        """#1790: conditional payment-status write — the from_status predicate
        in WHERE is the compare-and-swap; True iff this call won the flip."""
        if isinstance(from_statuses, str):
            status_pred = col(MarketJobPayment.status) == from_statuses
        else:
            status_pred = col(MarketJobPayment.status).in_(from_statuses)
        claim = await self.session.execute(
            update(MarketJobPayment)
            .where(col(MarketJobPayment.id) == payment_id, status_pred)
            .values(**values)
            .execution_options(synchronize_session=False)
        )
        return getattr(claim, "rowcount", 0) == 1

    async def _cas_settle_terminal(
        self,
        job_id: str,
        *,
        allowed_states: set[str] | frozenset[str],
        job_values: dict[str, Any],
        payment: MarketJobPayment | None,
        payment_from_statuses: frozenset[str] | str,
        payment_values: dict[str, Any],
    ) -> dict[str, Any] | None:
        """#1835 F2: CAS the release/refund terminal writes.

        The payment flip and the job transition are conditional UPDATEs —
        the allowed-state set plus the no-open-dispute clause in WHERE are
        the compare-and-swap; a concurrent cancel/settle/dispute that
        committed during the RPC window wins. Returns None when the job CAS
        won (caller commits); on a lost race the transaction is rolled back
        (reverting the payment flip) and the winning job's dict is returned
        (#1790 pattern).
        """
        if payment is not None:
            await self._cas_payment_status(payment.id, payment_from_statuses, payment_values)
        claim = await self.session.execute(
            update(MarketJob)
            .where(
                col(MarketJob.id) == job_id,
                col(MarketJob.state).in_(allowed_states),
                or_(col(MarketJob.disputed_at).is_(None), col(MarketJob.dispute_cleared_at).is_not(None)),
            )
            .values(**job_values)
            .execution_options(synchronize_session=False)
        )
        if getattr(claim, "rowcount", 0) == 1:
            return None
        await self.session.rollback()
        winner = await self.session.get(MarketJob, job_id)
        return self._job_to_dict(winner) if winner else {}

    @staticmethod
    def _settle_payment_values(
        *,
        status: str,
        tx_hash: str,
        amount: Any,
        now: datetime,
        amount_field: str,
        hash_field: str,
        ts_field: str,
    ) -> dict[str, Any]:
        values: dict[str, Any] = {
            "status": status,
            hash_field: tx_hash,
            ts_field: now,
            "updated_at": now,
        }
        if amount is not None:
            values[amount_field] = Decimal(str(amount))
        return values

    @staticmethod
    def _refundable_job_states(payment: MarketJobPayment | None) -> set[str]:
        """#1835 F2: state set mirroring _guard_refund_settlement — QUEUED/
        RUNNING only when the payment is already refund_pending (cancel
        flagged it), never for a live escrowed payment."""
        states = {"FAILED", "CANCELED", "EXPIRED", "REFUNDED"}
        if payment is not None and payment.status == "refund_pending":
            states |= {"QUEUED", "RUNNING"}
        return states

    @staticmethod
    def _addresses_match(left: Any, right: Any) -> bool:
        """Best-effort address equality: canonical EIP-55 when both parse,
        case-insensitive string compare otherwise."""
        if not left or not right:
            return False
        try:
            return canonical_address(str(left)) == canonical_address(str(right))
        except _OPS_ERRORS:
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
        # #1835 F1: an open dispute freezes settlement on every path, not
        # just the sweeper — the chain escrow has no dispute concept, so
        # without this check a dispute-then-release call pays out anyway.
        if job.disputed_at is not None and job.dispute_cleared_at is None:
            raise ValueError(f"Cannot release escrow for job {job_id}: an open dispute freezes settlement")
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
        # #1835 F1: same freeze as release — an open dispute blocks refund.
        if job.disputed_at is not None and job.dispute_cleared_at is None:
            raise ValueError(f"Cannot refund escrow for job {job_id}: an open dispute freezes settlement")
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

            now = datetime.now(UTC).replace(tzinfo=None)
            # #1835 F2: terminal writes are CAS via _cas_settle_terminal —
            # RUNNING/COMPLETED + no-open-dispute in WHERE is the swap; a
            # concurrent cancel/dispute that committed during the RPC
            # window wins and its state is reported instead.
            lost = await self._cas_settle_terminal(
                job_id,
                allowed_states={"RUNNING", "COMPLETED"},
                job_values={
                    "state": "RELEASED",
                    "payment_status": "released",
                    "tx_hash": tx_hash,
                    "completed_at": now,
                    "updated_at": now,
                },
                payment=payment,
                payment_from_statuses="escrowed",
                payment_values=self._settle_payment_values(
                    status="released",
                    tx_hash=tx_hash,
                    amount=released_amount,
                    now=now,
                    amount_field="released_amount",
                    hash_field="transaction_hash",
                    ts_field="released_at",
                ),
            )
            if lost is not None:
                return lost

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

            now = datetime.now(UTC).replace(tzinfo=None)
            # #1835 F2: same CAS treatment as release — the refundable state
            # set mirrors _guard_refund_settlement, plus the no-open-dispute
            # predicate so a dispute landing mid-RPC also loses.
            job_values: dict[str, Any] = {
                "state": "REFUNDED",
                "payment_status": "refunded",
                "refund_tx_hash": tx_hash,
                "updated_at": now,
            }
            if reason:
                job_values["receipt"] = {"reason": reason}
            lost = await self._cas_settle_terminal(
                job_id,
                allowed_states=self._refundable_job_states(payment),
                job_values=job_values,
                payment=payment,
                payment_from_statuses=frozenset({"escrowed", "refund_pending"}),
                payment_values=self._settle_payment_values(
                    status="refunded",
                    tx_hash=tx_hash,
                    amount=refunded_amount,
                    now=now,
                    amount_field="refunded_amount",
                    hash_field="refund_transaction_hash",
                    ts_field="refunded_at",
                ),
            )
            if lost is not None:
                return lost

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
