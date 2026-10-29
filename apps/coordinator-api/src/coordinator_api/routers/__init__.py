"""Router modules for the coordinator API."""

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)

# Skip optional routers with missing dependencies
try:
    from ..contexts.infrastructure.routers.admin import router as admin
except ImportError:
    admin = None  # type: ignore[assignment]
    logger.warning("Admin router not available (missing slowapi)")

# Agent identity router moved to contexts/agent_identity
from ..contexts.agent_identity.routers.agent_identity import router as agent_identity  # noqa: E402

# Blockchain router moved to contexts/blockchain
from ..contexts.blockchain.routers.blockchain import router as blockchain  # noqa: E402

# Edge GPU router moved to contexts/edge_gpu
from ..contexts.edge_gpu.routers.edge_gpu import router as edge_gpu  # noqa: E402

# from .registry import router as registry
# Governance routers moved to contexts/governance
from ..contexts.governance.routers.governance import router as governance  # noqa: E402
from ..contexts.governance.routers.governance_enhanced import router as governance_enhanced  # noqa: E402

# Market routers moved to contexts/market
from ..contexts.market.routers.market import router as market  # noqa: E402
from ..contexts.market.routers.market_gpu import router as market_gpu  # noqa: E402
from ..contexts.market.routers.market_offers import router as market_offers  # noqa: E402

# Payments router moved to contexts/payments
from ..contexts.payments.routers.payments import router as payments  # noqa: E402
from ..contexts.infrastructure.routers.client import router as client  # noqa: E402
from ..contexts.governance.routers.disputes import router as disputes  # noqa: E402
from ..contexts.infrastructure.routers.exchange import router as exchange  # noqa: E402
from ..contexts.infrastructure.routers.explorer import router as explorer  # noqa: E402
from ..contexts.zk_applications.routers.fhe import router as fhe  # noqa: E402
from ..contexts.infrastructure.routers.inference import router as inference  # noqa: E402
from ..contexts.infrastructure.routers.miner import router as miner  # noqa: E402
from ..contexts.blockchain.routers.oracle import router as oracle  # noqa: E402
from ..contexts.infrastructure.routers.services import router as services  # noqa: E402
from ..contexts.infrastructure.routers.users import router as users  # noqa: E402
from ..contexts.infrastructure.routers.web_vitals import router as web_vitals  # noqa: E402

# Staking router moved to contexts/staking
try:
    from ..contexts.staking.routers.staking import router as staking
except ImportError:
    staking = None  # type: ignore[assignment]
    logger.warning("Staking router not available")

# Reputation router moved to contexts/reputation
try:
    from ..contexts.reputation.routers.reputation import router as reputation
except ImportError:
    reputation = None  # type: ignore[assignment]
    logger.warning("Reputation router not available")

# Rewards router moved to contexts/rewards
try:
    from ..contexts.rewards.routers.rewards import router as rewards
except ImportError:
    rewards = None  # type: ignore[assignment]
    logger.warning("Rewards router not available")

# Trading router moved to contexts/trading
try:
    from ..contexts.trading.routers.trading import router as trading
except ImportError:
    trading = None  # type: ignore[assignment]
    logger.warning("Trading router not available")

# Agent messaging router (feature-flagged, separate from context routers)
from ..contexts.agent_coordination.routers.agent_messaging import router as agent  # noqa: E402

# Security router moved to contexts/security
try:
    from ..contexts.security.routers.security_router import router as agent_security_router
except ImportError:
    agent_security_router = None  # type: ignore[assignment]
    logger.warning("Security router not available")

# Retired in issue #701: analytics.routers.analytics and
# advanced_ai.routers.adaptive_learning_health were imported here but never
# mounted; the modules have been deleted.
from ..contexts.agent_coordination.routers.agent_creativity import router as agent_creativity  # noqa: E402
from ..contexts.agent_coordination.routers.agent_integration_router import router as agent_integration_router  # noqa: E402
from ..contexts.agent_coordination.routers.agent_performance import router as agent_performance  # noqa: E402

# Agent coordination routers moved to contexts/agent_coordination
from ..contexts.agent_coordination.routers.agent_router import router as agent_router  # noqa: E402

# swarm and agent_messaging (above) are deliberately empty routers: their mock
# endpoints were removed and they stay mounted but register no routes.
from ..contexts.agent_coordination.routers.swarm import router as swarm  # noqa: E402

# Bounty router moved to contexts/bounty
# NOTE: contexts/bounty/routers/bounty.py was deleted (dead, never mounted — issue #654);
# the live bounty surface is contexts/bounty/routers/bounty_flat.py loaded lazily in main.py.

# Retired in issue #701: certification.routers.certification and
# community.routers.community were imported here but never mounted; the
# modules have been deleted.

# Confidential router moved to contexts/confidential
from ..contexts.confidential.routers.confidential import router as confidential  # noqa: E402

# Developer platform router moved to contexts/developer_platform
from ..contexts.developer_platform.routers.developer_platform import router as developer_platform  # noqa: E402

# Retired in issue #701: ecosystem.routers.ecosystem_dashboard was imported
# here but never mounted; the module has been deleted.

# partners is deliberately unmounted: imported for the module contract (and
# its tests), but main.py never include_router's it — see the note at the
# registration site.
from ..contexts.enterprise_integration.routers.partners import router as partners  # noqa: E402

# Retired in issue #701: gpu_multimodal.routers.gpu_multimodal_health,
# multimodal.routers.multimodal_health, and
# multimodal.routers.modality_optimization_health were imported here but
# never mounted; the modules have been deleted.

# Infrastructure routers moved to contexts/infrastructure
# Retired in issue #701: infrastructure.routers.monitor (an empty router
# overlapping monitoring_dashboard) was unmounted and deleted.
from ..contexts.infrastructure.routers.monitoring_dashboard import router as monitoring_dashboard  # noqa: E402

# Multimodal routers moved to contexts/multimodal
from ..contexts.multimodal.routers.multi_modal_rl import router as multi_modal_rl  # noqa: E402

# Retired in issue #701: settlement.routers.settlement (the 4 /cross-chain*
# routes) was imported here but never mounted; the module has been deleted.
from ..contexts.zk_applications.routers.ml_zk_proofs import router as ml_zk_proofs  # noqa: E402

# zk_applications is deliberately unmounted: imported for the module
# contract, but main.py never include_router's it (the mounted ZK surface is
# zk_proofs / ml_zk_proofs / fhe).
from ..contexts.zk_applications.routers.zk_applications import router as zk_applications  # noqa: E402

# Islands proxy router moved to contexts/infrastructure
from ..contexts.infrastructure.routers.islands_proxy import router as islands_proxy  # noqa: E402
from .media import router as media  # noqa: E402

__all__ = [
    "client",
    "miner",
    "admin",
    "market",
    "market_gpu",
    "explorer",
    "services",
    "users",
    "exchange",
    "market_offers",
    "payments",
    "web_vitals",
    "edge_gpu",
    "agent_identity",
    "blockchain",
    "developer_platform",
    "governance",
    "governance_enhanced",
    "staking",
    "reputation",
    "rewards",
    "trading",
    "agent",
    "agent_security_router",
    "multi_modal_rl",
    "confidential",
    "zk_applications",
    "ml_zk_proofs",
    "agent_router",
    "agent_integration_router",
    "agent_creativity",
    "agent_performance",
    "swarm",
    "partners",
    "monitoring_dashboard",
    "islands_proxy",
    "inference",
    "fhe",
    "oracle",
    "disputes",
    "media",
]
