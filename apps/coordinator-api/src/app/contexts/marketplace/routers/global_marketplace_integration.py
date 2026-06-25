"""
Global Marketplace Integration API Router
REST API endpoints for integrated global marketplace with cross-chain capabilities
"""

from datetime import UTC, datetime
from typing import Annotated, Any

from app.shared_kernel.enums import TransactionPriority
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from aitbc.aitbc_logging import get_logger

from ....agent_identity.manager import AgentIdentityManager
from ....reputation.engine import CrossChainReputationEngine
from ....storage.db import get_session
from ...cross_chain.services.cross_chain.bridge_enhanced import BridgeProtocol
from ..domain.global_marketplace import GlobalMarketplaceOffer
from ..services.global_marketplace_integration import GlobalMarketplaceIntegrationService, IntegrationStatus

logger = get_logger(__name__)

router = APIRouter(prefix="/global-marketplace-integration", tags=["Global Marketplace Integration"])


def get_integration_service(session: Annotated[Session, Depends(get_session)]) -> GlobalMarketplaceIntegrationService:
    return GlobalMarketplaceIntegrationService(session)


def get_agent_identity_manager(session: Annotated[Session, Depends(get_session)]) -> AgentIdentityManager:
    return AgentIdentityManager(session)


def get_reputation_engine(session: Annotated[Session, Depends(get_session)]) -> CrossChainReputationEngine:
    return CrossChainReputationEngine(session)


@router.post("/offers/create-cross-chain", response_model=dict[str, Any])
async def create_cross_chain_marketplace_offer(
    agent_id: str,
    service_type: str,
    resource_specification: dict[str, Any],
    base_price: float,
    currency: str | None,
    total_capacity: int | None,
    regions_available: list[str] | None,
    supported_chains: list[int] | None,
    cross_chain_pricing: dict[int, float] | None,
    auto_bridge_enabled: bool | None,
    reputation_threshold: float | None,
    deadline_minutes: int | None,
    session: Annotated[Session, Depends(get_session)],
    integration_service: Annotated[GlobalMarketplaceIntegrationService, Depends(get_integration_service)],
    identity_manager: Annotated[AgentIdentityManager, Depends(get_agent_identity_manager)],
) -> dict[str, Any]:
    """Create a cross-chain enabled marketplace offer"""
    try:
        identity = await identity_manager.get_identity(agent_id)  # type: ignore[attr-defined]
        if not identity:
            raise HTTPException(status_code=404, detail="Agent identity not found")
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
    except ValueError:
        raise HTTPException(status_code=400, detail="Bad request") from None
    except Exception:
        raise HTTPException(status_code=500, detail="Error creating cross-chain offer") from None


