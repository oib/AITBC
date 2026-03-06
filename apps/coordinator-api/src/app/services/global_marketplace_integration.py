"""
Global Marketplace Integration Service
Integration service that combines global marketplace operations with cross-chain capabilities
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple, Union
from uuid import uuid4
from decimal import Decimal
from enum import Enum
import json
from aitbc.logging import get_logger

from sqlmodel import Session, select, update, delete, func, Field
from sqlalchemy.exc import SQLAlchemyError

from ..domain.global_marketplace import (
    GlobalMarketplaceOffer, GlobalMarketplaceTransaction, GlobalMarketplaceAnalytics,
    MarketplaceRegion, RegionStatus, MarketplaceStatus
)
from ..domain.cross_chain_bridge import BridgeRequestStatus
from ..agent_identity.wallet_adapter_enhanced import WalletAdapterFactory, SecurityLevel
from ..services.global_marketplace import GlobalMarketplaceService, RegionManager
from ..services.cross_chain_bridge_enhanced import CrossChainBridgeService, BridgeProtocol
from ..services.multi_chain_transaction_manager import MultiChainTransactionManager, TransactionPriority
from ..reputation.engine import CrossChainReputationEngine

logger = get_logger(__name__)


class IntegrationStatus(str, Enum):
    """Global marketplace integration status"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    MAINTENANCE = "maintenance"
    DEGRADED = "degraded"


