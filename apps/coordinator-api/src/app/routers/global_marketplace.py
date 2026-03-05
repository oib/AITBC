"""
Global Marketplace API Router
REST API endpoints for global marketplace operations, multi-region support, and cross-chain integration
"""

from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Depends, Query, BackgroundTasks
from fastapi.responses import JSONResponse
from sqlmodel import Session, select, func, Field

from ..storage.db import get_session
from ..domain.global_marketplace import (
    GlobalMarketplaceOffer, GlobalMarketplaceTransaction, GlobalMarketplaceAnalytics,
    MarketplaceRegion, GlobalMarketplaceConfig, RegionStatus, MarketplaceStatus
)
from ..domain.agent_identity import AgentIdentity
from ..services.global_marketplace import GlobalMarketplaceService, RegionManager
from ..agent_identity.manager import AgentIdentityManager
from ..reputation.engine import CrossChainReputationEngine

router = APIRouter(
    prefix="/global-marketplace",
    tags=["Global Marketplace"]
)

# Dependency injection
def get_global_marketplace_service(session: Session = Depends(get_session)) -> GlobalMarketplaceService:
    return GlobalMarketplaceService(session)

def get_region_manager(session: Session = Depends(get_session)) -> RegionManager:
    return RegionManager(session)

def get_agent_identity_manager(session: Session = Depends(get_session)) -> AgentIdentityManager:
    return AgentIdentityManager(session)


