"""Router modules for the coordinator API."""

from .client import router as client
from .miner import router as miner
from .admin import router as admin
from .marketplace import router as marketplace
from .marketplace_gpu import router as marketplace_gpu
from .explorer import router as explorer
from .services import router as services
from .users import router as users
from .exchange import router as exchange
from .marketplace_offers import router as marketplace_offers
from .payments import router as payments
from .web_vitals import router as web_vitals
from .edge_gpu import router as edge_gpu
from .cache_management import router as cache_management
from .agent_identity import router as agent_identity
# from .registry import router as registry

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
    "global_marketplace",
    "cross_chain_integration",
    "global_marketplace_integration",
    "developer_platform",
    "governance_enhanced",
    "registry",
]
from .global_marketplace import router as global_marketplace
from .cross_chain_integration import router as cross_chain_integration
from .global_marketplace_integration import router as global_marketplace_integration
from .developer_platform import router as developer_platform
from .governance_enhanced import router as governance_enhanced
