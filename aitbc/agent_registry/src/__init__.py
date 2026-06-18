"""
Agent Registry Package
Provides agent registration, discovery, health tracking, and metadata management
"""

from .discovery import AgentDiscovery
from .health import AgentHealthTracker
from .metadata import MetadataManager, MetadataValidator
from .registration import (
    AgentCapability,
    AgentInfo,
    AgentRegistry,
    AgentStatus,
    AgentType,
    CapabilityType,
    create_agent_registry,
    get_agent_registry,
)

__all__ = [
    # Core registration
    "AgentRegistry",
    "AgentInfo",
    "AgentCapability",
    "AgentType",
    "AgentStatus",
    "CapabilityType",
    "create_agent_registry",
    "get_agent_registry",
    # Discovery
    "AgentDiscovery",
    # Health
    "AgentHealthTracker",
    # Metadata
    "MetadataValidator",
    "MetadataManager",
]
