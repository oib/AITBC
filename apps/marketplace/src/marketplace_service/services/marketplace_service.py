"""
Marketplace service for managing marketplace operations
"""

import time
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from aitbc import get_logger

from ..domain.marketplace import MarketplaceOffer, ServiceRating, SoftwareService

logger = get_logger(__name__)


class MarketplaceService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_offers(
        self,
        status: str | None = None,
        region: str | None = None,
        gpu_model: str | None = None,
    ) -> list[dict]:
        """List marketplace offers"""
        try:
            logger.info(f"list_offers called with filters: status={status}, region={region}, gpu_model={gpu_model}")
            stmt = select(MarketplaceOffer)
            if status:
                stmt = stmt.where(MarketplaceOffer.status == status)
            if region:
                stmt = stmt.where(MarketplaceOffer.region == region)
            if gpu_model:
                stmt = stmt.where(MarketplaceOffer.gpu_model == gpu_model)
            logger.info("Executing database query for offers")
            result = list((await self.session.execute(stmt)).all())
            logger.info(f"Retrieved {len(result)} offers")
            # Convert SQLAlchemy model objects to dictionaries for JSON serialization
            offers_list = []
            for row in result:
                offer = row[0] if row else None
                if offer:
                    offers_list.append({
                        'id': offer.id,
                        'provider': offer.provider,
                        'capacity': offer.capacity,
                        'price': offer.price,
                        'sla': offer.sla,
                        'status': offer.status,
                        'created_at': offer.created_at.isoformat() if offer.created_at else None,
                        'attributes': offer.attributes,
                        'gpu_model': offer.gpu_model,
                        'gpu_memory_gb': offer.gpu_memory_gb,
                        'gpu_count': offer.gpu_count,
                        'cuda_version': offer.cuda_version,
                        'price_per_hour': offer.price_per_hour,
                        'region': offer.region,
                    })
            logger.info(f"Converted {len(offers_list)} offers to dictionaries")
            return offers_list
        except Exception as e:
            logger.error(f"Error in list_offers: {type(e).__name__}: {str(e)}")
            raise

    async def get_offer(self, offer_id: str) -> MarketplaceOffer | None:
        """Get a specific marketplace offer"""
        try:
            logger.info(f"get_offer called with offer_id={offer_id}")
            stmt = select(MarketplaceOffer).where(MarketplaceOffer.id == offer_id)
            result = (await self.session.execute(stmt)).first()
            offer = result[0] if result else None
            logger.info(f"Retrieved offer: {offer_id}, found: {offer is not None}")
            return offer
        except Exception as e:
            logger.error(f"Error in get_offer: {type(e).__name__}: {str(e)}")
            raise

    async def book_offer(self, offer_id: str, booking_data: dict) -> dict:
        """Book/purchase a marketplace offer"""
        try:
            logger.info(f"book_offer called with offer_id={offer_id}, data keys: {booking_data.keys()}")
            offer = await self.get_offer(offer_id)
            if not offer:
                logger.error(f"Offer not found: {offer_id}")
                raise ValueError(f"Offer not found: {offer_id}")

            # Create a bid for the offer
            bid_data = {
                'provider': booking_data.get('wallet') or 'unknown',
                'capacity': booking_data.get('duration_hours', 1.0),
                'price': booking_data.get('price', offer.price),
                'status': 'pending',
            }

            bid = await self.create_bid(bid_data)
            logger.info(f"Created bid for offer {offer_id}: {bid.id}")

            return {
                'bid_id': bid.id,
                'offer_id': offer_id,
                'provider': offer.provider,
                'status': 'pending',
                'message': 'Bid created successfully',
                'escrow_contract_id': None,
            }
        except Exception as e:
            logger.error(f"Error in book_offer: {type(e).__name__}: {str(e)}")
            raise

    async def create_offer(self, offer_data: dict) -> MarketplaceOffer:
        """Create a new marketplace offer"""
        try:
            logger.info(f"create_offer called with data keys: {offer_data.keys()}")
            # Map wallet to provider for CLI compatibility
            if 'wallet' in offer_data and 'provider' not in offer_data:
                offer_data['provider'] = offer_data['wallet']
                logger.info(f"Mapped wallet '{offer_data['wallet']}' to provider")
            offer = MarketplaceOffer(**offer_data)
            self.session.add(offer)
            await self.session.commit()
            await self.session.refresh(offer)
            logger.info(f"Created offer with id: {offer.id}")
            return offer
        except Exception as e:
            logger.error(f"Error in create_offer: {type(e).__name__}: {str(e)}")
            raise

    
    async def get_analytics(self, period_type: str = "daily") -> dict[str, Any]:
        """Get marketplace analytics"""
        from sqlalchemy import func, select

        # Count offers
        offer_count_stmt = select(func.count()).select_from(MarketplaceOffer)
        offer_count_result = await self.session.execute(offer_count_stmt)
        total_offers = offer_count_result.scalar() or 0

        # Average price of offers
        avg_price_stmt = select(func.avg(MarketplaceOffer.price_per_hour)).where(
            MarketplaceOffer.price_per_hour.isnot(None)
        )
        avg_price_result = await self.session.execute(avg_price_stmt)
        avg_price = avg_price_result.scalar() or 0.0

        # Total capacity
        capacity_stmt = select(func.sum(MarketplaceOffer.capacity))
        capacity_result = await self.session.execute(capacity_stmt)
        total_capacity = capacity_result.scalar() or 0

        return {
            "period_type": period_type,
            "total_offers": total_offers,
            "total_capacity": total_capacity,
            "average_price": round(float(avg_price), 2),
        }

    async def list_plugins(self, type: str | None = None, status: str = "approved") -> list[dict]:
        """List plugins from database"""
        from sqlalchemy import select

        from ..domain.marketplace import Plugin

        try:
            stmt = select(Plugin)
            if type:
                stmt = stmt.where(Plugin.type == type)
            if status:
                stmt = stmt.where(Plugin.status == status)
            stmt = stmt.order_by(Plugin.created_at.desc())

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
            logger.error(f"Error in list_plugins: {type(e).__name__}: {str(e)}")
            raise

    async def register_plugin(self, plugin_data: dict) -> dict:
        """Register a new plugin"""
        from ..domain.marketplace import Plugin

        try:
            plugin = Plugin(**plugin_data)
            self.session.add(plugin)
            await self.session.commit()
            await self.session.refresh(plugin)
            logger.info(f"Registered plugin with id: {plugin.id}")
            return {
                "id": plugin.id,
                "name": plugin.name,
                "status": plugin.status,
            }
        except Exception as e:
            logger.error(f"Error in register_plugin: {type(e).__name__}: {str(e)}")
            raise

    async def list_software_services(self, service_type: str | None = None, status: str | None = None) -> list:
        """List software services with optional filters"""
        from ..domain.marketplace import SoftwareService
        from sqlalchemy import select

        try:
            query = select(SoftwareService)
            if service_type:
                query = query.where(SoftwareService.service_type == service_type)
            if status:
                query = query.where(SoftwareService.status == status)
            
            result = await self.session.execute(query)
            services = result.scalars().all()
            
            return [{
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
            } for s in services]
        except Exception as e:
            logger.error(f"Error in list_software_services: {type(e).__name__}: {str(e)}")
            raise

    async def get_software_service(self, plugin_id: str) -> dict | None:
        """Get a specific software service"""
        from ..domain.marketplace import SoftwareService
        from sqlalchemy import select

        try:
            query = select(SoftwareService).where(SoftwareService.plugin_id == plugin_id)
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
            logger.error(f"Error in get_software_service: {type(e).__name__}: {str(e)}")
            raise

    async def register_software_service(self, data: dict) -> dict:
        """Register or update a software service"""
        from ..domain.marketplace import SoftwareService
        from sqlalchemy import select
        from datetime import datetime

        try:
            # Auto-generate plugin_id if not provided
            plugin_id = data.get("plugin_id")
            if not plugin_id:
                service_type = data.get("service_type", "unknown")
                model = data.get("model", "")
                plugin_id = f"{service_type}-{model}".strip("-").replace(":", "-").replace("/", "-")
            
            # Check if exists
            query = select(SoftwareService).where(SoftwareService.plugin_id == plugin_id)
            result = await self.session.execute(query)
            existing = result.scalar_one_or_none()
            
            if existing:
                # Update existing
                for key, value in data.items():
                    if hasattr(existing, key) and value is not None:
                        setattr(existing, key, value)
                existing.updated_at = datetime.utcnow()
                await self.session.commit()
                await self.session.refresh(existing)
                logger.info(f"Updated software service: {plugin_id}")
            else:
                # Create new
                data["plugin_id"] = plugin_id
                service = SoftwareService(**data)
                self.session.add(service)
                await self.session.commit()
                await self.session.refresh(service)
                existing = service
                logger.info(f"Registered software service: {plugin_id}")
            
            return {
                "plugin_id": existing.plugin_id,
                "service_type": existing.service_type,
                "model": existing.model,
                "status": existing.status,
            }
        except Exception as e:
            logger.error(f"Error in register_software_service: {type(e).__name__}: {str(e)}")
            raise

    async def unregister_software_service(self, plugin_id: str) -> dict:
        """Unregister a software service"""
        from ..domain.marketplace import SoftwareService
        from sqlalchemy import select

        try:
            query = select(SoftwareService).where(SoftwareService.plugin_id == plugin_id)
            result = await self.session.execute(query)
            service = result.scalar_one_or_none()
            
            if not service:
                return {"error": "Service not found"}, 404
            
            await self.session.delete(service)
            await self.session.commit()
            logger.info(f"Unregistered software service: {plugin_id}")
            
            return {"plugin_id": plugin_id, "status": "unregistered"}
        except Exception as e:
            logger.error(f"Error in unregister_software_service: {type(e).__name__}: {str(e)}")
            raise

    async def create_graph(self, graph_data: dict) -> dict:
        """Create a new knowledge graph"""
        from ..domain.marketplace import KnowledgeGraph

        try:
            graph = KnowledgeGraph(**graph_data)
            self.session.add(graph)
            await self.session.commit()
            await self.session.refresh(graph)
            logger.info(f"Created graph with id: {graph.id}")
            return {
                "id": graph.id,
                "name": graph.name,
                "status": graph.status,
            }
        except Exception as e:
            logger.error(f"Error in create_graph: {type(e).__name__}: {str(e)}")
            raise

    async def add_node(self, node_data: dict) -> dict:
        """Add a node to a knowledge graph"""
        from ..domain.marketplace import GraphNode

        try:
            node = GraphNode(**node_data)
            self.session.add(node)
            await self.session.commit()
            await self.session.refresh(node)
            logger.info(f"Added node with id: {node.id} to graph: {node.graph_id}")
            return {
                "id": node.id,
                "graph_id": node.graph_id,
                "label": node.label,
            }
        except Exception as e:
            logger.error(f"Error in add_node: {type(e).__name__}: {str(e)}")
            raise

    async def add_edge(self, edge_data: dict) -> dict:
        """Add an edge to a knowledge graph"""
        from ..domain.marketplace import GraphEdge

        try:
            edge = GraphEdge(**edge_data)
            self.session.add(edge)
            await self.session.commit()
            await self.session.refresh(edge)
            logger.info(f"Added edge with id: {edge.id} to graph: {edge.graph_id}")
            return {
                "id": edge.id,
                "graph_id": edge.graph_id,
                "source_node_id": edge.source_node_id,
                "target_node_id": edge.target_node_id,
            }
        except Exception as e:
            logger.error(f"Error in add_edge: {type(e).__name__}: {str(e)}")
            raise

    async def query_graph(self, graph_id: str) -> dict:
        """Query a knowledge graph (get all nodes and edges)"""
        from sqlalchemy import select

        from ..domain.marketplace import GraphEdge, GraphNode

        try:
            # Get nodes
            node_stmt = select(GraphNode).where(GraphNode.graph_id == graph_id)
            node_result = await self.session.execute(node_stmt)
            nodes = node_result.scalars().all()

            # Get edges
            edge_stmt = select(GraphEdge).where(GraphEdge.graph_id == graph_id)
            edge_result = await self.session.execute(edge_stmt)
            edges = edge_result.scalars().all()

            return {
                "graph_id": graph_id,
                "nodes": [
                    {
                        "id": n.id,
                        "node_type": n.node_type,
                        "label": n.label,
                        "properties": n.properties,
                    }
                    for n in nodes
                ],
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
            logger.error(f"Error in query_graph: {type(e).__name__}: {str(e)}")
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
                logger.info(f"Updated offer {offer_id} status to {status}")
            
            return offer
        except Exception as e:
            logger.error(f"Error in update_offer_status: {type(e).__name__}: {str(e)}")
            raise

    def get_current_timestamp(self) -> int:
        """Get current Unix timestamp"""
        return int(time.time())

    async def add_service_rating(self, service_id: str, rating: float, reviewer_id: str, comment: str = "", source_node: str = "local") -> ServiceRating:
        """Add a service rating and update service average rating"""
        try:
            # Validate rating scale (1-5)
            if not (1.0 <= rating <= 5.0):
                raise ValueError("Rating must be between 1.0 and 5.0")

            # Create rating record
            service_rating = ServiceRating(
                service_id=service_id,
                rating=rating,
                reviewer_id=reviewer_id,
                comment=comment,
                source_node=source_node
            )
            self.session.add(service_rating)
            await self.session.commit()
            await self.session.refresh(service_rating)
            logger.info(f"Added rating {rating} for service {service_id} by reviewer {reviewer_id} from {source_node}")

            # Update service average rating
            await self._update_service_rating(service_id)

            return service_rating
        except Exception as e:
            logger.error(f"Error in add_service_rating: {type(e).__name__}: {str(e)}")
            raise

    async def get_service_ratings(self, service_id: str, limit: int = 50, offset: int = 0) -> list[dict]:
        """Get ratings for a specific service"""
        try:
            from sqlalchemy import select

            stmt = select(ServiceRating).where(ServiceRating.service_id == service_id)
            stmt = stmt.order_by(ServiceRating.created_at.desc())
            stmt = stmt.limit(limit).offset(offset)

            result = await self.session.execute(stmt)
            ratings = result.scalars().all()

            return [{
                "id": r.id,
                "service_id": r.service_id,
                "rating": r.rating,
                "reviewer_id": r.reviewer_id,
                "comment": r.comment,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "source_node": r.source_node,
            } for r in ratings]
        except Exception as e:
            logger.error(f"Error in get_service_ratings: {type(e).__name__}: {str(e)}")
            raise

    async def get_unsynced_ratings(self, limit: int = 100) -> list[dict]:
        """Get ratings that haven't been synced yet"""
        try:
            from sqlalchemy import select

            stmt = select(ServiceRating).where(ServiceRating.synced_at.is_(None)).limit(limit)
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
            logger.error(f"Error in get_unsynced_ratings: {type(e).__name__}: {str(e)}")
            raise

    async def mark_ratings_synced(self, rating_ids: list[str]) -> int:
        """Mark ratings as synced"""
        try:
            from sqlalchemy import select
            from datetime import datetime

            stmt = select(ServiceRating).where(ServiceRating.id.in_(rating_ids))
            result = await self.session.execute(stmt)
            ratings = result.scalars().all()

            for rating in ratings:
                rating.synced_at = datetime.utcnow()

            await self.session.commit()
            logger.info(f"Marked {len(ratings)} ratings as synced")
            return len(ratings)
        except Exception as e:
            logger.error(f"Error in mark_ratings_synced: {type(e).__name__}: {str(e)}")
            raise

    async def sync_ratings_from_remote(self, remote_ratings: list[dict]) -> dict:
        """Sync ratings from remote node"""
        try:
            from sqlalchemy import select
            from datetime import datetime

            synced_count = 0
            updated_count = 0
            skipped_count = 0

            for remote_rating in remote_ratings:
                # Check if rating already exists
                stmt = select(ServiceRating).where(
                    ServiceRating.service_id == remote_rating["service_id"],
                    ServiceRating.reviewer_id == remote_rating["reviewer_id"],
                )
                result = await self.session.execute(stmt)
                existing = result.scalar_one_or_none()

                if existing:
                    # Conflict resolution: keep the most recent rating
                    remote_created = datetime.fromisoformat(remote_rating["created_at"])
                    if remote_created > existing.created_at:
                        existing.rating = remote_rating["rating"]
                        existing.comment = remote_rating["comment"]
                        existing.synced_at = datetime.utcnow()
                        updated_count += 1
                    else:
                        skipped_count += 1
                else:
                    # Create new rating from remote
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
            logger.info(f"Synced {synced_count} new, updated {updated_count}, skipped {skipped_count} ratings")

            # Update service averages
            for remote_rating in remote_ratings:
                await self._update_service_rating(remote_rating["service_id"])

            return {
                "synced": synced_count,
                "updated": updated_count,
                "skipped": skipped_count,
            }
        except Exception as e:
            logger.error(f"Error in sync_ratings_from_remote: {type(e).__name__}: {str(e)}")
            raise

    async def _update_service_rating(self, service_id: str) -> None:
        """Calculate and update service average rating"""
        try:
            from sqlalchemy import func, select

            # Get all ratings for the service
            stmt = select(func.avg(ServiceRating.rating), func.count(ServiceRating.id))
            stmt = stmt.where(ServiceRating.service_id == service_id)
            result = await self.session.execute(stmt)
            avg_rating, count = result.first()

            # Update service record (try plugin_id first, then offer_id)
            service_stmt = select(SoftwareService).where(SoftwareService.plugin_id == service_id)
            service_result = await self.session.execute(service_stmt)
            service = service_result.scalar_one_or_none()
            
            if not service:
                # Try to find by offer_id
                service_stmt = select(SoftwareService).where(SoftwareService.offer_id == service_id)
                service_result = await self.session.execute(service_stmt)
                service = service_result.scalar_one_or_none()

            if service:
                service.avg_rating = float(avg_rating) if avg_rating else 0.0
                service.rating_count = int(count) if count else 0
                await self.session.commit()
                logger.info(f"Updated service {service_id} rating: avg={service.avg_rating}, count={service.rating_count}")
        except Exception as e:
            logger.error(f"Error in _update_service_rating: {type(e).__name__}: {str(e)}")
            raise

    async def get_service_by_offer_id(self, offer_id: str) -> dict | None:
        """Get a software service by offer_id"""
        from sqlalchemy import select

        try:
            stmt = select(SoftwareService).where(SoftwareService.offer_id == offer_id)
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
            logger.error(f"Error in get_service_by_offer_id: {type(e).__name__}: {str(e)}")
            raise
