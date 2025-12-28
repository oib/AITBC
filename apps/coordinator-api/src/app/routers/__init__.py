"""Router modules for the coordinator API."""

from .client import router as client
from .miner import router as miner
from .admin import router as admin
from .marketplace import router as marketplace
from .explorer import router as explorer
from .services import router as services
from .users import router as users
from .exchange import router as exchange
from .marketplace_offers import router as marketplace_offers
# from .registry import router as registry

__all__ = ["client", "miner", "admin", "marketplace", "explorer", "services", "users", "exchange", "marketplace_offers", "registry"]
