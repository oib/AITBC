"""Marketplace routers."""

from __future__ import annotations

from .global_marketplace import router as global_marketplace
from .global_marketplace_integration import router as global_marketplace_integration
from .marketplace import router as marketplace
from .marketplace_gpu import router as marketplace_gpu
from .marketplace_offers import router as marketplace_offers

__all__ = [
    "marketplace",
    "marketplace_gpu",
    "marketplace_offers",
    "global_marketplace",
    "global_marketplace_integration",
]
