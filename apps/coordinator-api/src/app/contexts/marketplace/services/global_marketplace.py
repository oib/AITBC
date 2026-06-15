from ..domain.global_marketplace import (
    GlobalMarketplaceAnalyticsRequest,
    GlobalMarketplaceOfferRequest,
    GlobalMarketplaceTransactionRequest,
)

'\nGlobal Marketplace Services\nCore services for global marketplace operations, multi-region support, and cross-chain integration\n'
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from aitbc import get_logger

logger = get_logger(__name__)
from sqlalchemy import desc
from sqlmodel import Session, select

from ....reputation.engine import CrossChainReputationEngine
from ...agent_identity.domain.agent_identity import AgentIdentity
from ..domain.global_marketplace import (
    GlobalMarketplaceAnalytics,
    GlobalMarketplaceOffer,
    GlobalMarketplaceTransaction,
    MarketplaceRegion,
    MarketplaceStatus,
    RegionStatus,
)


class GlobalMarketplaceService:
    """Core service for global marketplace operations"""

    def __init__(self, session: Session):
        self.session = session

    async def create_global_offer(self, request: 'GlobalMarketplaceOfferRequest', agent_identity: AgentIdentity) -> GlobalMarketplaceOffer:
        """Create a new global marketplace offer"""
        try:
            reputation_engine = CrossChainReputationEngine(self.session)
            reputation_summary = await reputation_engine.get_agent_reputation_summary(agent_identity.id)
            if reputation_summary.get('trust_score', 0) < 500:
                raise ValueError('Insufficient reputation for global marketplace')
            global_offer = GlobalMarketplaceOffer(original_offer_id=f'offer_{uuid4().hex[:8]}', agent_id=agent_identity.id, service_type=request.service_type, resource_specification=request.resource_specification, base_price=request.base_price, currency=request.currency, total_capacity=request.total_capacity, available_capacity=request.total_capacity, regions_available=request.regions_available or ['global'], supported_chains=request.supported_chains, dynamic_pricing_enabled=request.dynamic_pricing_enabled, expires_at=request.expires_at)
            regions = await self._get_active_regions()
            price_per_region = {}
            for region in regions:
                load_factor = region.load_factor
                regional_price = request.base_price * load_factor
                price_per_region[region.region_code] = regional_price
            global_offer.price_per_region = price_per_region
            region_statuses = {}
            for region_code in global_offer.regions_available:
                region_statuses[region_code] = MarketplaceStatus.ACTIVE
            global_offer.region_statuses = region_statuses
            self.session.add(global_offer)
            self.session.commit()
            self.session.refresh(global_offer)
            logger.info('Created global offer %s for agent %s', global_offer.id, agent_identity.id)
            return global_offer
        except Exception as e:
            logger.error('Error creating global offer: %s', e)
            self.session.rollback()
            raise

    async def get_global_offers(self, region: str | None=None, service_type: str | None=None, status: MarketplaceStatus | None=None, limit: int=100, offset: int=0) -> list[GlobalMarketplaceOffer]:
        """Get global marketplace offers with filtering"""
        try:
            stmt = select(GlobalMarketplaceOffer)
            if service_type:
                stmt = stmt.where(GlobalMarketplaceOffer.service_type == service_type)
            if status:
                stmt = stmt.where(GlobalMarketplaceOffer.global_status == status)
            if region and region != 'global':
                stmt = stmt.where(GlobalMarketplaceOffer.regions_available.contains([region]))  # type: ignore[attr-defined]
            stmt = stmt.order_by(desc(GlobalMarketplaceOffer.created_at)).offset(offset).limit(limit)  # type: ignore[arg-type]
            offers = self.session.execute(stmt).all()
            current_time = datetime.now(UTC)
            valid_offers = []
            for offer in offers:
                if offer.expires_at is None or offer.expires_at > current_time:
                    valid_offers.append(offer)
            return valid_offers # type: ignore[return-value]
        except Exception as e:
            logger.error('Error getting global offers: %s', e)
            raise

    async def create_global_transaction(self, request: 'GlobalMarketplaceTransactionRequest', buyer_identity: AgentIdentity) -> GlobalMarketplaceTransaction:
        """Create a global marketplace transaction"""
        try:
            stmt = select(GlobalMarketplaceOffer).where(GlobalMarketplaceOffer.id == request.offer_id)
            offer = self.session.execute(stmt).first()
            if not offer:
                raise ValueError('Offer not found')
            if offer.available_capacity < request.quantity:
                raise ValueError('Insufficient capacity')
            reputation_engine = CrossChainReputationEngine(self.session)
            buyer_reputation = await reputation_engine.get_agent_reputation_summary(buyer_identity.id)
            if buyer_reputation.get('trust_score', 0) < 300:
                raise ValueError('Insufficient reputation for transactions')
            unit_price = offer.base_price
            total_amount = unit_price * request.quantity
            regional_fees = {}
            if request.source_region != 'global':
                regions = await self._get_active_regions()
                for region in regions:
                    if region.region_code == request.source_region:
                        regional_fees[region.region_code] = total_amount * 0.01
            cross_chain_fee = 0.0
            if request.source_chain and request.target_chain and (request.source_chain != request.target_chain):
                cross_chain_fee = total_amount * 0.005
            transaction = GlobalMarketplaceTransaction(buyer_id=buyer_identity.id, seller_id=offer.agent_id, offer_id=offer.id, service_type=offer.service_type, quantity=request.quantity, unit_price=unit_price, total_amount=total_amount + cross_chain_fee + sum(regional_fees.values()), currency=offer.currency, source_chain=request.source_chain, target_chain=request.target_chain, source_region=request.source_region, target_region=request.target_region, cross_chain_fee=cross_chain_fee, regional_fees=regional_fees, status='pending', payment_status='pending', delivery_status='pending')
            offer.available_capacity -= request.quantity
            offer.total_transactions += 1
            offer.updated_at = datetime.now(UTC)
            self.session.add(transaction)
            self.session.commit()
            self.session.refresh(transaction)
            logger.info('Created global transaction %s for offer %s', transaction.id, offer.id)
            return transaction
        except Exception as e:
            logger.error('Error creating global transaction: %s', e)
            self.session.rollback()
            raise

    async def get_global_transactions(self, user_id: str | None=None, status: str | None=None, limit: int=100, offset: int=0) -> list[GlobalMarketplaceTransaction]:
        """Get global marketplace transactions"""
        try:
            stmt = select(GlobalMarketplaceTransaction)
            if user_id:
                stmt = stmt.where((GlobalMarketplaceTransaction.buyer_id == user_id) | (GlobalMarketplaceTransaction.seller_id == user_id))
            if status:
                stmt = stmt.where(GlobalMarketplaceTransaction.status == status)
            stmt = stmt.order_by(desc(GlobalMarketplaceTransaction.created_at)).offset(offset).limit(limit)  # type: ignore[arg-type]
            transactions = self.session.execute(stmt).all()
            return transactions # type: ignore[return-value]
        except Exception as e:
            logger.error('Error getting global transactions: %s', e)
            raise

    async def get_marketplace_analytics(self, request: 'GlobalMarketplaceAnalyticsRequest') -> GlobalMarketplaceAnalytics:
        """Get global marketplace analytics"""
        try:
            stmt = select(GlobalMarketplaceAnalytics).where(GlobalMarketplaceAnalytics.period_type == request.period_type, GlobalMarketplaceAnalytics.period_start >= request.start_date, GlobalMarketplaceAnalytics.period_end <= request.end_date, GlobalMarketplaceAnalytics.region == request.region)
            existing_analytics = self.session.execute(stmt).first()
            if existing_analytics:
                return existing_analytics # type: ignore[return-value]
            analytics = await self._generate_analytics(request)
            self.session.add(analytics)
            self.session.commit()
            self.session.refresh(analytics)
            return analytics
        except Exception as e:
            logger.error('Error getting marketplace analytics: %s', e)
            raise

    async def _generate_analytics(self, request: 'GlobalMarketplaceAnalyticsRequest') -> GlobalMarketplaceAnalytics:
        """Generate analytics for the specified period"""
        stmt = select(GlobalMarketplaceOffer).where(GlobalMarketplaceOffer.created_at >= request.start_date, GlobalMarketplaceOffer.created_at <= request.end_date)
        if request.region != 'global':
            stmt = stmt.where(GlobalMarketplaceOffer.regions_available.contains([request.region]))  # type: ignore[attr-defined]
        offers = self.session.execute(stmt).all()
        stmt = select(GlobalMarketplaceTransaction).where(GlobalMarketplaceTransaction.created_at >= request.start_date, GlobalMarketplaceTransaction.created_at <= request.end_date)  # type: ignore[assignment]
        if request.region != 'global':
            stmt = stmt.where((GlobalMarketplaceTransaction.source_region == request.region) | (GlobalMarketplaceTransaction.target_region == request.region))
        transactions = self.session.execute(stmt).all()
        total_offers = len(offers)
        total_transactions = len(transactions)
        total_volume = sum(tx.total_amount for tx in transactions)
        average_price = total_volume / max(total_transactions, 1)
        completed_transactions = [tx for tx in transactions if tx.status == 'completed']
        success_rate = len(completed_transactions) / max(total_transactions, 1)
        cross_chain_transactions = [tx for tx in transactions if tx.source_chain and tx.target_chain]
        cross_chain_volume = sum(tx.total_amount for tx in cross_chain_transactions)
        regional_distribution: dict[str, int] = {}
        for tx in transactions:
            region = tx.source_region
            regional_distribution[region] = regional_distribution.get(region, 0) + 1
        analytics = GlobalMarketplaceAnalytics(period_type=request.period_type, period_start=request.start_date, period_end=request.end_date, region=request.region, total_offers=total_offers, total_transactions=total_transactions, total_volume=total_volume, average_price=average_price, success_rate=success_rate, cross_chain_transactions=len(cross_chain_transactions), cross_chain_volume=cross_chain_volume, regional_distribution=regional_distribution)
        return analytics

    async def _get_active_regions(self) -> list[MarketplaceRegion]:
        """Get all active marketplace regions"""
        stmt = select(MarketplaceRegion).where(MarketplaceRegion.status == RegionStatus.ACTIVE)
        regions = self.session.execute(stmt).all()
        return regions # type: ignore[return-value]

    async def get_region_health(self, region_code: str) -> dict[str, Any]:
        """Get health status for a specific region"""
        try:
            stmt = select(MarketplaceRegion).where(MarketplaceRegion.region_code == region_code)
            region = self.session.execute(stmt).first()
            if not region:
                return {'status': 'not_found'}
            health_score = region.health_score
            recent_analytics = await self._get_recent_analytics(region_code)
            return {'status': region.status.value, 'health_score': health_score, 'load_factor': region.load_factor, 'average_response_time': region.average_response_time, 'error_rate': region.error_rate, 'last_health_check': region.last_health_check, 'recent_performance': recent_analytics}
        except Exception as e:
            logger.error('Error getting region health for %s: %s', region_code, e)
            return {'status': 'error', 'error': 'Failed to get region health'}

    async def _get_recent_analytics(self, region: str, hours: int=24) -> dict[str, Any]:
        """Get recent analytics for a region"""
        try:
            cutoff_time = datetime.now(UTC) - timedelta(hours=hours)
            stmt = select(GlobalMarketplaceAnalytics).where(GlobalMarketplaceAnalytics.region == region, GlobalMarketplaceAnalytics.created_at >= cutoff_time).order_by(desc(GlobalMarketplaceAnalytics.created_at))  # type: ignore[arg-type]
            analytics = self.session.execute(stmt).first()
            if analytics:
                return {'total_transactions': analytics.total_transactions, 'success_rate': analytics.success_rate, 'average_response_time': analytics.average_response_time, 'error_rate': analytics.error_rate}
            return {}
        except Exception as e:
            logger.error('Error getting recent analytics for %s: %s', region, e)
            return {}

