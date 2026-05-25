"""
Service layer for coordinator business logic.

This module uses a lazy import pattern to avoid importing all 101+ services at startup.
Only the 4 core services (JobService, MinerService, MarketplaceService, ExplorerService)
are exported in __all__ and loaded immediately via __getattr__.

The agent_coordination bounded context package provides:
- AgentIntegrationService, AgentCommunicationService, AgentPerformanceService
- AgentSecurityManager, AgentOrchestrator, AgentPortfolioManager, AgentServiceMarketplace

To add a new service to the public API:
1. Add the service name to __all__
2. Add an entry to _MODULE_BY_EXPORT mapping the service name to its module path
3. The service will be lazily loaded on first access

For services not in __all__, import them directly from their module:
    from app.services.blockchain import BlockchainService
    from app.services.agent_coordination import AgentIntegrationService
"""

from importlib import import_module

__all__ = ["JobService", "MinerService", "MarketplaceService", "ExplorerService"]

_MODULE_BY_EXPORT = {
    "ExplorerService": ".explorer",
    "JobService": ".jobs",
    "MarketplaceService": ".marketplace",
    "MinerService": ".miners",
}


def __getattr__(name: str) -> object:
    """Lazy load services on first access."""
    module_name = _MODULE_BY_EXPORT.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module = import_module(module_name, __name__)
    value = getattr(module, name)
    globals()[name] = value
    return value
