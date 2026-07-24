"""AITBC Agent Core - Shared agent service logic with protocol-based dependency injection.

This package provides shared business logic for agent integration and orchestration
using protocol-based dependency injection to avoid coupling to app-specific implementations.
"""

__version__ = "0.1.0"

from .branding import BrandSettings
from .identity import AgentIdentity
from .integration import AgentIntegrationService
from .plugins import LoadedPlugin, PluginManager, get_active_brand
from .protocols import (
    AgentStatus,
    IAgentExecution,
    IAgentOrchestrator,
    IAgentStepExecution,
    IAuditor,
    IPricingAPI,
    IResourceDiscovery,
    ISecurityManager,
    ISessionProvider,
    IZKProofService,
    StepType,
    VerificationLevel,
)
from .roles import Role

__all__ = [
    # Version
    "__version__",
    # Branding / white-label
    "AgentIdentity",
    "BrandSettings",
    "LoadedPlugin",
    "PluginManager",
    "Role",
    "get_active_brand",
    # Protocols
    "AgentStatus",
    "VerificationLevel",
    "StepType",
    "IAgentExecution",
    "IAgentStepExecution",
    "ISecurityManager",
    "IAuditor",
    "IAgentOrchestrator",
    "IZKProofService",
    "ISessionProvider",
    # White-label SDK protocols
    "IPricingAPI",
    "IResourceDiscovery",
    # Core service
    "AgentIntegrationService",
]
