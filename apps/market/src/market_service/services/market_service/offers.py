"""
MarketService offers/plugins/graph mixin.

The software-service endpoints and the on-chain anchor-resolution cluster
moved verbatim to ``offers_software.py`` (``_OffersSoftwareMixin``); this
module keeps the offer lifecycle, plugin registry, knowledge-graph and bid
methods. ``_OffersMixin`` inherits the software mixin so the
``MarketService`` MRO and every ``self.*`` call are unchanged (issue #1860,
phase 6 band split).
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlmodel import col, select

from aitbc.aitbc_logging import get_logger
from aitbc.market import OfferFSM, OfferStatus

from ...domain.market import Bid, MarketOffer
from ...domain.offer_status import spellings_of, to_offer_status
from .offers_software import _OffersSoftwareMixin
from .shared import (
    _get_by_caller_id,
    _money_decimal,
    _replay_after_integrity_conflict,
    _resolve_bid_price,
    _validate_booking_numbers,
    bid_ttl_seconds,
    coerce_offer_expires_at,
    max_page_size,
    offer_listing_expired,
    offer_reservation_ttl_seconds,
)


logger = get_logger(__name__)


class _OffersMixin(_OffersSoftwareMixin):
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
            # #1914: the effective bid price must be positive and at least the
            # offer's ask — same reason, same window: a zero-price bid would
            # settle on any dust tx in complete_bid.
            _resolve_bid_price(booking_data, offer.price)
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
            # a "completed" bid settles for dust. #1914 adds the positive /
            # at-ask floor; book_offer already ran this before the CAS claim,
            # this is the same check for any other _create_bid caller.
            price = _resolve_bid_price(booking_data, offer.price)
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
