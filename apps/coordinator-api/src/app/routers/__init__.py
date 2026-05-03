"""Router modules for the coordinator API."""

# Skip optional routers with missing dependencies
try:
    from .admin import router as admin
except ImportError:
    admin = None
    print("WARNING: Admin router not available (missing slowapi)")

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
    "governance_enhanced",
    "registry",
]
from .cross_chain_integration import router as cross_chain_integration
from .developer_platform import router as developer_platform
from .global_marketplace import router as global_marketplace
from .global_marketplace_integration import router as global_marketplace_integration
from .governance_enhanced import router as governance_enhanced
