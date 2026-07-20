"""FastAPI routers for the Trading Service."""

from .exchange_compat import router as exchange_compat_router
from .inter_chain import router as inter_chain_router
from .legacy_trading import router as legacy_trading_router
from .offers import router as offers_router
from .settlement import router as settlement_router
from .subscriptions import router as subscriptions_router
from .system import router as system_router
from .transactions import router as transactions_router

__all__ = [
    "exchange_compat_router",
    "inter_chain_router",
    "legacy_trading_router",
    "offers_router",
    "settlement_router",
    "subscriptions_router",
    "system_router",
    "transactions_router",
]