class RegionManager:
    """Service for managing global marketplace regions"""

    def __init__(self, session: Session):
        self.session = session

    async def create_region(self, region_code: str, region_name: str, configuration: dict[str, Any]) -> MarketplaceRegion:
        """Create a new marketplace region"""
        try:
            region = MarketplaceRegion(region_code=region_code, region_name=region_name, geographic_area=configuration.get('geographic_area', 'global'), base_currency=configuration.get('base_currency', 'USD'), timezone=configuration.get('timezone', 'UTC'), language=configuration.get('language', 'en'), api_endpoint=configuration.get('api_endpoint', ''), websocket_endpoint=configuration.get('websocket_endpoint', ''), blockchain_rpc_endpoints=configuration.get('blockchain_rpc_endpoints', {}), load_factor=configuration.get('load_factor', 1.0), max_concurrent_requests=configuration.get('max_concurrent_requests', 1000), priority_weight=configuration.get('priority_weight', 1.0))
            self.session.add(region)
            self.session.commit()
            self.session.refresh(region)
            logger.info('Created marketplace region %s', region_code)
            return region
        except Exception as e:
            logger.error('Error creating region %s: %s', region_code, e)
            self.session.rollback()
            raise

    async def update_region_health(self, region_code: str, health_metrics: dict[str, Any]) -> MarketplaceRegion:
        """Update region health metrics"""
        try:
            stmt = select(MarketplaceRegion).where(MarketplaceRegion.region_code == region_code)
            region = self.session.execute(stmt).first()
            if not region:
                raise ValueError(f'Region {region_code} not found')
            region.health_score = health_metrics.get('health_score', 1.0)
            region.average_response_time = health_metrics.get('average_response_time', 0.0)
            region.request_rate = health_metrics.get('request_rate', 0.0)
            region.error_rate = health_metrics.get('error_rate', 0.0)
            region.last_health_check = datetime.now(UTC)
            if region.health_score < 0.5:
                region.status = RegionStatus.MAINTENANCE
            elif region.health_score < 0.8:
                region.status = RegionStatus.ACTIVE
            else:
                region.status = RegionStatus.ACTIVE
            self.session.commit()
            self.session.refresh(region)
            logger.info('Updated health for region %s: %s', region_code, region.health_score)
            return region # type: ignore[return-value]
        except Exception as e:
            logger.error('Error updating region health %s: %s', region_code, e)
            self.session.rollback()
            raise

    async def get_optimal_region(self, service_type: str, user_location: str | None=None) -> MarketplaceRegion:
        """Get the optimal region for a service request"""
        try:
            stmt = select(MarketplaceRegion).where(MarketplaceRegion.status == RegionStatus.ACTIVE).order_by(desc(MarketplaceRegion.priority_weight))  # type: ignore[arg-type]
            regions = self.session.execute(stmt).all()
            if not regions:
                raise ValueError('No active regions available')
            if user_location:
                optimal_region = regions[0]
            else:
                optimal_region = min(regions, key=lambda r: (r.health_score * -1, r.load_factor))
            return optimal_region # type: ignore[return-value]
        except Exception as e:
            logger.error('Error getting optimal region: %s', e)
            raise
