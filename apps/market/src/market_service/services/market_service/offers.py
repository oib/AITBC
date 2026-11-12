"""
MarketService offers/plugins/software-service/graph/anchor mixin.
"""

import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlmodel import col, select

from aitbc.aitbc_logging import get_logger
from aitbc.crypto.signature_recovery import canonical_address
from aitbc.market import OfferFSM, OfferStatus
from aitbc.market.offer_registration import verify_offer_registration
from aitbc.utils.chain_id import resolve_chain_id

from ...config import settings
from ...domain.market import Bid, MarketOffer, OfferAnchor, SoftwareService
from ...domain.offer_status import spellings_of, to_offer_status


logger = get_logger(__name__)

from .shared import (
    _ANCHOR_NEGATIVES_MAX,
    _ANCHOR_NEGATIVE_TTL_SECONDS,
    _GPU_LISTING_DEFAULT_STATUS,
    _OPS_ERRORS,
    _REGISTRATION_FIELDS,
    _get_by_caller_id,
    _gpu_offer_to_service_dict,
    _local_offer_dict,
    _money_decimal,
    _replay_after_integrity_conflict,
    _validate_booking_numbers,
    bid_ttl_seconds,
    coerce_offer_expires_at,
    max_page_size,
    offer_listing_expired,
    offer_reservation_ttl_seconds,
)

from .core import _CoreMixin


class _OffersMixin(_CoreMixin):
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

        from ...domain.market import Plugin

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
        from ...domain.market import Plugin

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

        from ...domain.market import SoftwareService

        try:
            # First, try to get offers from blockchain via RPC (v0.6.6: uses BlockchainRPCClient)
            blockchain_offers = await self._blockchain_gpu_offers(chain_id, status)

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

    async def _blockchain_gpu_offers(self, chain_id: str | None, status: str | None) -> list[dict[str, Any]]:
        """GPU offers from the chain RPC, minus allocated/malformed rows.

        Failures degrade to whatever was collected (usually empty) so the
        local database listing still answers.
        """
        blockchain_offers: list[dict[str, Any]] = []
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
                except _OPS_ERRORS as e:
                    logger.warning("Failed to parse blockchain offer: %s", e)
                    continue

            logger.info("Retrieved %s offers from blockchain RPC (chain_id=%s)", len(blockchain_offers), chain_id)
            # The RPC page is unbounded — cap it before the merge so a
            # large on-chain offer set cannot be materialised and
            # re-merged in full (#1543 residual).
            return blockchain_offers[: max_page_size()]
        except _OPS_ERRORS as e:
            logger.warning("Failed to get offers from blockchain RPC: %s", e)
            return blockchain_offers

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
            now = time.monotonic()
            live = self._partition_live_anchors(wanted, stored, now)
            if not live:
                return

            gpu_anchors, offer_anchors = await self._fetch_chain_anchors(chain_id)
            changed = self._apply_chain_anchors(live, gpu_anchors, offer_anchors, now, stored, local_rows)
            if changed:
                await self.session.commit()
        except Exception as e:  # noqa: BLE001 - anchor resolution is best-effort enrichment
            logger.warning("Failed to resolve on-chain offer anchors: %s", e)

    @classmethod
    def _partition_live_anchors(
        cls,
        wanted: dict[str, tuple[dict[str, Any], bool, str]],
        stored: dict[str, OfferAnchor],
        now: float,
    ) -> dict[str, tuple[dict[str, Any], bool, str, str]]:
        """Apply stored OfferAnchor rows to their offers in place and return
        the live set still needing chain resolution, minus entries inside
        the negative-cache TTL."""
        live: dict[str, tuple[dict[str, Any], bool, str, str]] = {}
        for dbkey, (offer, is_gpu, raw) in wanted.items():
            binding = cls._anchor_binding_key(offer, is_gpu)
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
        cls._evict_anchor_negatives(now)
        return {k: v for k, v in live.items() if cls._anchor_negatives.get((k, v[3]), 0.0) <= now}

    async def _fetch_chain_anchors(
        self, chain_id: str | None
    ) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
        """Fetch anchor candidates per key, newest-first, for both anchor tx
        types. Keeping every candidate per key lets a skipped foreign tx
        fall through to the offer's own older anchor instead of shadowing
        it."""
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
        return gpu_anchors, offer_anchors

    def _apply_chain_anchors(
        self,
        live: dict[str, tuple[dict[str, Any], bool, str, str]],
        gpu_anchors: dict[str, list[dict[str, Any]]],
        offer_anchors: dict[str, list[dict[str, Any]]],
        now: float,
        stored: dict[str, OfferAnchor],
        local_rows: dict[str, SoftwareService] | None,
    ) -> bool:
        """Resolve each live offer against the fetched chain candidates and
        persist new anchors; returns True when any row was written."""
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
        return changed

    async def get_software_service(self, plugin_id: str) -> dict[str, Any] | None:
        """Get a specific software service (local row or on-chain GPU offer)"""
        from sqlalchemy import select

        from ...domain.market import SoftwareService

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
            existing = await self._upsert_software_service(plugin_id, data, signer)
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

    async def _upsert_software_service(self, plugin_id: str, data: dict[str, Any], signer: str | None) -> SoftwareService:
        """Update the existing row for ``plugin_id`` or create a new one.

        ``data`` must already be allow-listed to ``_REGISTRATION_FIELDS``.
        Raises PermissionError when the signer is not the row's provider.
        """
        from sqlalchemy import select

        from ...domain.market import SoftwareService

        query = select(SoftwareService).where(SoftwareService.plugin_id == plugin_id)  # type: ignore[arg-type]
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
        return existing

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

        from ...domain.market import SoftwareService

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
        from ...domain.market import KnowledgeGraph

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
        from ...domain.market import GraphNode

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
        from ...domain.market import GraphEdge

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

        from ...domain.market import GraphEdge, GraphNode

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
