"""
Global Marketplace Integration API Router
REST API endpoints for integrated global marketplace with cross-chain capabilities
"""

from datetime import datetime, UTC
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from ..agent_identity.manager import AgentIdentityManager
from ..domain.global_marketplace import (
    GlobalMarketplaceOffer,
)
from ..reputation.engine import CrossChainReputationEngine
from ..services.cross_chain_bridge_enhanced import BridgeProtocol
from ..services.global_marketplace_integration import (
    GlobalMarketplaceIntegrationService,
    IntegrationStatus,
)
from ..services.multi_chain_transaction_manager import TransactionPriority
from ..storage.db import get_session

router = APIRouter(prefix="/global-marketplace-integration", tags=["Global Marketplace Integration"])


# Dependency injection
def get_integration_service(session: Session = Depends(get_session)) -> GlobalMarketplaceIntegrationService:
    return GlobalMarketplaceIntegrationService(session)


def get_agent_identity_manager(session: Session = Depends(get_session)) -> AgentIdentityManager:
    return AgentIdentityManager(session)


def get_reputation_engine(session: Session = Depends(get_session)) -> CrossChainReputationEngine:
    return CrossChainReputationEngine(session)


# Cross-Chain Marketplace Offer Endpoints
@router.post("/offers/create-cross-chain", response_model=dict[str, Any])
async def create_cross_chain_marketplace_offer(
    agent_id: str,
    service_type: str,
    resource_specification: dict[str, Any],
    base_price: float,
    currency: str = "USD",
    total_capacity: int = 100,
    regions_available: list[str] | None = None,
    supported_chains: list[int] | None = None,
    cross_chain_pricing: dict[int, float] | None = None,
    auto_bridge_enabled: bool = True,
    reputation_threshold: float = 500.0,
    deadline_minutes: int = 60,
    session: Session = Depends(get_session),
    integration_service: GlobalMarketplaceIntegrationService = Depends(get_integration_service),
    identity_manager: AgentIdentityManager = Depends(get_agent_identity_manager),
) -> dict[str, Any]:
    """Create a cross-chain enabled marketplace offer"""

    try:
        # Validate agent identity
        identity = await identity_manager.get_identity(agent_id)
        if not identity:
            raise HTTPException(status_code=404, detail="Agent identity not found")

        # Create cross-chain marketplace offer
        offer = await integration_service.create_cross_chain_marketplace_offer(
            agent_id=agent_id,
            service_type=service_type,
            resource_specification=resource_specification,
            base_price=base_price,
            currency=currency,
            total_capacity=total_capacity,
            regions_available=regions_available,
            supported_chains=supported_chains,
            cross_chain_pricing=cross_chain_pricing,
            auto_bridge_enabled=auto_bridge_enabled,
            reputation_threshold=reputation_threshold,
            deadline_minutes=deadline_minutes,
        )

        return offer

    except ValueError as e:
        raise HTTPException(status_code=400, detail="Bad request")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error creating cross-chain offer")


