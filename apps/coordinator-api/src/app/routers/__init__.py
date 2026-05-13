"""Router modules for the coordinator API."""

from aitbc import get_logger

logger = get_logger(__name__)

# Skip optional routers with missing dependencies
try:
    from .admin import router as admin
except ImportError:
    admin = None
    logger.warning("Admin router not available (missing slowapi)")

from .agent_identity import router as agent_identity
from .blockchain import router as blockchain
from .cache_management import router as cache_management
from .client import router as client
from .edge_gpu import router as edge_gpu

from .exchange import router as exchange
from .explorer import router as explorer
from .marketplace import router as marketplace
from .marketplace_gpu import router as marketplace_gpu
from .marketplace_offers import router as marketplace_offers
from .miner import router as miner
from .payments import router as payments
from .services import router as services
from .users import router as users
from .web_vitals import router as web_vitals
from .multi_modal_rl import router as multi_modal_rl

# from .registry import router as registry

# Governance routers moved to contexts/governance
from .contexts.governance.routers.governance import router as governance
from .contexts.governance.routers.governance_enhanced import router as governance_enhanced

# Staking router moved to contexts/staking
from .contexts.staking.routers.staking import router as staking

# Reputation router moved to contexts/reputation
from .contexts.reputation.routers.reputation import router as reputation

# Rewards router moved to contexts/rewards
from .contexts.rewards.routers.rewards import router as rewards

# Trading router moved to contexts/trading
from .contexts.trading.routers.trading import router as trading

# Hermes routers moved to contexts/hermes
from .contexts.hermes.routers.hermes_enhanced import router as hermes_enhanced
from .contexts.hermes.routers.hermes_enhanced_simple import router as hermes_enhanced_simple
from .contexts.hermes.routers.hermes_enhanced_health import router as hermes_enhanced_health

# Security router moved to contexts/security
from .contexts.security.routers.agent_security_router import router as agent_security_router

# Analytics router moved to contexts/analytics
from .contexts.analytics.routers.analytics import router as analytics

# Certification router moved to contexts/certification
from .contexts.certification.routers.certification import router as certification

# Multimodal routers moved to contexts/multimodal
from .contexts.multimodal.routers.multi_modal_rl import router as multi_modal_rl
from .contexts.multimodal.routers.multimodal_health import router as multimodal_health
from .contexts.multimodal.routers.modality_optimization_health import router as modality_optimization_health

# Developer platform router moved to contexts/developer_platform
from .contexts.developer_platform.routers.developer_platform import router as developer_platform

# Community router moved to contexts/community
from .contexts.community.routers.community import router as community

# Bounty router moved to contexts/bounty
from .contexts.bounty.routers.bounty import router as bounty

# Confidential router moved to contexts/confidential
from .contexts.confidential.routers.confidential import router as confidential

# ZK applications routers moved to contexts/zk_applications
from .contexts.zk_applications.routers.zk_applications import router as zk_applications
from .contexts.zk_applications.routers.ml_zk_proofs import router as ml_zk_proofs

# Agent coordination routers moved to contexts/agent_coordination
from .contexts.agent_coordination.routers.agent_router import router as agent_router
from .contexts.agent_coordination.routers.agent_integration_router import router as agent_integration_router
from .contexts.agent_coordination.routers.agent_creativity import router as agent_creativity
from .contexts.agent_coordination.routers.agent_performance import router as agent_performance
from .contexts.agent_coordination.routers.swarm import router as swarm

# Enterprise integration router moved to contexts/enterprise_integration
from .contexts.enterprise_integration.routers.partners import router as partners

# Advanced AI router moved to contexts/advanced_ai
from .contexts.advanced_ai.routers.adaptive_learning_health import router as adaptive_learning_health

# Ecosystem router moved to contexts/ecosystem
from .contexts.ecosystem.routers.ecosystem_dashboard import router as ecosystem_dashboard

# GPU multimodal router moved to contexts/gpu_multimodal
from .contexts.gpu_multimodal.routers.gpu_multimodal_health import router as gpu_multimodal_health

# Settlement router moved to contexts/settlement
from .contexts.settlement.routers.settlement import router as settlement

# Infrastructure routers moved to contexts/infrastructure
from .contexts.infrastructure.routers.monitor import router as monitor
from .contexts.infrastructure.routers.monitoring_dashboard import router as monitoring_dashboard

__all__ = [
    "client",
    "miner",
    "admin",
    "marketplace",
    "marketplace_gpu",
    "explorer",
    "services",
    "users",
    "exchange",
    "marketplace_offers",
    "payments",
    "web_vitals",
    "edge_gpu",
    "cache_management",
    "agent_identity",
    "blockchain",
    "global_marketplace",
    "cross_chain_integration",
    "global_marketplace_integration",
    "developer_platform",
    "governance",
    "governance_enhanced",
    "staking",
    "reputation",
    "rewards",
    "trading",
    "hermes_enhanced",
    "hermes_enhanced_simple",
    "hermes_enhanced_health",
    "agent_security_router",
    "analytics",
    "certification",
    "multi_modal_rl",
    "multimodal_health",
    "modality_optimization_health",
    "community",
    "bounty",
    "confidential",
    "zk_applications",
    "ml_zk_proofs",
    "agent_router",
    "agent_integration_router",
    "agent_creativity",
    "agent_performance",
    "swarm",
    "partners",
    "adaptive_learning_health",
    "ecosystem_dashboard",
    "gpu_multimodal_health",
    "settlement",
    "monitor",
    "monitoring_dashboard",
    "registry",
]
