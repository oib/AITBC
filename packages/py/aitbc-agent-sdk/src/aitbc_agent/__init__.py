"""
AITBC Agent SDK - Python SDK for AI agents to participate in the AITBC network
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

__version__ = "1.0.0"

_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "Agent": ("agent", "Agent"),
    "AgentIdentity": ("agent", "AgentIdentity"),
    "AgentCapabilities": ("agent", "AgentCapabilities"),
    "AITBCAgent": ("agent", "AITBCAgent"),
    "ComputeProvider": ("compute_provider", "ComputeProvider"),
    "ComputeConsumer": ("compute_consumer", "ComputeConsumer"),
    "PlatformBuilder": ("platform_builder", "PlatformBuilder"),
    "SwarmCoordinator": ("swarm_coordinator", "SwarmCoordinator"),
    "ContractClient": ("contract_integration", "ContractClient"),
    "ContractConfig": ("contract_integration", "ContractConfig"),
    "AgentContractIntegration": ("contract_integration", "AgentContractIntegration"),
}


def __getattr__(name: str) -> Any:
    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute_name = _LAZY_EXPORTS[name]
    module = import_module(f".{module_name}", __name__)
    value = getattr(module, attribute_name)
    globals()[name] = value
    return value


__all__ = ["__version__", *_LAZY_EXPORTS.keys()]