# Global Marketplace Offer Endpoints
@router.post("/offers", response_model=Dict[str, Any])
async def create_global_offer(
    offer_request: Dict[str, Any],
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
    marketplace_service: GlobalMarketplaceService = Depends(get_global_marketplace_service),
    identity_manager: AgentIdentityManager = Depends(get_agent_identity_manager)
) -> Dict[str, Any]:
    """Create a new global marketplace offer"""
    
    try:
        # Validate request data
        required_fields = ['agent_id', 'service_type', 'resource_specification', 'base_price', 'total_capacity']
        for field in required_fields:
            if field not in offer_request:
                raise HTTPException(status_code=400, detail=f"Missing required field: {field}")
        
        # Get agent identity
        agent_identity = await identity_manager.get_identity(offer_request['agent_id'])
        if not agent_identity:
            raise HTTPException(status_code=404, detail="Agent identity not found")
        
        # Create offer request object
        from ..domain.global_marketplace import GlobalMarketplaceOfferRequest
        
        offer_req = GlobalMarketplaceOfferRequest(
            agent_id=offer_request['agent_id'],
            service_type=offer_request['service_type'],
            resource_specification=offer_request['resource_specification'],
            base_price=offer_request['base_price'],
            currency=offer_request.get('currency', 'USD'),
            total_capacity=offer_request['total_capacity'],
            regions_available=offer_request.get('regions_available', []),
            supported_chains=offer_request.get('supported_chains', []),
            dynamic_pricing_enabled=offer_request.get('dynamic_pricing_enabled', False),
            expires_at=offer_request.get('expires_at')
        )
        
        # Create global offer
        offer = await marketplace_service.create_global_offer(offer_req, agent_identity)
        
        return {
            "offer_id": offer.id,
            "agent_id": offer.agent_id,
            "service_type": offer.service_type,
            "base_price": offer.base_price,
            "currency": offer.currency,
            "total_capacity": offer.total_capacity,
            "available_capacity": offer.available_capacity,
            "regions_available": offer.regions_available,
            "supported_chains": offer.supported_chains,
            "price_per_region": offer.price_per_region,
            "global_status": offer.global_status,
            "created_at": offer.created_at.isoformat()
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating global offer: {str(e)}")


@router.get("/offers", response_model=List[Dict[str, Any]])
async def get_global_offers(
    region: Optional[str] = Query(None, description="Filter by region"),
    service_type: Optional[str] = Query(None, description="Filter by service type"),
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(100, ge=1, le=500, description="Maximum number of offers"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    session: Session = Depends(get_session),
    marketplace_service: GlobalMarketplaceService = Depends(get_global_marketplace_service)
) -> List[Dict[str, Any]]:
    """Get global marketplace offers with filtering"""
    
    try:
        # Convert status string to enum if provided
        status_enum = None
        if status:
            try:
                status_enum = MarketplaceStatus(status)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
        
        offers = await marketplace_service.get_global_offers(
            region=region,
            service_type=service_type,
            status=status_enum,
            limit=limit,
            offset=offset
        )
        
        # Convert to response format
        response_offers = []
        for offer in offers:
            response_offers.append({
                "id": offer.id,
                "agent_id": offer.agent_id,
                "service_type": offer.service_type,
                "base_price": offer.base_price,
                "currency": offer.currency,
                "price_per_region": offer.price_per_region,
                "total_capacity": offer.total_capacity,
                "available_capacity": offer.available_capacity,
                "regions_available": offer.regions_available,
                "global_status": offer.global_status,
                "global_rating": offer.global_rating,
                "total_transactions": offer.total_transactions,
                "success_rate": offer.success_rate,
                "supported_chains": offer.supported_chains,
                "cross_chain_pricing": offer.cross_chain_pricing,
                "created_at": offer.created_at.isoformat(),
                "updated_at": offer.updated_at.isoformat(),
                "expires_at": offer.expires_at.isoformat() if offer.expires_at else None
            })
        
        return response_offers
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting global offers: {str(e)}")


@router.get("/offers/{offer_id}", response_model=Dict[str, Any])
async def get_global_offer(
    offer_id: str,
    session: Session = Depends(get_session),
    marketplace_service: GlobalMarketplaceService = Depends(get_global_marketplace_service)
) -> Dict[str, Any]:
    """Get a specific global marketplace offer"""
    
    try:
        # Get the offer
        stmt = select(GlobalMarketplaceOffer).where(GlobalMarketplaceOffer.id == offer_id)
        offer = session.execute(stmt).scalars().first()
        
        if not offer:
            raise HTTPException(status_code=404, detail="Offer not found")
        
        return {
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
            "region_statuses": offer.region_statuses,
            "global_status": offer.global_status,
            "global_rating": offer.global_rating,
            "total_transactions": offer.total_transactions,
            "success_rate": offer.success_rate,
            "supported_chains": offer.supported_chains,
            "cross_chain_pricing": offer.cross_chain_pricing,
            "dynamic_pricing_enabled": offer.dynamic_pricing_enabled,
            "created_at": offer.created_at.isoformat(),
            "updated_at": offer.updated_at.isoformat(),
            "expires_at": offer.expires_at.isoformat() if offer.expires_at else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting global offer: {str(e)}")


# Global Marketplace Transaction Endpoints
@router.post("/transactions", response_model=Dict[str, Any])
async def create_global_transaction(
    transaction_request: Dict[str, Any],
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
    marketplace_service: GlobalMarketplaceService = Depends(get_global_marketplace_service),
    identity_manager: AgentIdentityManager = Depends(get_agent_identity_manager)
) -> Dict[str, Any]:
    """Create a new global marketplace transaction"""
    
    try:
        # Validate request data
        required_fields = ['buyer_id', 'offer_id', 'quantity']
        for field in required_fields:
            if field not in transaction_request:
                raise HTTPException(status_code=400, detail=f"Missing required field: {field}")
        
        # Get buyer identity
        buyer_identity = await identity_manager.get_identity(transaction_request['buyer_id'])
        if not buyer_identity:
            raise HTTPException(status_code=404, detail="Buyer identity not found")
        
        # Create transaction request object
        from ..domain.global_marketplace import GlobalMarketplaceTransactionRequest
        
        tx_req = GlobalMarketplaceTransactionRequest(
            buyer_id=transaction_request['buyer_id'],
            offer_id=transaction_request['offer_id'],
            quantity=transaction_request['quantity'],
            source_region=transaction_request.get('source_region', 'global'),
            target_region=transaction_request.get('target_region', 'global'),
            payment_method=transaction_request.get('payment_method', 'crypto'),
            source_chain=transaction_request.get('source_chain'),
            target_chain=transaction_request.get('target_chain')
        )
        
        # Create global transaction
        transaction = await marketplace_service.create_global_transaction(tx_req, buyer_identity)
        
        return {
            "transaction_id": transaction.id,
            "buyer_id": transaction.buyer_id,
            "seller_id": transaction.seller_id,
            "offer_id": transaction.offer_id,
            "service_type": transaction.service_type,
            "quantity": transaction.quantity,
            "unit_price": transaction.unit_price,
            "total_amount": transaction.total_amount,
            "currency": transaction.currency,
            "source_chain": transaction.source_chain,
            "target_chain": transaction.target_chain,
            "cross_chain_fee": transaction.cross_chain_fee,
            "source_region": transaction.source_region,
            "target_region": transaction.target_region,
            "regional_fees": transaction.regional_fees,
            "status": transaction.status,
            "payment_status": transaction.payment_status,
            "delivery_status": transaction.delivery_status,
            "created_at": transaction.created_at.isoformat()
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating global transaction: {str(e)}")


@router.get("/transactions", response_model=List[Dict[str, Any]])
async def get_global_transactions(
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(100, ge=1, le=500, description="Maximum number of transactions"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    session: Session = Depends(get_session),
    marketplace_service: GlobalMarketplaceService = Depends(get_global_marketplace_service)
) -> List[Dict[str, Any]]:
    """Get global marketplace transactions"""
    
    try:
        transactions = await marketplace_service.get_global_transactions(
            user_id=user_id,
            status=status,
            limit=limit,
            offset=offset
        )
        
        # Convert to response format
        response_transactions = []
        for tx in transactions:
            response_transactions.append({
                "id": tx.id,
                "transaction_hash": tx.transaction_hash,
                "buyer_id": tx.buyer_id,
                "seller_id": tx.seller_id,
                "offer_id": tx.offer_id,
                "service_type": tx.service_type,
                "quantity": tx.quantity,
                "unit_price": tx.unit_price,
                "total_amount": tx.total_amount,
                "currency": tx.currency,
                "source_chain": tx.source_chain,
                "target_chain": tx.target_chain,
                "cross_chain_fee": tx.cross_chain_fee,
                "source_region": tx.source_region,
                "target_region": tx.target_region,
                "regional_fees": tx.regional_fees,
                "status": tx.status,
                "payment_status": tx.payment_status,
                "delivery_status": tx.delivery_status,
                "created_at": tx.created_at.isoformat(),
                "updated_at": tx.updated_at.isoformat(),
                "confirmed_at": tx.confirmed_at.isoformat() if tx.confirmed_at else None,
                "completed_at": tx.completed_at.isoformat() if tx.completed_at else None
            })
        
        return response_transactions
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting global transactions: {str(e)}")


@router.get("/transactions/{transaction_id}", response_model=Dict[str, Any])
async def get_global_transaction(
    transaction_id: str,
    session: Session = Depends(get_session),
    marketplace_service: GlobalMarketplaceService = Depends(get_global_marketplace_service)
) -> Dict[str, Any]:
    """Get a specific global marketplace transaction"""
    
    try:
        # Get the transaction
        stmt = select(GlobalMarketplaceTransaction).where(
            GlobalMarketplaceTransaction.id == transaction_id
        )
        transaction = session.execute(stmt).scalars().first()
        
        if not transaction:
            raise HTTPException(status_code=404, detail="Transaction not found")
        
        return {
            "id": transaction.id,
            "transaction_hash": transaction.transaction_hash,
            "buyer_id": transaction.buyer_id,
            "seller_id": transaction.seller_id,
            "offer_id": transaction.offer_id,
            "service_type": transaction.service_type,
            "quantity": transaction.quantity,
            "unit_price": transaction.unit_price,
            "total_amount": transaction.total_amount,
            "currency": transaction.currency,
            "source_chain": transaction.source_chain,
            "target_chain": transaction.target_chain,
            "bridge_transaction_id": transaction.bridge_transaction_id,
            "cross_chain_fee": transaction.cross_chain_fee,
            "source_region": transaction.source_region,
            "target_region": transaction.target_region,
            "regional_fees": transaction.regional_fees,
            "status": transaction.status,
            "payment_status": transaction.payment_status,
            "delivery_status": transaction.delivery_status,
            "metadata": transaction.metadata,
            "created_at": transaction.created_at.isoformat(),
            "updated_at": transaction.updated_at.isoformat(),
            "confirmed_at": transaction.confirmed_at.isoformat() if transaction.confirmed_at else None,
            "completed_at": transaction.completed_at.isoformat() if transaction.completed_at else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting global transaction: {str(e)}")


# Region Management Endpoints
@router.get("/regions", response_model=List[Dict[str, Any]])
async def get_regions(
    status: Optional[str] = Query(None, description="Filter by status"),
    session: Session = Depends(get_session)
) -> List[Dict[str, Any]]:
    """Get all marketplace regions"""
    
    try:
        stmt = select(MarketplaceRegion)
        
        if status:
            try:
                status_enum = RegionStatus(status)
                stmt = stmt.where(MarketplaceRegion.status == status_enum)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
        
        regions = session.execute(stmt).scalars().all()
        
        response_regions = []
        for region in regions:
            response_regions.append({
                "id": region.id,
                "region_code": region.region_code,
                "region_name": region.region_name,
                "geographic_area": region.geographic_area,
                "base_currency": region.base_currency,
                "timezone": region.timezone,
                "language": region.language,
                "load_factor": region.load_factor,
                "max_concurrent_requests": region.max_concurrent_requests,
                "priority_weight": region.priority_weight,
                "status": region.status.value,
                "health_score": region.health_score,
                "average_response_time": region.average_response_time,
                "request_rate": region.request_rate,
                "error_rate": region.error_rate,
                "api_endpoint": region.api_endpoint,
                "last_health_check": region.last_health_check.isoformat() if region.last_health_check else None,
                "created_at": region.created_at.isoformat(),
                "updated_at": region.updated_at.isoformat()
            })
        
        return response_regions
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting regions: {str(e)}")


@router.get("/regions/{region_code}/health", response_model=Dict[str, Any])
async def get_region_health(
    region_code: str,
    session: Session = Depends(get_session),
    marketplace_service: GlobalMarketplaceService = Depends(get_global_marketplace_service)
) -> Dict[str, Any]:
    """Get health status for a specific region"""
    
    try:
        health_data = await marketplace_service.get_region_health(region_code)
        return health_data
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting region health: {str(e)}")


@router.post("/regions/{region_code}/health", response_model=Dict[str, Any])
async def update_region_health(
    region_code: str,
    health_metrics: Dict[str, Any],
    session: Session = Depends(get_session),
    region_manager: RegionManager = Depends(get_region_manager)
) -> Dict[str, Any]:
    """Update health metrics for a region"""
    
    try:
        region = await region_manager.update_region_health(region_code, health_metrics)
        
        return {
            "region_code": region.region_code,
            "region_name": region.region_name,
            "status": region.status.value,
            "health_score": region.health_score,
            "last_health_check": region.last_health_check.isoformat() if region.last_health_check else None,
            "updated_at": region.updated_at.isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating region health: {str(e)}")


# Analytics Endpoints
@router.get("/analytics", response_model=Dict[str, Any])
async def get_marketplace_analytics(
    period_type: str = Query("daily", description="Analytics period type"),
    start_date: datetime = Query(..., description="Start date for analytics"),
    end_date: datetime = Query(..., description="End date for analytics"),
    region: Optional[str] = Query("global", description="Region for analytics"),
    include_cross_chain: bool = Query(False, description="Include cross-chain metrics"),
    include_regional: bool = Query(False, description="Include regional breakdown"),
    session: Session = Depends(get_session),
    marketplace_service: GlobalMarketplaceService = Depends(get_global_marketplace_service)
) -> Dict[str, Any]:
    """Get global marketplace analytics"""
    
    try:
        # Create analytics request
        from ..domain.global_marketplace import GlobalMarketplaceAnalyticsRequest
        
        analytics_request = GlobalMarketplaceAnalyticsRequest(
            period_type=period_type,
            start_date=start_date,
            end_date=end_date,
            region=region,
            metrics=[],
            include_cross_chain=include_cross_chain,
            include_regional=include_regional
        )
        
        analytics = await marketplace_service.get_marketplace_analytics(analytics_request)
        
        return {
            "period_type": analytics.period_type,
            "period_start": analytics.period_start.isoformat(),
            "period_end": analytics.period_end.isoformat(),
            "region": analytics.region,
            "total_offers": analytics.total_offers,
            "total_transactions": analytics.total_transactions,
            "total_volume": analytics.total_volume,
            "average_price": analytics.average_price,
            "average_response_time": analytics.average_response_time,
            "success_rate": analytics.success_rate,
            "active_buyers": analytics.active_buyers,
            "active_sellers": analytics.active_sellers,
            "cross_chain_transactions": analytics.cross_chain_transactions,
            "cross_chain_volume": analytics.cross_chain_volume,
            "regional_distribution": analytics.regional_distribution,
            "regional_performance": analytics.regional_performance,
            "generated_at": analytics.created_at.isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting marketplace analytics: {str(e)}")


# Configuration Endpoints
@router.get("/config", response_model=Dict[str, Any])
async def get_global_marketplace_config(
    category: Optional[str] = Query(None, description="Filter by configuration category"),
    session: Session = Depends(get_session)
) -> Dict[str, Any]:
    """Get global marketplace configuration"""
    
    try:
        stmt = select(GlobalMarketplaceConfig)
        
        if category:
            stmt = stmt.where(GlobalMarketplaceConfig.category == category)
        
        configs = session.execute(stmt).scalars().all()
        
        config_dict = {}
        for config in configs:
            config_dict[config.config_key] = {
                "value": config.config_value,
                "type": config.config_type,
                "description": config.description,
                "category": config.category,
                "is_public": config.is_public,
                "updated_at": config.updated_at.isoformat()
            }
        
        return config_dict
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting configuration: {str(e)}")


# Health and Status Endpoints
@router.get("/health", response_model=Dict[str, Any])
async def get_global_marketplace_health(
    session: Session = Depends(get_session),
    marketplace_service: GlobalMarketplaceService = Depends(get_global_marketplace_service)
) -> Dict[str, Any]:
    """Get global marketplace health status"""
    
    try:
        # Get overall health metrics
        total_regions = session.execute(select(func.count(MarketplaceRegion.id))).scalar() or 0
        active_regions = session.execute(
            select(func.count(MarketplaceRegion.id)).where(MarketplaceRegion.status == RegionStatus.ACTIVE)
        ).scalar() or 0
        
        total_offers = session.execute(select(func.count(GlobalMarketplaceOffer.id))).scalar() or 0
        active_offers = session.execute(
            select(func.count(GlobalMarketplaceOffer.id)).where(
                GlobalMarketplaceOffer.global_status == MarketplaceStatus.ACTIVE
            )
        ).scalar() or 0
        
        total_transactions = session.execute(select(func.count(GlobalMarketplaceTransaction.id))).scalar() or 0
        recent_transactions = session.execute(
            select(func.count(GlobalMarketplaceTransaction.id)).where(
                GlobalMarketplaceTransaction.created_at >= datetime.utcnow() - timedelta(hours=24)
            )
        ).scalar() or 0
        
        # Calculate health score
        region_health_ratio = active_regions / max(total_regions, 1)
        offer_activity_ratio = active_offers / max(total_offers, 1)
        transaction_activity = recent_transactions / max(total_transactions, 1)
        
        overall_health = (region_health_ratio + offer_activity_ratio + transaction_activity) / 3
        
        return {
            "status": "healthy" if overall_health > 0.7 else "degraded",
            "overall_health_score": overall_health,
            "regions": {
                "total": total_regions,
                "active": active_regions,
                "health_ratio": region_health_ratio
            },
            "offers": {
                "total": total_offers,
                "active": active_offers,
                "activity_ratio": offer_activity_ratio
            },
            "transactions": {
                "total": total_transactions,
                "recent_24h": recent_transactions,
                "activity_rate": transaction_activity
            },
            "last_updated": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting health status: {str(e)}")
