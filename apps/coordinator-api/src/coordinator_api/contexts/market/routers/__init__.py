"""Market routers."""

from __future__ import annotations

from .market import router as market
from .market_gpu import router as market_gpu
from .market_offers import router as market_offers

__all__ = [
    "market",
    "market_gpu",
    "market_offers",
]
