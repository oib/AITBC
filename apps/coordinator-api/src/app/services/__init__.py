"""
Service layer for coordinator business logic.

This module uses a lazy import pattern to avoid importing all services at startup.
Only the 4 core services (JobService, MinerService, MarketplaceService, ExplorerService)
are exported in __all__ and loaded immediately via __getattr__.

All flat service files have been migrated to their owning bounded contexts.
This shim re-exports the 4 core services from their new context locations for
backward compatibility with code that imports from `app.services`.

To add a new service to the public API:
1. Add the service name to __all__
2. Add an entry to _MODULE_BY_EXPORT mapping the service name to its module path
3. The service will be lazily loaded on first access

For services not in __all__, import them directly from their context:
    from app.contexts.infrastructure.services.jobs import JobService
    from app.contexts.agent_coordination.services.agent_coordination import AgentIntegrationService
"""

from importlib import import_module
from typing import Any

__all__ = ["JobService", "MinerService", "MarketplaceService", "ExplorerService"]

_MODULE_BY_EXPORT = {
    "ExplorerService": "..contexts.infrastructure.services.explorer",
    "JobService": "..contexts.infrastructure.services.jobs",
    "MarketplaceService": "..contexts.marketplace.services.marketplace",
    "MinerService": "..contexts.infrastructure.services.miners",
}


def __getattr__(name: str) -> Any:
    """Lazy load services on first access."""
    module_name = _MODULE_BY_EXPORT.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module = import_module(module_name, __name__)
    value = getattr(module, name)
    globals()[name] = value
    return value
