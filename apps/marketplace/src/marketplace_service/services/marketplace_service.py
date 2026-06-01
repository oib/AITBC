"""
Marketplace service for managing marketplace operations
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from aitbc import get_logger

from marketplace_service.marketplace import MarketplaceBid, MarketplaceOffer

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
                'status': 'pending',
                'message': 'Bid created successfully'
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

    async def list_bids(
        self,
        status: str | None = None,
        provider: str | None = None,
    ) -> list[dict]:
        """List marketplace bids"""
        try:
            logger.info(f"list_bids called with filters: status={status}, provider={provider}")
            stmt = select(MarketplaceBid)
            if status:
                stmt = stmt.where(MarketplaceBid.status == status)
            if provider:
                stmt = stmt.where(MarketplaceBid.provider == provider)
            logger.info("Executing database query for bids")
            result = list((await self.session.execute(stmt)).all())
            logger.info(f"Retrieved {len(result)} bids")
            # Convert SQLAlchemy model objects to dictionaries for JSON serialization
            bids_list = []
            for row in result:
                bid = row[0] if row else None
                if bid:
                    bids_list.append({
                        'id': bid.id,
                        'provider': bid.provider,
                        'capacity': bid.capacity,
                        'price': bid.price,
                        'notes': bid.notes,
                        'status': bid.status,
                        'submitted_at': bid.submitted_at.isoformat() if bid.submitted_at else None,
                    })
            logger.info(f"Converted {len(bids_list)} bids to dictionaries")
            return bids_list
        except Exception as e:
            logger.error(f"Error in list_bids: {type(e).__name__}: {str(e)}")
            raise

    async def create_bid(self, bid_data: dict) -> MarketplaceBid:
        """Create a new marketplace bid"""
        try:
            logger.info(f"create_bid called with data keys: {bid_data.keys()}")
            bid = MarketplaceBid(**bid_data)
            self.session.add(bid)
            await self.session.commit()
            await self.session.refresh(bid)
            logger.info(f"Created bid with id: {bid.id}")
            return bid
        except Exception as e:
            logger.error(f"Error in create_bid: {type(e).__name__}: {str(e)}")
            raise

    async def get_analytics(self, period_type: str = "daily") -> dict[str, Any]:
        """Get marketplace analytics"""
        from sqlalchemy import func, select

        # Count offers
        offer_count_stmt = select(func.count()).select_from(MarketplaceOffer)
        offer_count_result = await self.session.execute(offer_count_stmt)
        total_offers = offer_count_result.scalar() or 0

        # Count bids
        bid_count_stmt = select(func.count()).select_from(MarketplaceBid)
        bid_count_result = await self.session.execute(bid_count_stmt)
        total_bids = bid_count_result.scalar() or 0

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
            "total_bids": total_bids,
            "total_capacity": total_capacity,
            "average_price": round(float(avg_price), 2),
        }

    async def list_plugins(self, type: str | None = None, status: str = "approved") -> list[dict]:
        """List plugins from database"""
        from sqlalchemy import select

        from .domain.marketplace import Plugin

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
        from .domain.marketplace import Plugin

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

    async def create_graph(self, graph_data: dict) -> dict:
        """Create a new knowledge graph"""
        from .domain.marketplace import KnowledgeGraph

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
        from marketplace_service.marketplace import GraphNode

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
        from marketplace_service.marketplace import GraphEdge

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

        from marketplace_service.marketplace import GraphEdge, GraphNode

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
