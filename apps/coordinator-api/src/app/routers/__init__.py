"""Router modules for the coordinator API."""

from .client import router as client
from .miner import router as miner
from .admin import router as admin
from .marketplace import router as marketplace
from .explorer import router as explorer

__all__ = ["client", "miner", "admin", "marketplace", "explorer"]