class CrossChainOfferStatus(str, Enum):
    """Cross-chain offer status"""
    AVAILABLE = "available"
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class GlobalMarketplaceIntegrationService:
    """Service that integrates global marketplace with cross-chain capabilities"""
    
    def __init__(self, session: Session):
        self.session = session
        self.marketplace_service = GlobalMarketplaceService(session)
        self.region_manager = RegionManager(session)
        self.bridge_service: Optional[CrossChainBridgeService] = None
        self.tx_manager: Optional[MultiChainTransactionManager] = None
        self.reputation_engine = CrossChainReputationEngine(session)
        
        # Integration configuration
        self.integration_config = {
            "auto_cross_chain_listing": True,
            "cross_chain_pricing_enabled": True,
            "regional_pricing_enabled": True,
            "reputation_based_ranking": True,
            "auto_bridge_execution": True,
            "multi_chain_wallet_support": True
        }
        
        # Performance metrics
        self.metrics = {
            "total_integrated_offers": 0,
            "cross_chain_transactions": 0,
            "regional_distributions": 0,
            "integration_success_rate": 0.0,
            "average_integration_time": 0.0
        }
    
    async def initialize_integration(
        self,
        chain_configs: Dict[int, Dict[str, Any]],
        bridge_config: Dict[str, Any],
        tx_manager_config: Dict[str, Any]
    ) -> None:
        """Initialize global marketplace integration services"""
        
        try:
            # Initialize bridge service
            self.bridge_service = CrossChainBridgeService(session)
            await self.bridge_service.initialize_bridge(chain_configs)
            
            # Initialize transaction manager
            self.tx_manager = MultiChainTransactionManager(session)
            await self.tx_manager.initialize(chain_configs)
            
            logger.info("Global marketplace integration services initialized")
            
        except Exception as e:
            logger.error(f"Error initializing integration services: {e}")
            raise
    
    async def create_cross_chain_marketplace_offer(
        self,
        agent_id: str,
        service_type: str,
        resource_specification: Dict[str, Any],
        base_price: float,
        currency: str = "USD",
        total_capacity: int = 100,
        regions_available: List[str] = None,
        supported_chains: List[int] = None,
        cross_chain_pricing: Optional[Dict[int, float]] = None,
        auto_bridge_enabled: bool = True,
        reputation_threshold: float = 500.0,
        deadline_minutes: int = 60
    ) -> Dict[str, Any]:
        """Create a cross-chain enabled marketplace offer"""
        
        try:
            # Validate agent reputation
            reputation_summary = await self.reputation_engine.get_agent_reputation_summary(agent_id)
            if reputation_summary.get('trust_score', 0) < reputation_threshold:
                raise ValueError(f"Insufficient reputation: {reputation_summary.get('trust_score', 0)} < {reputation_threshold}")
            
            # Get active regions
            active_regions = await self.region_manager._get_active_regions()
            if not regions_available:
                regions_available = [region.region_code for region in active_regions]
            
            # Get supported chains
            if not supported_chains:
                supported_chains = WalletAdapterFactory.get_supported_chains()
            
            # Calculate cross-chain pricing if not provided
            if not cross_chain_pricing and self.integration_config["cross_chain_pricing_enabled"]:
                cross_chain_pricing = await self._calculate_cross_chain_pricing(
                    base_price, supported_chains, regions_available
                )
            
            # Create global marketplace offer
            from ..domain.global_marketplace import GlobalMarketplaceOfferRequest
            
            offer_request = GlobalMarketplaceOfferRequest(
                agent_id=agent_id,
                service_type=service_type,
                resource_specification=resource_specification,
                base_price=base_price,
                currency=currency,
                total_capacity=total_capacity,
                regions_available=regions_available,
                supported_chains=supported_chains,
                dynamic_pricing_enabled=self.integration_config["regional_pricing_enabled"],
                expires_at=datetime.utcnow() + timedelta(minutes=deadline_minutes)
            )
            
            global_offer = await self.marketplace_service.create_global_offer(offer_request, None)
            
            # Update with cross-chain pricing
            if cross_chain_pricing:
                global_offer.cross_chain_pricing = cross_chain_pricing
                self.session.commit()
            
            # Create cross-chain listings if enabled
            cross_chain_listings = []
            if self.integration_config["auto_cross_chain_listing"]:
                cross_chain_listings = await self._create_cross_chain_listings(global_offer)
            
            logger.info(f"Created cross-chain marketplace offer {global_offer.id}")
            
            return {
                "offer_id": global_offer.id,
                "agent_id": agent_id,
                "service_type": service_type,
                "base_price": base_price,
                "currency": currency,
                "total_capacity": total_capacity,
                "available_capacity": global_offer.available_capacity,
                "regions_available": global_offer.regions_available,
                "supported_chains": global_offer.supported_chains,
                "cross_chain_pricing": global_offer.cross_chain_pricing,
                "cross_chain_listings": cross_chain_listings,
                "auto_bridge_enabled": auto_bridge_enabled,
                "status": global_offer.global_status.value,
                "created_at": global_offer.created_at.isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error creating cross-chain marketplace offer: {e}")
            self.session.rollback()
            raise
    
    async def execute_cross_chain_transaction(
        self,
        buyer_id: str,
        offer_id: str,
        quantity: int,
        source_chain: Optional[int] = None,
        target_chain: Optional[int] = None,
        source_region: str = "global",
        target_region: str = "global",
        payment_method: str = "crypto",
        bridge_protocol: Optional[BridgeProtocol] = None,
        priority: TransactionPriority = TransactionPriority.MEDIUM,
        auto_execute_bridge: bool = True
    ) -> Dict[str, Any]:
        """Execute a cross-chain marketplace transaction"""
        
        try:
            # Get the global offer
            stmt = select(GlobalMarketplaceOffer).where(GlobalMarketplaceOffer.id == offer_id)
            offer = self.session.execute(stmt).first()
            
            if not offer:
                raise ValueError("Offer not found")
            
            if offer.available_capacity < quantity:
                raise ValueError("Insufficient capacity")
            
            # Validate buyer reputation
            buyer_reputation = await self.reputation_engine.get_agent_reputation_summary(buyer_id)
            if buyer_reputation.get('trust_score', 0) < 300:  # Minimum for transactions
                raise ValueError("Insufficient buyer reputation")
            
            # Determine optimal chains if not specified
            if not source_chain or not target_chain:
                source_chain, target_chain = await self._determine_optimal_chains(
                    buyer_id, offer, source_region, target_region
                )
            
            # Calculate pricing
            unit_price = offer.base_price
            if source_chain in offer.cross_chain_pricing:
                unit_price = offer.cross_chain_pricing[source_chain]
            
            total_amount = unit_price * quantity
            
            # Create global marketplace transaction
            from ..domain.global_marketplace import GlobalMarketplaceTransactionRequest
            
            tx_request = GlobalMarketplaceTransactionRequest(
                buyer_id=buyer_id,
                offer_id=offer_id,
                quantity=quantity,
                source_region=source_region,
                target_region=target_region,
                payment_method=payment_method,
                source_chain=source_chain,
                target_chain=target_chain
            )
            
            global_transaction = await self.marketplace_service.create_global_transaction(
                tx_request, None
            )
            
            # Update offer capacity
            offer.available_capacity -= quantity
            offer.total_transactions += 1
            offer.updated_at = datetime.utcnow()
            
            # Execute cross-chain bridge if needed and enabled
            bridge_transaction_id = None
            if source_chain != target_chain and auto_execute_bridge and self.integration_config["auto_bridge_execution"]:
                bridge_result = await self._execute_cross_chain_bridge(
                    buyer_id, source_chain, target_chain, total_amount,
                    bridge_protocol, priority
                )
                bridge_transaction_id = bridge_result["bridge_request_id"]
                
                # Update transaction with bridge info
                global_transaction.bridge_transaction_id = bridge_transaction_id
                global_transaction.cross_chain_fee = bridge_result.get("total_fee", 0)
            
            self.session.commit()
            
            logger.info(f"Executed cross-chain transaction {global_transaction.id}")
            
            return {
                "transaction_id": global_transaction.id,
                "buyer_id": buyer_id,
                "seller_id": offer.agent_id,
                "offer_id": offer_id,
                "service_type": offer.service_type,
                "quantity": quantity,
                "unit_price": unit_price,
                "total_amount": total_amount + global_transaction.cross_chain_fee,
                "currency": offer.currency,
                "source_chain": source_chain,
                "target_chain": target_chain,
                "bridge_transaction_id": bridge_transaction_id,
                "cross_chain_fee": global_transaction.cross_chain_fee,
                "source_region": source_region,
                "target_region": target_region,
                "status": global_transaction.status,
                "created_at": global_transaction.created_at.isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error executing cross-chain transaction: {e}")
            self.session.rollback()
            raise
    
    async def get_integrated_marketplace_offers(
        self,
        region: Optional[str] = None,
        service_type: Optional[str] = None,
        chain_id: Optional[int] = None,
        min_reputation: Optional[float] = None,
        include_cross_chain: bool = True,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Get integrated marketplace offers with cross-chain capabilities"""
        
        try:
            # Get base offers
            offers = await self.marketplace_service.get_global_offers(
                region=region,
                service_type=service_type,
                limit=limit,
                offset=offset
            )
            
            integrated_offers = []
            for offer in offers:
                # Filter by reputation if specified
                if min_reputation:
                    reputation_summary = await self.reputation_engine.get_agent_reputation_summary(offer.agent_id)
                    if reputation_summary.get('trust_score', 0) < min_reputation:
                        continue
                
                # Filter by chain if specified
                if chain_id and chain_id not in offer.supported_chains:
                    continue
                
                # Create integrated offer data
                integrated_offer = {
                    "id": offer.id,
                    "agent_id": offer.agent_id,
                    "service_type": offer.service_type,
                    "resource_specification": offer.resource_specification,
                    "base_price": offer.base_price,
                    "currency": offer.currency,
                    "price_per_region": offer.price_per_region,
                    "total_capacity": offer.total_capacity,
                    "available_capacity": offer.available_capacity,
                    "regions_available": offer.regions_available,
                    "supported_chains": offer.supported_chains,
                    "cross_chain_pricing": offer.cross_chain_pricing if include_cross_chain else {},
                    "global_status": offer.global_status,
                    "global_rating": offer.global_rating,
                    "total_transactions": offer.total_transactions,
                    "success_rate": offer.success_rate,
                    "created_at": offer.created_at.isoformat(),
                    "updated_at": offer.updated_at.isoformat()
                }
                
                # Add cross-chain availability if requested
                if include_cross_chain:
                    integrated_offer["cross_chain_availability"] = await self._get_cross_chain_availability(offer)
                
                integrated_offers.append(integrated_offer)
            
            return integrated_offers
            
        except Exception as e:
            logger.error(f"Error getting integrated marketplace offers: {e}")
            raise
    
    async def get_cross_chain_analytics(
        self,
        time_period_hours: int = 24,
        region: Optional[str] = None,
        chain_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Get comprehensive cross-chain analytics"""
        
        try:
            # Get base marketplace analytics
            from ..domain.global_marketplace import GlobalMarketplaceAnalyticsRequest
            
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(hours=time_period_hours)
            
            analytics_request = GlobalMarketplaceAnalyticsRequest(
                period_type="hourly",
                start_date=start_time,
                end_date=end_time,
                region=region or "global",
                metrics=[],
                include_cross_chain=True,
                include_regional=True
            )
            
            marketplace_analytics = await self.marketplace_service.get_marketplace_analytics(analytics_request)
            
            # Get bridge statistics
            bridge_stats = await self.bridge_service.get_bridge_statistics(time_period_hours)
            
            # Get transaction statistics
            tx_stats = await self.tx_manager.get_transaction_statistics(time_period_hours, chain_id)
            
            # Calculate cross-chain metrics
            cross_chain_metrics = await self._calculate_cross_chain_metrics(
                time_period_hours, region, chain_id
            )
            
            return {
                "time_period_hours": time_period_hours,
                "region": region or "global",
                "chain_id": chain_id,
                "marketplace_analytics": marketplace_analytics,
                "bridge_statistics": bridge_stats,
                "transaction_statistics": tx_stats,
                "cross_chain_metrics": cross_chain_metrics,
                "integration_metrics": self.metrics,
                "generated_at": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting cross-chain analytics: {e}")
            raise
    
    async def optimize_global_offer_pricing(
        self,
        offer_id: str,
        optimization_strategy: str = "balanced",
        target_regions: Optional[List[str]] = None,
        target_chains: Optional[List[int]] = None
    ) -> Dict[str, Any]:
        """Optimize pricing for a global marketplace offer"""
        
        try:
            # Get the offer
            stmt = select(GlobalMarketplaceOffer).where(GlobalMarketplaceOffer.id == offer_id)
            offer = self.session.execute(stmt).first()
            
            if not offer:
                raise ValueError("Offer not found")
            
            # Get current market conditions
            market_conditions = await self._analyze_market_conditions(
                offer.service_type, target_regions, target_chains
            )
            
            # Calculate optimized pricing
            optimized_pricing = await self._calculate_optimized_pricing(
                offer, market_conditions, optimization_strategy
            )
            
            # Update offer with optimized pricing
            offer.price_per_region = optimized_pricing["regional_pricing"]
            offer.cross_chain_pricing = optimized_pricing["cross_chain_pricing"]
            offer.updated_at = datetime.utcnow()
            
            self.session.commit()
            
            logger.info(f"Optimized pricing for offer {offer_id}")
            
            return {
                "offer_id": offer_id,
                "optimization_strategy": optimization_strategy,
                "market_conditions": market_conditions,
                "optimized_pricing": optimized_pricing,
                "price_improvement": optimized_pricing.get("price_improvement", 0),
                "updated_at": offer.updated_at.isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error optimizing offer pricing: {e}")
            self.session.rollback()
            raise
    
    # Private methods
    async def _calculate_cross_chain_pricing(
        self,
        base_price: float,
        supported_chains: List[int],
        regions: List[str]
    ) -> Dict[int, float]:
        """Calculate cross-chain pricing for different chains"""
        
        try:
            cross_chain_pricing = {}
            
            # Get chain-specific factors
            for chain_id in supported_chains:
                chain_info = WalletAdapterFactory.get_chain_info(chain_id)
                
                # Base pricing factors
                gas_factor = 1.0
                popularity_factor = 1.0
                liquidity_factor = 1.0
                
                # Adjust based on chain characteristics
                if chain_id == 1:  # Ethereum
                    gas_factor = 1.2  # Higher gas costs
                    popularity_factor = 1.1  # High popularity
                elif chain_id == 137:  # Polygon
                    gas_factor = 0.8  # Lower gas costs
                    popularity_factor = 0.9  # Good popularity
                elif chain_id == 56:  # BSC
                    gas_factor = 0.7  # Lower gas costs
                    popularity_factor = 0.8  # Moderate popularity
                elif chain_id in [42161, 10]:  # L2s
                    gas_factor = 0.6  # Much lower gas costs
                    popularity_factor = 0.7  # Growing popularity
                
                # Calculate final price
                chain_price = base_price * gas_factor * popularity_factor * liquidity_factor
                cross_chain_pricing[chain_id] = chain_price
            
            return cross_chain_pricing
            
        except Exception as e:
            logger.error(f"Error calculating cross-chain pricing: {e}")
            return {}
    
    async def _create_cross_chain_listings(self, offer: GlobalMarketplaceOffer) -> List[Dict[str, Any]]:
        """Create cross-chain listings for a global offer"""
        
        try:
            listings = []
            
            for chain_id in offer.supported_chains:
                listing = {
                    "offer_id": offer.id,
                    "chain_id": chain_id,
                    "price": offer.cross_chain_pricing.get(chain_id, offer.base_price),
                    "currency": offer.currency,
                    "capacity": offer.available_capacity,
                    "status": CrossChainOfferStatus.AVAILABLE.value,
                    "created_at": datetime.utcnow().isoformat()
                }
                listings.append(listing)
            
            return listings
            
        except Exception as e:
            logger.error(f"Error creating cross-chain listings: {e}")
            return []
    
    async def _determine_optimal_chains(
        self,
        buyer_id: str,
        offer: GlobalMarketplaceOffer,
        source_region: str,
        target_region: str
    ) -> Tuple[int, int]:
        """Determine optimal source and target chains"""
        
        try:
            # Get buyer's preferred chains (could be based on wallet, history, etc.)
            buyer_chains = WalletAdapterFactory.get_supported_chains()
            
            # Find common chains
            common_chains = list(set(offer.supported_chains) & set(buyer_chains))
            
            if not common_chains:
                # Fallback to most popular chains
                common_chains = [1, 137]  # Ethereum and Polygon
            
            # Select source chain (prefer buyer's region or lowest cost)
            source_chain = common_chains[0]
            if len(common_chains) > 1:
                # Choose based on gas price
                min_gas_chain = min(common_chains, key=lambda x: WalletAdapterFactory.get_chain_info(x).get("gas_price", 20))
                source_chain = min_gas_chain
            
            # Select target chain (could be same as source for simplicity)
            target_chain = source_chain
            
            return source_chain, target_chain
            
        except Exception as e:
            logger.error(f"Error determining optimal chains: {e}")
            return 1, 137  # Default to Ethereum and Polygon
    
    async def _execute_cross_chain_bridge(
        self,
        user_id: str,
        source_chain: int,
        target_chain: int,
        amount: float,
        protocol: Optional[BridgeProtocol],
        priority: TransactionPriority
    ) -> Dict[str, Any]:
        """Execute cross-chain bridge for transaction"""
        
        try:
            # Get user's address (simplified)
            user_address = f"0x{hashlib.sha256(user_id.encode()).hexdigest()[:40]}"
            
            # Create bridge request
            bridge_request = await self.bridge_service.create_bridge_request(
                user_address=user_address,
                source_chain_id=source_chain,
                target_chain_id=target_chain,
                amount=amount,
                protocol=protocol,
                security_level=BridgeSecurityLevel.MEDIUM,
                deadline_minutes=30
            )
            
            return bridge_request
            
        except Exception as e:
            logger.error(f"Error executing cross-chain bridge: {e}")
            raise
    
    async def _get_cross_chain_availability(self, offer: GlobalMarketplaceOffer) -> Dict[str, Any]:
        """Get cross-chain availability for an offer"""
        
        try:
            availability = {
                "total_chains": len(offer.supported_chains),
                "available_chains": offer.supported_chains,
                "pricing_available": bool(offer.cross_chain_pricing),
                "bridge_enabled": self.integration_config["auto_bridge_execution"],
                "regional_availability": {}
            }
            
            # Check regional availability
            for region in offer.regions_available:
                region_availability = {
                    "available": True,
                    "chains_available": offer.supported_chains,
                    "pricing": offer.price_per_region.get(region, offer.base_price)
                }
                availability["regional_availability"][region] = region_availability
            
            return availability
            
        except Exception as e:
            logger.error(f"Error getting cross-chain availability: {e}")
            return {}
    
    async def _calculate_cross_chain_metrics(
        self,
        time_period_hours: int,
        region: Optional[str],
        chain_id: Optional[int]
    ) -> Dict[str, Any]:
        """Calculate cross-chain specific metrics"""
        
        try:
            # Mock implementation - would calculate real metrics
            metrics = {
                "cross_chain_volume": 0.0,
                "cross_chain_transactions": 0,
                "average_cross_chain_time": 0.0,
                "cross_chain_success_rate": 0.0,
                "chain_utilization": {},
                "regional_distribution": {}
            }
            
            # Calculate chain utilization
            for chain_id in WalletAdapterFactory.get_supported_chains():
                metrics["chain_utilization"][str(chain_id)] = {
                    "volume": 0.0,
                    "transactions": 0,
                    "success_rate": 0.0
                }
            
            return metrics
            
        except Exception as e:
            logger.error(f"Error calculating cross-chain metrics: {e}")
            return {}
    
    async def _analyze_market_conditions(
        self,
        service_type: str,
        target_regions: Optional[List[str]],
        target_chains: Optional[List[int]]
    ) -> Dict[str, Any]:
        """Analyze current market conditions"""
        
        try:
            # Mock implementation - would analyze real market data
            conditions = {
                "demand_level": "medium",
                "competition_level": "medium",
                "price_trend": "stable",
                "regional_conditions": {},
                "chain_conditions": {}
            }
            
            # Analyze regional conditions
            if target_regions:
                for region in target_regions:
                    conditions["regional_conditions"][region] = {
                        "demand": "medium",
                        "supply": "medium",
                        "price_pressure": "stable"
                    }
            
            # Analyze chain conditions
            if target_chains:
                for chain_id in target_chains:
                    chain_info = WalletAdapterFactory.get_chain_info(chain_id)
                    conditions["chain_conditions"][str(chain_id)] = {
                        "gas_price": chain_info.get("gas_price", 20),
                        "network_activity": "medium",
                        "congestion": "low"
                    }
            
            return conditions
            
        except Exception as e:
            logger.error(f"Error analyzing market conditions: {e}")
            return {}
    
    async def _calculate_optimized_pricing(
        self,
        offer: GlobalMarketplaceOffer,
        market_conditions: Dict[str, Any],
        strategy: str
    ) -> Dict[str, Any]:
        """Calculate optimized pricing based on strategy"""
        
        try:
            optimized_pricing = {
                "regional_pricing": {},
                "cross_chain_pricing": {},
                "price_improvement": 0.0
            }
            
            # Base pricing
            base_price = offer.base_price
            
            if strategy == "balanced":
                # Balanced approach - moderate adjustments
                for region in offer.regions_available:
                    regional_condition = market_conditions["regional_conditions"].get(region, {})
                    demand_multiplier = 1.0
                    
                    if regional_condition.get("demand") == "high":
                        demand_multiplier = 1.1
                    elif regional_condition.get("demand") == "low":
                        demand_multiplier = 0.9
                    
                    optimized_pricing["regional_pricing"][region] = base_price * demand_multiplier
                
                for chain_id in offer.supported_chains:
                    chain_condition = market_conditions["chain_conditions"].get(str(chain_id), {})
                    chain_multiplier = 1.0
                    
                    if chain_condition.get("congestion") == "high":
                        chain_multiplier = 1.05
                    elif chain_condition.get("congestion") == "low":
                        chain_multiplier = 0.95
                    
                    optimized_pricing["cross_chain_pricing"][chain_id] = base_price * chain_multiplier
            
            elif strategy == "aggressive":
                # Aggressive pricing - maximize volume
                for region in offer.regions_available:
                    optimized_pricing["regional_pricing"][region] = base_price * 0.9
                
                for chain_id in offer.supported_chains:
                    optimized_pricing["cross_chain_pricing"][chain_id] = base_price * 0.85
                
                optimized_pricing["price_improvement"] = -0.1  # 10% reduction
            
            elif strategy == "premium":
                # Premium pricing - maximize margin
                for region in offer.regions_available:
                    optimized_pricing["regional_pricing"][region] = base_price * 1.15
                
                for chain_id in offer.supported_chains:
                    optimized_pricing["cross_chain_pricing"][chain_id] = base_price * 1.1
                
                optimized_pricing["price_improvement"] = 0.1  # 10% increase
            
            return optimized_pricing
            
        except Exception as e:
            logger.error(f"Error calculating optimized pricing: {e}")
            return {"regional_pricing": {}, "cross_chain_pricing": {}, "price_improvement": 0.0}
