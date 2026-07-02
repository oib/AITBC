"""
RPC sub-routers for domain-specific endpoints.
"""

from .bridge import router as bridge_router
from .consensus import router as consensus_router
from .contracts import router as contracts_router
from .core import router as core_router
from .disputes import router as disputes_router
from .islands import router as islands_router
from .settlement import router as settlement_router
from .staking import router as staking_router
from .subscription import router as subscription_router

__all__ = [
    "bridge_router",
    "consensus_router",
    "contracts_router",
    "core_router",
    "disputes_router",
    "islands_router",
    "settlement_router",
    "staking_router",
    "subscription_router",
]
