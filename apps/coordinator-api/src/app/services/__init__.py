"""Service layer for coordinator business logic."""

from importlib import import_module

__all__ = ["JobService", "MinerService", "MarketplaceService", "ExplorerService"]

_MODULE_BY_EXPORT = {
    "ExplorerService": ".explorer",
    "JobService": ".jobs",
    "MarketplaceService": ".marketplace",
    "MinerService": ".miners",
}


def __getattr__(name: str):
    module_name = _MODULE_BY_EXPORT.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module = import_module(module_name, __name__)
    value = getattr(module, name)
    globals()[name] = value
    return value
