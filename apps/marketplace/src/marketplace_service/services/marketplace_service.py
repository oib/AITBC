"""
Marketplace service for managing marketplace operations
"""

import time
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from aitbc.aitbc_logging import get_logger

from ..domain.marketplace import MarketplaceOffer, ServiceRating, SoftwareService

logger = get_logger(__name__)


class MarketplaceService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_offers(
        self, status: str | None = None, region: str | None = None, gpu_model: str | None = None
    ) -> list[dict[str, Any]]:
        """List marketplace offers"""
        try:
            logger.info("list_offers called with filters: status=%s, region=%s, gpu_model=%s", status, region, gpu_model)
            stmt = select(MarketplaceOffer)
            if status:
                stmt = stmt.where(MarketplaceOffer.status == status)
            if region:
                stmt = stmt.where(MarketplaceOffer.region == region)
            if gpu_model:
                stmt = stmt.where(MarketplaceOffer.gpu_model == gpu_model)
            logger.info("Executing database query for offers")
            result = list((await self.session.execute(stmt)).all())
            logger.info("Retrieved %s offers", len(result))
            offers_list = []
            for row in result:
                offer = row[0] if row else None
                if offer:
                    offers_list.append(
                        {
                            "id": offer.id,
                            "provider": offer.provider,
                            "capacity": offer.capacity,
                            "price": offer.price,
                            "sla": offer.sla,
                            "status": offer.status,
                            "created_at": offer.created_at.isoformat() if offer.created_at else None,
                            "attributes": offer.attributes,
                            "gpu_model": offer.gpu_model,
                            "gpu_memory_gb": offer.gpu_memory_gb,
                            "gpu_count": offer.gpu_count,
                            "cuda_version": offer.cuda_version,
                            "price_per_hour": offer.price_per_hour,
                            "region": offer.region,
                        }
                    )
            logger.info("Converted %s offers to dictionaries", len(offers_list))
            return offers_list
        except Exception as e:
            logger.error("Error in list_offers: %s: %s", type(e).__name__, str(e))
            raise

    async def get_offer(self, offer_id: str) -> MarketplaceOffer | None:
        """Get a specific marketplace offer"""
        try:
            logger.info("get_offer called with offer_id=%s", offer_id)
            stmt = select(MarketplaceOffer).where(MarketplaceOffer.id == offer_id)
            result = (await self.session.execute(stmt)).first()
            offer = result[0] if result else None
            logger.info("Retrieved offer: %s, found: %s", offer_id, offer is not None)
            return offer
        except Exception as e:
            logger.error("Error in get_offer: %s: %s", type(e).__name__, str(e))
            raise

    async def book_offer(self, offer_id: str, booking_data: dict[str, Any]) -> dict[str, Any]:
        """Book/purchase a marketplace offer"""
        try:
            logger.info("book_offer called with offer_id=%s, data keys: %s", offer_id, booking_data.keys())
            offer = await self.get_offer(offer_id)
            if not offer:
                logger.error("Offer not found: %s", offer_id)
                raise ValueError(f"Offer not found: {offer_id}")
            bid_data = {
                "provider": booking_data.get("wallet") or "unknown",
                "capacity": booking_data.get("duration_hours", 1.0),
                "price": booking_data.get("price", offer.price),
                "status": "pending",
            }
            bid = await self._create_bid(bid_data)
            logger.info("Created bid for offer %s: %s", offer_id, bid.id)
            return {
                "bid_id": bid.id,
                "offer_id": offer_id,
                "provider": offer.provider,
                "status": "pending",
                "message": "Bid created successfully",
                "escrow_contract_id": None,
            }
        except Exception as e:
            logger.error("Error in book_offer: %s: %s", type(e).__name__, str(e))
            raise

    async def create_offer(self, offer_data: dict[str, Any]) -> MarketplaceOffer:
        """Create a new marketplace offer"""
        try:
            logger.info("create_offer called with data keys: %s", offer_data.keys())
            if "wallet" in offer_data and "provider" not in offer_data:
                offer_data["provider"] = offer_data["wallet"]
                logger.info("Mapped wallet '%s' to provider", offer_data["wallet"])
            offer = MarketplaceOffer(**offer_data)
            self.session.add(offer)
            await self.session.commit()
            await self.session.refresh(offer)
            logger.info("Created offer with id: %s", offer.id)
            return offer
        except Exception as e:
            logger.error("Error in create_offer: %s: %s", type(e).__name__, str(e))
            raise

    async def get_analytics(self, period_type: str = "daily") -> dict[str, Any]:
        """Get marketplace analytics"""
        from sqlalchemy import func, select

        offer_count_stmt = select(func.count()).select_from(MarketplaceOffer)
        offer_count_result = await self.session.execute(offer_count_stmt)
        total_offers = offer_count_result.scalar() or 0
        avg_price_stmt = select(func.avg(MarketplaceOffer.price_per_hour)).where(MarketplaceOffer.price_per_hour.isnot(None))  # type: ignore[union-attr]
        avg_price_result = await self.session.execute(avg_price_stmt)
        avg_price = avg_price_result.scalar() or 0.0
        capacity_stmt = select(func.sum(MarketplaceOffer.capacity))
        capacity_result = await self.session.execute(capacity_stmt)
        total_capacity = capacity_result.scalar() or 0
        return {
            "period_type": period_type,
            "total_offers": total_offers,
            "total_capacity": total_capacity,
            "average_price": round(float(avg_price), 2),
        }

    async def list_plugins(self, plugin_type: str | None = None, status: str = "approved") -> list[dict[str, Any]]:
        """List plugins from database"""
        from sqlalchemy import select

        from ..domain.marketplace import Plugin

        try:
            stmt = select(Plugin)
            if plugin_type:
                stmt = stmt.where(Plugin.type == plugin_type)  # type: ignore[arg-type]
            if status:
                stmt = stmt.where(Plugin.status == status)  # type: ignore[arg-type]
            stmt = stmt.order_by(Plugin.created_at.desc())  # type: ignore[attr-defined]
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
        from ..domain.marketplace import Plugin

        try:
            plugin = Plugin(**plugin_data)
            self.session.add(plugin)
            await self.session.commit()
            await self.session.refresh(plugin)
            logger.info("Registered plugin with id: %s", plugin.id)
            return {"id": plugin.id, "name": plugin.name, "status": plugin.status}
        except Exception as e:
            logger.error("Error in register_plugin: %s: %s", type(e).__name__, str(e))
            raise

    async def list_software_services(self, service_type: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
        """List software services with optional filters"""
        from sqlalchemy import select

        from ..domain.marketplace import SoftwareService

        try:
            query = select(SoftwareService)
            if service_type:
                query = query.where(SoftwareService.service_type == service_type)  # type: ignore[arg-type]
            if status:
                query = query.where(SoftwareService.status == status)  # type: ignore[arg-type]
            result = await self.session.execute(query)
            services = result.scalars().all()
            return [
                {
                    "plugin_id": s.plugin_id,
                    "service_type": s.service_type,
                    "model": s.model,
                    "price": s.price,
                    "price_unit": s.price_unit,
                    "offer_id": s.offer_id,
                    "endpoint": s.endpoint,
                    "public_endpoint": s.public_endpoint,
                    "health_url": s.health_url,
                    "provider_address": s.provider_address,
                    "node_id": s.node_id,
                    "gpu_name": s.gpu_name,
                    "gpu_device": s.gpu_device,
                    "gpu_uuid": s.gpu_uuid,
                    "gpu_offer_id": s.gpu_offer_id,
                    "description": s.description,
                    "status": s.status,
                    "registered_at": s.registered_at.isoformat() if s.registered_at else None,
                    "updated_at": s.updated_at.isoformat() if s.updated_at else None,
                    "avg_rating": s.avg_rating,
                    "rating_count": s.rating_count,
                }
                for s in services
            ]
        except Exception as e:
            logger.error("Error in list_software_services: %s: %s", type(e).__name__, str(e))
            raise

    async def get_software_service(self, plugin_id: str) -> dict[str, Any] | None:
        """Get a specific software service"""
        from sqlalchemy import select

        from ..domain.marketplace import SoftwareService

        try:
            query = select(SoftwareService).where(SoftwareService.plugin_id == plugin_id)  # type: ignore[arg-type]
            result = await self.session.execute(query)
            service = result.scalar_one_or_none()
            if not service:
                return None
            return {
                "plugin_id": service.plugin_id,
                "service_type": service.service_type,
                "model": service.model,
                "price": service.price,
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
                "description": service.description,
                "status": service.status,
                "registered_at": service.registered_at.isoformat() if service.registered_at else None,
                "updated_at": service.updated_at.isoformat() if service.updated_at else None,
                "avg_rating": service.avg_rating,
                "rating_count": service.rating_count,
            }
        except Exception as e:
            logger.error("Error in get_software_service: %s: %s", type(e).__name__, str(e))
            raise

    async def register_software_service(self, data: dict[str, Any]) -> dict[str, Any]:
        """Register or update a software service"""
        from datetime import datetime

        from sqlalchemy import select

        from ..domain.marketplace import SoftwareService

        try:
            plugin_id = data.get("plugin_id")
            if not plugin_id:
                service_type = data.get("service_type", "unknown")
                model = data.get("model", "")
                plugin_id = f"{service_type}-{model}".strip("-").replace(":", "-").replace("/", "-")
            query = select(SoftwareService).where(SoftwareService.plugin_id == plugin_id)  # type: ignore[arg-type]
            result = await self.session.execute(query)
            existing = result.scalar_one_or_none()
            if existing:
                for key, value in data.items():
                    if hasattr(existing, key) and value is not None:
                        setattr(existing, key, value)
                existing.updated_at = datetime.utcnow()
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
        except Exception as e:
            logger.error("Error in register_software_service: %s: %s", type(e).__name__, str(e))
            raise

    async def unregister_software_service(self, plugin_id: str) -> Any:
        """Unregister a software service"""
        from sqlalchemy import select

        from ..domain.marketplace import SoftwareService

        try:
            query = select(SoftwareService).where(SoftwareService.plugin_id == plugin_id)  # type: ignore[arg-type]
            result = await self.session.execute(query)
            service = result.scalar_one_or_none()
            if not service:
                return ({"error": "Service not found"}, 404)
            await self.session.delete(service)
            await self.session.commit()
            logger.info("Unregistered software service: %s", plugin_id)
            return {"plugin_id": plugin_id, "status": "unregistered"}
        except Exception as e:
            logger.error("Error in unregister_software_service: %s: %s", type(e).__name__, str(e))
            raise

    async def create_graph(self, graph_data: dict[str, Any]) -> dict[str, Any]:
        """Create a new knowledge graph"""
        from ..domain.marketplace import KnowledgeGraph

        try:
            graph = KnowledgeGraph(**graph_data)
            self.session.add(graph)
            await self.session.commit()
            await self.session.refresh(graph)
            logger.info("Created graph with id: %s", graph.id)
            return {"id": graph.id, "name": graph.name, "status": graph.status}
        except Exception as e:
            logger.error("Error in create_graph: %s: %s", type(e).__name__, str(e))
            raise

    async def add_node(self, node_data: dict[str, Any]) -> dict[str, Any]:
        """Add a node to a knowledge graph"""
        from ..domain.marketplace import GraphNode

        try:
            node = GraphNode(**node_data)
            self.session.add(node)
            await self.session.commit()
            await self.session.refresh(node)
            logger.info("Added node with id: %s to graph: %s", node.id, node.graph_id)
            return {"id": node.id, "graph_id": node.graph_id, "label": node.label}
        except Exception as e:
            logger.error("Error in add_node: %s: %s", type(e).__name__, str(e))
            raise

    async def add_edge(self, edge_data: dict[str, Any]) -> dict[str, Any]:
        """Add an edge to a knowledge graph"""
        from ..domain.marketplace import GraphEdge

        try:
            edge = GraphEdge(**edge_data)
            self.session.add(edge)
            await self.session.commit()
            await self.session.refresh(edge)
            logger.info("Added edge with id: %s to graph: %s", edge.id, edge.graph_id)
            return {
                "id": edge.id,
                "graph_id": edge.graph_id,
                "source_node_id": edge.source_node_id,
                "target_node_id": edge.target_node_id,
            }
        except Exception as e:
            logger.error("Error in add_edge: %s: %s", type(e).__name__, str(e))
            raise

    async def query_graph(self, graph_id: str) -> dict[str, Any]:
        """Query a knowledge graph (get all nodes and edges)"""
        from sqlalchemy import select

        from ..domain.marketplace import GraphEdge, GraphNode

        try:
            node_stmt = select(GraphNode).where(GraphNode.graph_id == graph_id)  # type: ignore[arg-type]
            node_result = await self.session.execute(node_stmt)
            nodes = node_result.scalars().all()
            edge_stmt = select(GraphEdge).where(GraphEdge.graph_id == graph_id)  # type: ignore[arg-type]
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

    async def update_offer_status(self, offer_id: str, status: str) -> MarketplaceOffer | None:
        """Update offer status"""
        try:
            stmt = select(MarketplaceOffer).where(MarketplaceOffer.id == offer_id)
            result = await self.session.execute(stmt)
            offer = result.scalars().first()
            if offer:
                offer.status = status
                await self.session.commit()
                await self.session.refresh(offer)
                logger.info("Updated offer %s status to %s", offer_id, status)
            return offer
        except Exception as e:
            logger.error("Error in update_offer_status: %s: %s", type(e).__name__, str(e))
            raise

    async def _create_bid(self, bid_data: dict[str, Any]) -> Any:
        """Create a bid record (simple stub for internal use)"""
        try:
            # Create a simple bid-like object
            class Bid:
                def __init__(self, data: dict[str, Any]) -> None:
                    self.id: str = data.get("provider", "unknown") + "-" + str(int(time.time()))
                    self.provider: str | None = data.get("provider")
                    self.capacity: float | None = data.get("capacity")
                    self.price: float | None = data.get("price")
                    self.status: str | None = data.get("status")

            bid = Bid(bid_data)
            logger.info("Created internal bid: %s", bid.id)
            return bid
        except Exception as e:
            logger.error("Error in _create_bid: %s: %s", type(e).__name__, str(e))
            raise

    def get_current_timestamp(self) -> int:
        """Get current Unix timestamp"""
        return int(time.time())

    async def add_service_rating(
        self, service_id: str, rating: float, reviewer_id: str, comment: str = "", source_node: str = "local"
    ) -> ServiceRating:
        """Add a service rating and update service average rating"""
        try:
            if not 1.0 <= rating <= 5.0:
                raise ValueError("Rating must be between 1.0 and 5.0")
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

            stmt = select(ServiceRating).where(ServiceRating.synced_at.is_(None)).limit(limit)  # type: ignore[union-attr]
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
            from datetime import datetime

            from sqlalchemy import select

            stmt = select(ServiceRating).where(ServiceRating.id.in_(rating_ids))  # type: ignore[attr-defined]
            result = await self.session.execute(stmt)
            ratings = result.scalars().all()
            for rating in ratings:
                rating.synced_at = datetime.utcnow()
            await self.session.commit()
            logger.info("Marked %s ratings as synced", len(ratings))
            return len(ratings)
        except Exception as e:
            logger.error("Error in mark_ratings_synced: %s: %s", type(e).__name__, str(e))
            raise

    async def sync_ratings_from_remote(self, remote_ratings: list[dict[str, Any]]) -> dict[str, Any]:
        """Sync ratings from remote node"""
        try:
            from datetime import datetime

            from sqlalchemy import select

            synced_count = 0
            updated_count = 0
            skipped_count = 0
            for remote_rating in remote_ratings:
                stmt = select(ServiceRating).where(
                    ServiceRating.service_id == remote_rating["service_id"],
                    ServiceRating.reviewer_id == remote_rating["reviewer_id"],
                )
                result = await self.session.execute(stmt)
                existing = result.scalar_one_or_none()
                if existing:
                    remote_created = datetime.fromisoformat(remote_rating["created_at"])
                    if remote_created > existing.created_at:
                        existing.rating = remote_rating["rating"]
                        existing.comment = remote_rating["comment"]
                        existing.synced_at = datetime.utcnow()
                        updated_count += 1
                    else:
                        skipped_count += 1
                else:
                    new_rating = ServiceRating(
                        id=remote_rating["id"],
                        service_id=remote_rating["service_id"],
                        rating=remote_rating["rating"],
                        reviewer_id=remote_rating["reviewer_id"],
                        comment=remote_rating["comment"],
                        created_at=datetime.fromisoformat(remote_rating["created_at"]),
                        synced_at=datetime.utcnow(),
                        source_node=remote_rating.get("source_node", "remote"),
                    )
                    self.session.add(new_rating)
                    synced_count += 1
            await self.session.commit()
            logger.info("Synced %s new, updated %s, skipped %s ratings", synced_count, updated_count, skipped_count)
            for remote_rating in remote_ratings:
                await self._update_service_rating(remote_rating["service_id"])
            return {"synced": synced_count, "updated": updated_count, "skipped": skipped_count}
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
                "price": service.price,
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