@router.get("/offers/cross-chain", response_model=list[dict[str, Any]])
async def get_integrated_marketplace_offers(
    region: str | None = Query(None, description="Filter by region"),
    service_type: str | None = Query(None, description="Filter by service type"),
    chain_id: int | None = Query(None, description="Filter by blockchain chain"),
    min_reputation: float | None = Query(None, description="Minimum reputation score"),
    include_cross_chain: bool = Query(True, description="Include cross-chain information"),
    limit: int = Query(100, ge=1, le=500, description="Maximum number of offers"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    session: Session = Depends(get_session),
    integration_service: GlobalMarketplaceIntegrationService = Depends(get_integration_service),
) -> list[dict[str, Any]]:
    """Get integrated marketplace offers with cross-chain capabilities"""

    try:
        offers = await integration_service.get_integrated_marketplace_offers(
            region=region,
            service_type=service_type,
            chain_id=chain_id,
            min_reputation=min_reputation,
            include_cross_chain=include_cross_chain,
            limit=limit,
            offset=offset,
        )

        return offers

    except Exception as e:
        raise HTTPException(status_code=500, detail="Error getting integrated offers")


@router.get("/offers/{offer_id}/cross-chain-details", response_model=dict[str, Any])
async def get_cross_chain_offer_details(
    offer_id: str,
    session: Session = Depends(get_session),
    integration_service: GlobalMarketplaceIntegrationService = Depends(get_integration_service),
) -> dict[str, Any]:
    """Get detailed cross-chain information for a specific offer"""

    try:
        # Get the offer
        stmt = select(GlobalMarketplaceOffer).where(GlobalMarketplaceOffer.id == offer_id)
        offer = session.execute(stmt).scalars().first()

        if not offer:
            raise HTTPException(status_code=404, detail="Offer not found")

        # Get cross-chain availability
        cross_chain_availability = await integration_service._get_cross_chain_availability(offer)

        return {
            "offer_id": offer.id,
            "agent_id": offer.agent_id,
            "service_type": offer.service_type,
            "resource_specification": offer.resource_specification,
            "base_price": offer.base_price,
            "currency": offer.currency,
            "price_per_region": offer.price_per_region,
            "cross_chain_pricing": offer.cross_chain_pricing,
            "total_capacity": offer.total_capacity,
            "available_capacity": offer.available_capacity,
            "regions_available": offer.regions_available,
            "supported_chains": offer.supported_chains,
            "global_status": offer.global_status,
            "global_rating": offer.global_rating,
            "total_transactions": offer.total_transactions,
            "success_rate": offer.success_rate,
            "cross_chain_availability": cross_chain_availability,
            "created_at": offer.created_at.isoformat(),
            "updated_at": offer.updated_at.isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error getting cross-chain offer details")


@router.post("/offers/{offer_id}/optimize-pricing", response_model=dict[str, Any])
async def optimize_offer_pricing(
    offer_id: str,
    optimization_strategy: str = Query("balanced", description="Pricing optimization strategy"),
    target_regions: list[str] | None = Query(None, description="Target regions for optimization"),
    target_chains: list[int] | None = Query(None, description="Target chains for optimization"),
    session: Session = Depends(get_session),
    integration_service: GlobalMarketplaceIntegrationService = Depends(get_integration_service),
) -> dict[str, Any]:
    """Optimize pricing for a global marketplace offer"""

    try:
        optimization = await integration_service.optimize_global_offer_pricing(
            offer_id=offer_id,
            optimization_strategy=optimization_strategy,
            target_regions=target_regions,
            target_chains=target_chains,
        )

        return optimization

    except ValueError as e:
        raise HTTPException(status_code=400, detail="Bad request")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error optimizing offer pricing")


# Cross-Chain Transaction Endpoints
@router.post("/transactions/execute-cross-chain", response_model=dict[str, Any])
async def execute_cross_chain_transaction(
    buyer_id: str,
    offer_id: str,
    quantity: int,
    source_chain: int | None = None,
    target_chain: int | None = None,
    source_region: str = "global",
    target_region: str = "global",
    payment_method: str = "crypto",
    bridge_protocol: BridgeProtocol | None = None,
    priority: TransactionPriority = TransactionPriority.MEDIUM,
    auto_execute_bridge: bool = True,
    session: Session = Depends(get_session),
    integration_service: GlobalMarketplaceIntegrationService = Depends(get_integration_service),
    identity_manager: AgentIdentityManager = Depends(get_agent_identity_manager),
) -> dict[str, Any]:
    """Execute a cross-chain marketplace transaction"""

    try:
        # Validate buyer identity
        identity = await identity_manager.get_identity(buyer_id)
        if not identity:
            raise HTTPException(status_code=404, detail="Buyer identity not found")

        # Execute cross-chain transaction
        transaction = await integration_service.execute_cross_chain_transaction(
            buyer_id=buyer_id,
            offer_id=offer_id,
            quantity=quantity,
            source_chain=source_chain,
            target_chain=target_chain,
            source_region=source_region,
            target_region=target_region,
            payment_method=payment_method,
            bridge_protocol=bridge_protocol,
            priority=priority,
            auto_execute_bridge=auto_execute_bridge,
        )

        return transaction

    except ValueError as e:
        raise HTTPException(status_code=400, detail="Bad request")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error executing cross-chain transaction")


@router.get("/transactions/cross-chain", response_model=list[dict[str, Any]])
async def get_cross_chain_transactions(
    buyer_id: str | None = Query(None, description="Filter by buyer ID"),
    seller_id: str | None = Query(None, description="Filter by seller ID"),
    source_chain: int | None = Query(None, description="Filter by source chain"),
    target_chain: int | None = Query(None, description="Filter by target chain"),
    status: str | None = Query(None, description="Filter by transaction status"),
    limit: int = Query(100, ge=1, le=500, description="Maximum number of transactions"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    session: Session = Depends(get_session),
    integration_service: GlobalMarketplaceIntegrationService = Depends(get_integration_service),
) -> list[dict[str, Any]]:
    """Get cross-chain marketplace transactions"""

    try:
        # Get global transactions with cross-chain filter
        transactions = await integration_service.marketplace_service.get_global_transactions(
            user_id=buyer_id or seller_id, status=status, limit=limit, offset=offset
        )

        # Filter for cross-chain transactions
        cross_chain_transactions = []
        for tx in transactions:
            if tx.source_chain and tx.target_chain and tx.source_chain != tx.target_chain:
                if (not source_chain or tx.source_chain == source_chain) and (
                    not target_chain or tx.target_chain == target_chain
                ):
                    cross_chain_transactions.append(
                        {
                            "id": tx.id,
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
                            "bridge_transaction_id": tx.bridge_transaction_id,
                            "source_region": tx.source_region,
                            "target_region": tx.target_region,
                            "status": tx.status,
                            "payment_status": tx.payment_status,
                            "delivery_status": tx.delivery_status,
                            "created_at": tx.created_at.isoformat(),
                            "updated_at": tx.updated_at.isoformat(),
                        }
                    )

        return cross_chain_transactions

    except Exception as e:
        raise HTTPException(status_code=500, detail="Error getting cross-chain transactions")


# Analytics and Monitoring Endpoints
@router.get("/analytics/cross-chain", response_model=dict[str, Any])
async def get_cross_chain_analytics(
    time_period_hours: int = Query(24, ge=1, le=8760, description="Time period in hours"),
    region: str | None = Query(None, description="Filter by region"),
    chain_id: int | None = Query(None, description="Filter by blockchain chain"),
    session: Session = Depends(get_session),
    integration_service: GlobalMarketplaceIntegrationService = Depends(get_integration_service),
) -> dict[str, Any]:
    """Get comprehensive cross-chain analytics"""

    try:
        analytics = await integration_service.get_cross_chain_analytics(
            time_period_hours=time_period_hours, region=region, chain_id=chain_id
        )

        return analytics

    except Exception as e:
        raise HTTPException(status_code=500, detail="Error getting cross-chain analytics")


@router.get("/analytics/marketplace-integration", response_model=dict[str, Any])
async def get_marketplace_integration_analytics(
    session: Session = Depends(get_session),
    integration_service: GlobalMarketplaceIntegrationService = Depends(get_integration_service),
) -> dict[str, Any]:
    """Get marketplace integration status and metrics"""

    try:
        # Get integration metrics
        integration_metrics = integration_service.metrics

        # Get active regions
        active_regions = await integration_service.region_manager._get_active_regions()

        # Get supported chains
        supported_chains = [1, 137, 56, 42161, 10, 43114]  # From wallet adapter factory

        return {
            "integration_status": IntegrationStatus.ACTIVE.value,
            "total_integrated_offers": integration_metrics["total_integrated_offers"],
            "cross_chain_transactions": integration_metrics["cross_chain_transactions"],
            "regional_distributions": integration_metrics["regional_distributions"],
            "integration_success_rate": integration_metrics["integration_success_rate"],
            "average_integration_time": integration_metrics["average_integration_time"],
            "active_regions": len(active_regions),
            "supported_chains": len(supported_chains),
            "integration_config": integration_service.integration_config,
            "last_updated": datetime.now(datetime.UTC).isoformat(),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail="Error getting marketplace integration analytics")


# Configuration and Status Endpoints
@router.get("/status", response_model=dict[str, Any])
async def get_integration_status(
    session: Session = Depends(get_session),
    integration_service: GlobalMarketplaceIntegrationService = Depends(get_integration_service),
) -> dict[str, Any]:
    """Get global marketplace integration status"""

    try:
        # Get service status
        services_status = {
            "marketplace_service": "active",
            "region_manager": "active",
            "bridge_service": "active" if integration_service.bridge_service else "inactive",
            "transaction_manager": "active" if integration_service.tx_manager else "inactive",
            "reputation_engine": "active",
        }

        # Get integration metrics
        metrics = integration_service.metrics

        # Get configuration
        config = integration_service.integration_config

        return {
            "status": IntegrationStatus.ACTIVE.value,
            "services": services_status,
            "metrics": metrics,
            "configuration": config,
            "supported_features": {
                "auto_cross_chain_listing": config["auto_cross_chain_listing"],
                "cross_chain_pricing": config["cross_chain_pricing_enabled"],
                "regional_pricing": config["regional_pricing_enabled"],
                "reputation_based_ranking": config["reputation_based_ranking"],
                "auto_bridge_execution": config["auto_bridge_execution"],
                "multi_chain_wallet_support": config["multi_chain_wallet_support"],
            },
            "last_updated": datetime.now(datetime.UTC).isoformat(),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail="Error getting integration status")


@router.get("/config", response_model=dict[str, Any])
async def get_integration_config(
    session: Session = Depends(get_session),
    integration_service: GlobalMarketplaceIntegrationService = Depends(get_integration_service),
) -> dict[str, Any]:
    """Get global marketplace integration configuration"""

    try:
        config = integration_service.integration_config

        # Get available optimization strategies
        optimization_strategies = {
            "balanced": {
                "name": "Balanced",
                "description": "Moderate pricing adjustments based on market conditions",
                "price_range": "±10%",
            },
            "aggressive": {
                "name": "Aggressive",
                "description": "Lower prices to maximize volume and market share",
                "price_range": "-10% to -20%",
            },
            "premium": {
                "name": "Premium",
                "description": "Higher prices to maximize margins for premium services",
                "price_range": "+10% to +25%",
            },
        }

        # Get supported bridge protocols
        bridge_protocols = {
            protocol.value: {
                "name": protocol.value.replace("_", " ").title(),
                "description": f"{protocol.value.replace('_', ' ').title()} protocol for cross-chain transfers",
                "recommended_for": {
                    "atomic_swap": "small to medium transfers",
                    "htlc": "high-security transfers",
                    "liquidity_pool": "large transfers",
                    "wrapped_token": "token wrapping",
                }.get(protocol.value, "general transfers"),
            }
            for protocol in BridgeProtocol
        }

        return {
            "integration_config": config,
            "optimization_strategies": optimization_strategies,
            "bridge_protocols": bridge_protocols,
            "transaction_priorities": {
                priority.value: {
                    "name": priority.value.title(),
                    "description": f"{priority.value.title()} priority transactions",
                    "processing_multiplier": {
                        TransactionPriority.LOW.value: 1.5,
                        TransactionPriority.MEDIUM.value: 1.0,
                        TransactionPriority.HIGH.value: 0.8,
                        TransactionPriority.URGENT.value: 0.7,
                        TransactionPriority.CRITICAL.value: 0.5,
                    }.get(priority.value, 1.0),
                }
                for priority in TransactionPriority
            },
            "last_updated": datetime.now(datetime.UTC).isoformat(),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail="Error getting integration config")


@router.post("/config/update", response_model=dict[str, Any])
async def update_integration_config(
    config_updates: dict[str, Any],
    session: Session = Depends(get_session),
    integration_service: GlobalMarketplaceIntegrationService = Depends(get_integration_service),
) -> dict[str, Any]:
    """Update global marketplace integration configuration"""

    try:
        # Validate configuration updates
        valid_keys = integration_service.integration_config.keys()
        for key in config_updates:
            if key not in valid_keys:
                raise ValueError(f"Invalid configuration key: {key}")

        # Update configuration
        for key, value in config_updates.items():
            integration_service.integration_config[key] = value

        return {
            "updated_config": integration_service.integration_config,
            "updated_keys": list(config_updates.keys()),
            "updated_at": datetime.now(datetime.UTC).isoformat(),
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail="Bad request")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error updating integration config")


# Health and Diagnostics Endpoints
@router.get("/health", response_model=dict[str, Any])
async def get_integration_health(
    session: Session = Depends(get_session),
    integration_service: GlobalMarketplaceIntegrationService = Depends(get_integration_service),
) -> dict[str, Any]:
    """Get global marketplace integration health status"""

    try:
        # Check service health
        health_status = {"overall_status": "healthy", "services": {}, "metrics": {}, "issues": []}

        # Check marketplace service
        try:
            await integration_service.marketplace_service.get_global_offers(limit=1)
            health_status["services"]["marketplace_service"] = "healthy"
        except Exception as e:
            health_status["services"]["marketplace_service"] = "unhealthy"
            health_status["issues"].append("Marketplace service error")

        # Check region manager
        try:
            regions = await integration_service.region_manager._get_active_regions()
            health_status["services"]["region_manager"] = "healthy"
            health_status["metrics"]["active_regions"] = len(regions)
        except Exception as e:
            health_status["services"]["region_manager"] = "unhealthy"
            health_status["issues"].append("Region manager error")

        # Check bridge service
        if integration_service.bridge_service:
            try:
                stats = await integration_service.bridge_service.get_bridge_statistics(1)
                health_status["services"]["bridge_service"] = "healthy"
                health_status["metrics"]["bridge_requests"] = stats["total_requests"]
            except Exception as e:
                health_status["services"]["bridge_service"] = "unhealthy"
                health_status["issues"].append("Bridge service error")

        # Check transaction manager
        if integration_service.tx_manager:
            try:
                stats = await integration_service.tx_manager.get_transaction_statistics(1)
                health_status["services"]["transaction_manager"] = "healthy"
                health_status["metrics"]["transactions"] = stats["total_transactions"]
            except Exception as e:
                health_status["services"]["transaction_manager"] = "unhealthy"
                health_status["issues"].append("Transaction manager error")

        # Determine overall status
        if health_status["issues"]:
            health_status["overall_status"] = "degraded"

        health_status["last_updated"] = datetime.now(datetime.UTC).isoformat()

        return health_status

    except Exception as e:
        raise HTTPException(status_code=500, detail="Error getting integration health")


@router.post("/diagnostics/run", response_model=dict[str, Any])
async def run_integration_diagnostics(
    diagnostic_type: str = Query("full", description="Type of diagnostic to run"),
    session: Session = Depends(get_session),
    integration_service: GlobalMarketplaceIntegrationService = Depends(get_integration_service),
) -> dict[str, Any]:
    """Run integration diagnostics"""

    try:
        diagnostics = {"diagnostic_type": diagnostic_type, "started_at": datetime.now(datetime.UTC).isoformat(), "results": {}}

        if diagnostic_type == "full" or diagnostic_type == "services":
            # Test services
            diagnostics["results"]["services"] = {}

            # Test marketplace service
            try:
                await integration_service.marketplace_service.get_global_offers(limit=1)
                diagnostics["results"]["services"]["marketplace_service"] = {"status": "healthy", "offers_accessible": True}
            except Exception as e:
                diagnostics["results"]["services"]["marketplace_service"] = {"status": "unhealthy", "error": "Service error"}

            # Test region manager
            try:
                regions = await integration_service.region_manager._get_active_regions()
                diagnostics["results"]["services"]["region_manager"] = {"status": "healthy", "active_regions": len(regions)}
            except Exception as e:
                diagnostics["results"]["services"]["region_manager"] = {"status": "unhealthy", "error": "Service error"}

        if diagnostic_type == "full" or diagnostic_type == "cross-chain":
            # Test cross-chain functionality
            diagnostics["results"]["cross_chain"] = {}

            if integration_service.bridge_service:
                try:
                    stats = await integration_service.bridge_service.get_bridge_statistics(1)
                    diagnostics["results"]["cross_chain"]["bridge_service"] = {"status": "healthy", "statistics": stats}
                except Exception as e:
                    diagnostics["results"]["cross_chain"]["bridge_service"] = {"status": "unhealthy", "error": "Service error"}

            if integration_service.tx_manager:
                try:
                    stats = await integration_service.tx_manager.get_transaction_statistics(1)
                    diagnostics["results"]["cross_chain"]["transaction_manager"] = {"status": "healthy", "statistics": stats}
                except Exception as e:
                    logger.error(f"Transaction manager error: {e}")
                    diagnostics["results"]["cross_chain"]["transaction_manager"] = {"status": "unhealthy", "error": "Service error"}

        if diagnostic_type == "full" or diagnostic_type == "performance":
            # Test performance
            diagnostics["results"]["performance"] = {
                "integration_metrics": integration_service.metrics,
                "configuration": integration_service.integration_config,
            }

        diagnostics["completed_at"] = datetime.now(datetime.UTC).isoformat()
        diagnostics["duration_seconds"] = (
            datetime.now(datetime.UTC) - datetime.fromisoformat(diagnostics["started_at"])
        ).total_seconds()

        return diagnostics

    except Exception as e:
        raise HTTPException(status_code=500, detail="Error running diagnostics")
