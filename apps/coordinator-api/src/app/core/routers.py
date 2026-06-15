"""
Router registration for Coordinator API.
"""

from typing import Any

from aitbc import get_logger

logger = get_logger(__name__)


def register_routers(app: Any) -> None:
    """Register all routers with the application"""
    # Core routers
    from ..contexts.agent_identity.routers import agent_identity
    from ..contexts.blockchain.routers import blockchain
    from ..contexts.cross_chain.routers.cross_chain_integration import router as cross_chain
    from ..contexts.ipfs.routers import router as ipfs
    from ..contexts.marketplace.routers import (
        marketplace,
        marketplace_gpu,
        marketplace_offers,
    )
    from ..contexts.payments.routers import payments
    from ..contexts.portfolio.routers import portfolio_router
    from ..routers import (
        admin,
        agent_router,
        client,
        developer_platform,
        edge_gpu,
        exchange,
        explorer,
        governance_enhanced,
        inference,
        islands_proxy,
        miner,
        monitor,
        multi_modal_rl,
        services,
        swarm,
        training,
        users,
        web_vitals,
    )

    # Register routers
    app.include_router(agent_identity, prefix="/agent-identity", tags=["agent-identity"])
    app.include_router(blockchain, prefix="/blockchain", tags=["blockchain"])
    app.include_router(cross_chain, prefix="/cross-chain", tags=["cross-chain"])
    app.include_router(ipfs, prefix="/ipfs", tags=["ipfs"])
    app.include_router(marketplace, prefix="/marketplace", tags=["marketplace"])
    app.include_router(marketplace_gpu, prefix="/marketplace/gpu", tags=["marketplace-gpu"])
    app.include_router(marketplace_offers, prefix="/marketplace/offers", tags=["marketplace-offers"])
    app.include_router(payments, prefix="/payments", tags=["payments"])
    app.include_router(portfolio_router, prefix="/portfolio", tags=["portfolio"])
    app.include_router(admin, prefix="/admin", tags=["admin"])
    app.include_router(agent_router, prefix="/agent", tags=["agent"])
    app.include_router(client, prefix="/client", tags=["client"])
    app.include_router(developer_platform, prefix="/developer", tags=["developer"])
    app.include_router(edge_gpu, prefix="/edge/gpu", tags=["edge-gpu"])
    app.include_router(exchange, prefix="/exchange", tags=["exchange"])
    app.include_router(explorer, prefix="/explorer", tags=["explorer"])
    app.include_router(governance_enhanced, prefix="/governance", tags=["governance"])
    app.include_router(inference, prefix="/inference", tags=["inference"])
    app.include_router(islands_proxy, prefix="/islands", tags=["islands"])
    app.include_router(miner, prefix="/miner", tags=["miner"])
    app.include_router(monitor, prefix="/monitor", tags=["monitor"])
    app.include_router(multi_modal_rl, prefix="/multi-modal", tags=["multi-modal"])
    app.include_router(services, prefix="/services", tags=["services"])
    app.include_router(swarm, prefix="/swarm", tags=["swarm"])
    app.include_router(training, prefix="/training", tags=["training"])
    app.include_router(users, prefix="/users", tags=["users"])
    app.include_router(web_vitals, prefix="/web-vitals", tags=["web-vitals"])

    # Optional routers
    try:
        from ..contexts.zk_applications.routers.ml_zk_proofs import router as ml_zk_proofs

        app.include_router(ml_zk_proofs, prefix="/zk/ml-proofs", tags=["zk-ml-proofs"])
    except ImportError:
        logger.warning("ML ZK proofs router not available (missing tenseal)")

    from ..contexts.hermes.routers.hermes_decision import router as hermes_decision
    from ..contexts.hermes.routers.hermes_enhanced_simple import router as hermes_enhanced
    from ..contexts.hermes.routers.hermes_health import router as hermes_health
    from ..contexts.hermes.routers.hermes_resource import router as hermes_resource
    from ..contexts.infrastructure.routers.monitoring_dashboard import router as monitoring_dashboard

    app.include_router(hermes_enhanced, prefix="/hermes", tags=["hermes"])
    app.include_router(hermes_decision, prefix="/hermes/decision", tags=["hermes-decision"])
    app.include_router(hermes_health, prefix="/hermes/health", tags=["hermes-health"])
    app.include_router(hermes_resource, prefix="/hermes/resource", tags=["hermes-resource"])
    app.include_router(monitoring_dashboard, prefix="/infrastructure/monitoring", tags=["infrastructure-monitoring"])

    try:
        from ..contexts.multimodal.routers.multi_modal_rl import router as multi_modal_rl_router

        app.include_router(multi_modal_rl_router, prefix="/multimodal", tags=["multimodal"])
    except ImportError:
        logger.warning("Multi-modal RL router not available (missing torch)")

    logger.info("All routers registered successfully")