@router.get("/offers/cross-chain", response_model=list[dict[str, Any]])
async def get_integrated_marketplace_offers(
    region: str | None,
    service_type: str | None,
    chain_id: int | None,
    min_reputation: float | None,
    include_cross_chain: bool | None,
    limit: int | None,
    offset: int | None,
    session: Annotated[Session, Depends(get_session)],
    integration_service: Annotated[GlobalMarketplaceIntegrationService, Depends(get_integration_service)],
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
    except Exception:
        raise HTTPException(status_code=500, detail="Error getting integrated offers") from None


@router.get("/offers/{offer_id}/cross-chain-details", response_model=dict[str, Any])
async def get_cross_chain_offer_details(
    offer_id: str,
    session: Annotated[Session, Depends(get_session)],
    integration_service: Annotated[GlobalMarketplaceIntegrationService, Depends(get_integration_service)],
) -> dict[str, Any]:
    """Get detailed cross-chain information for a specific offer"""
    try:
        stmt = select(GlobalMarketplaceOffer).where(GlobalMarketplaceOffer.id == offer_id)
        offer = session.execute(stmt).scalars().first()
        if not offer:
            raise HTTPException(status_code=404, detail="Offer not found")
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
    except Exception:
        raise HTTPException(status_code=500, detail="Error getting cross-chain offer details") from None


@router.post("/offers/{offer_id}/optimize-pricing", response_model=dict[str, Any])
async def optimize_offer_pricing(
    offer_id: str,
    optimization_strategy: str | None,
    target_regions: list[str] | None,
    target_chains: list[int] | None,
    session: Annotated[Session, Depends(get_session)],
    integration_service: Annotated[GlobalMarketplaceIntegrationService, Depends(get_integration_service)],
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
    except ValueError:
        raise HTTPException(status_code=400, detail="Bad request") from None
    except Exception:
        raise HTTPException(status_code=500, detail="Error optimizing offer pricing") from None


@router.post("/transactions/execute-cross-chain", response_model=dict[str, Any])
async def execute_cross_chain_transaction(
    buyer_id: str,
    offer_id: str,
    quantity: int,
    source_chain: int | None,
    target_chain: int | None,
    source_region: str | None,
    target_region: str | None,
    payment_method: str | None,
    bridge_protocol: BridgeProtocol | None,
    priority: TransactionPriority | None,
    auto_execute_bridge: bool | None,
    session: Annotated[Session, Depends(get_session)],
    integration_service: Annotated[GlobalMarketplaceIntegrationService, Depends(get_integration_service)],
    identity_manager: Annotated[AgentIdentityManager, Depends(get_agent_identity_manager)],
) -> dict[str, Any]:
    """Execute a cross-chain marketplace transaction"""
    try:
        identity = await identity_manager.get_identity(buyer_id)  # type: ignore[attr-defined]
        if not identity:
            raise HTTPException(status_code=404, detail="Buyer identity not found")
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
    except ValueError:
        raise HTTPException(status_code=400, detail="Bad request") from None
    except Exception:
        raise HTTPException(status_code=500, detail="Error executing cross-chain transaction") from None


@router.get("/transactions/cross-chain", response_model=list[dict[str, Any]])
async def get_cross_chain_transactions(
    buyer_id: str | None,
    seller_id: str | None,
    source_chain: int | None,
    target_chain: int | None,
    status: str | None,
    limit: int | None,
    offset: int | None,
    session: Annotated[Session, Depends(get_session)],
    integration_service: Annotated[GlobalMarketplaceIntegrationService, Depends(get_integration_service)],
) -> list[dict[str, Any]]:
    """Get cross-chain marketplace transactions"""
    try:
        transactions = await integration_service.marketplace_service.get_global_transactions(
            user_id=buyer_id or seller_id, status=status, limit=limit, offset=offset
        )
        cross_chain_transactions = []
        for tx in transactions:
            if tx.source_chain and tx.target_chain and (tx.source_chain != tx.target_chain):
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
    except Exception:
        raise HTTPException(status_code=500, detail="Error getting cross-chain transactions") from None


@router.get("/analytics/cross-chain", response_model=dict[str, Any])
async def get_cross_chain_analytics(
    time_period_hours: int | None,
    region: str | None,
    chain_id: int | None,
    session: Annotated[Session, Depends(get_session)],
    integration_service: Annotated[GlobalMarketplaceIntegrationService, Depends(get_integration_service)],
) -> dict[str, Any]:
    """Get comprehensive cross-chain analytics"""
    try:
        analytics = await integration_service.get_cross_chain_analytics(
            time_period_hours=time_period_hours, region=region, chain_id=chain_id
        )
        return analytics
    except Exception:
        raise HTTPException(status_code=500, detail="Error getting cross-chain analytics") from None


@router.get("/analytics/marketplace-integration", response_model=dict[str, Any])
async def get_marketplace_integration_analytics(
    session: Annotated[Session, Depends(get_session)],
    integration_service: Annotated[GlobalMarketplaceIntegrationService, Depends(get_integration_service)],
) -> dict[str, Any]:
    """Get marketplace integration status and metrics"""
    try:
        integration_metrics = integration_service.metrics
        active_regions = await integration_service.region_manager._get_active_regions()  # type: ignore[attr-defined]
        supported_chains = [1, 137, 56, 42161, 10, 43114]
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
            "last_updated": datetime.now(UTC).isoformat(),
        }
    except Exception:
        raise HTTPException(status_code=500, detail="Error getting marketplace integration analytics") from None


@router.get("/status", response_model=dict[str, Any])
async def get_integration_status(
    session: Annotated[Session, Depends(get_session)],
    integration_service: Annotated[GlobalMarketplaceIntegrationService, Depends(get_integration_service)],
) -> dict[str, Any]:
    """Get global marketplace integration status"""
    try:
        services_status = {
            "marketplace_service": "active",
            "region_manager": "active",
            "bridge_service": "active" if integration_service.bridge_service else "inactive",
            "transaction_manager": "active" if integration_service.tx_manager else "inactive",
            "reputation_engine": "active",
        }
        metrics = integration_service.metrics
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
            "last_updated": datetime.now(UTC).isoformat(),
        }
    except Exception:
        raise HTTPException(status_code=500, detail="Error getting integration status") from None


@router.get("/config", response_model=dict[str, Any])
async def get_integration_config(
    session: Annotated[Session, Depends(get_session)],
    integration_service: Annotated[GlobalMarketplaceIntegrationService, Depends(get_integration_service)],
) -> dict[str, Any]:
    """Get global marketplace integration configuration"""
    try:
        config = integration_service.integration_config
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
            "last_updated": datetime.now(UTC).isoformat(),
        }
    except Exception:
        raise HTTPException(status_code=500, detail="Error getting integration config") from None


@router.post("/config/update", response_model=dict[str, Any])
async def update_integration_config(
    config_updates: dict[str, Any],
    session: Annotated[Session, Depends(get_session)],
    integration_service: Annotated[GlobalMarketplaceIntegrationService, Depends(get_integration_service)],
) -> dict[str, Any]:
    """Update global marketplace integration configuration"""
    try:
        valid_keys = integration_service.integration_config.keys()
        for key in config_updates:
            if key not in valid_keys:
                raise ValueError(f"Invalid configuration key: {key}")
        for key, value in config_updates.items():
            integration_service.integration_config[key] = value
        return {
            "updated_config": integration_service.integration_config,
            "updated_keys": list(config_updates.keys()),
            "updated_at": datetime.now(UTC).isoformat(),
        }
    except ValueError:
        raise HTTPException(status_code=400, detail="Bad request") from None
    except Exception:
        raise HTTPException(status_code=500, detail="Error updating integration config") from None


@router.get("/health", response_model=dict[str, Any])
async def get_integration_health(
    session: Annotated[Session, Depends(get_session)],
    integration_service: Annotated[GlobalMarketplaceIntegrationService, Depends(get_integration_service)],
) -> dict[str, Any]:
    """Get global marketplace integration health status"""
    try:
        health_status: dict[str, Any] = {"overall_status": "healthy", "services": {}, "metrics": {}, "issues": []}
        try:
            await integration_service.marketplace_service.get_global_offers(limit=1)
            health_status["services"]["marketplace_service"] = "healthy"
        except Exception:
            health_status["services"]["marketplace_service"] = "unhealthy"
            health_status["issues"].append("Marketplace service error")
        try:
            regions = await integration_service.region_manager._get_active_regions()  # type: ignore[attr-defined]
            health_status["services"]["region_manager"] = "healthy"
            health_status["metrics"]["active_regions"] = len(regions)
        except Exception:
            health_status["services"]["region_manager"] = "unhealthy"
            health_status["issues"].append("Region manager error")
        if integration_service.bridge_service:
            try:
                stats = await integration_service.bridge_service.get_bridge_statistics(1)
                health_status["services"]["bridge_service"] = "healthy"
                health_status["metrics"]["bridge_requests"] = stats["total_requests"]
            except Exception:
                health_status["services"]["bridge_service"] = "unhealthy"
                health_status["issues"].append("Bridge service error")
        if integration_service.tx_manager:
            try:
                stats = await integration_service.tx_manager.get_transaction_statistics(1)
                health_status["services"]["transaction_manager"] = "healthy"
                health_status["metrics"]["transactions"] = stats["total_transactions"]
            except Exception:
                health_status["services"]["transaction_manager"] = "unhealthy"
                health_status["issues"].append("Transaction manager error")
        if health_status["issues"]:
            health_status["overall_status"] = "degraded"
        health_status["last_updated"] = datetime.now(UTC).isoformat()
        return health_status
    except Exception:
        raise HTTPException(status_code=500, detail="Error getting integration health") from None


@router.post("/diagnostics/run", response_model=dict[str, Any])
async def run_integration_diagnostics(
    diagnostic_type: str | None,
    session: Annotated[Session, Depends(get_session)],
    integration_service: Annotated[GlobalMarketplaceIntegrationService, Depends(get_integration_service)],
) -> dict[str, Any]:
    """Run integration diagnostics"""
    try:
        diagnostics: dict[str, Any] = {
            "diagnostic_type": diagnostic_type,
            "started_at": datetime.now(UTC).isoformat(),
            "results": {},
        }
        if diagnostic_type == "full" or diagnostic_type == "services":
            diagnostics["results"]["services"] = {}
            try:
                await integration_service.marketplace_service.get_global_offers(limit=1)
                diagnostics["results"]["services"]["marketplace_service"] = {"status": "healthy", "offers_accessible": True}
            except Exception:
                diagnostics["results"]["services"]["marketplace_service"] = {"status": "unhealthy", "error": "Service error"}
            try:
                regions = await integration_service.region_manager._get_active_regions()  # type: ignore[attr-defined]
                diagnostics["results"]["services"]["region_manager"] = {"status": "healthy", "active_regions": len(regions)}
            except Exception:
                diagnostics["results"]["services"]["region_manager"] = {"status": "unhealthy", "error": "Service error"}
        if diagnostic_type == "full" or diagnostic_type == "cross-chain":
            diagnostics["results"]["cross_chain"] = {}
            if integration_service.bridge_service:
                try:
                    stats = await integration_service.bridge_service.get_bridge_statistics(1)
                    diagnostics["results"]["cross_chain"]["bridge_service"] = {"status": "healthy", "statistics": stats}
                except Exception:
                    diagnostics["results"]["cross_chain"]["bridge_service"] = {"status": "unhealthy", "error": "Service error"}
            if integration_service.tx_manager:
                try:
                    stats = await integration_service.tx_manager.get_transaction_statistics(1)
                    diagnostics["results"]["cross_chain"]["transaction_manager"] = {"status": "healthy", "statistics": stats}
                except Exception as e:
                    logger.error("Transaction manager error: %s", e)
                    diagnostics["results"]["cross_chain"]["transaction_manager"] = {
                        "status": "unhealthy",
                        "error": "Service error",
                    }
        if diagnostic_type == "full" or diagnostic_type == "performance":
            diagnostics["results"]["performance"] = {
                "integration_metrics": integration_service.metrics,
                "configuration": integration_service.integration_config,
            }
        diagnostics["completed_at"] = datetime.now(UTC).isoformat()
        start_time = datetime.fromisoformat(diagnostics["started_at"])
        diagnostics["duration_seconds"] = (datetime.now(UTC) - start_time).total_seconds()
        return diagnostics
    except Exception:
        raise HTTPException(status_code=500, detail="Error running diagnostics") from None
