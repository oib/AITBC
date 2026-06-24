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
    "AgentCapability",
    # Discovery
    "AgentDiscovery",
    # Health
    "AgentHealthTracker",
    "AgentInfo",
    # Core registration
    "AgentRegistry",
    "AgentStatus",
    "AgentType",
    "CapabilityType",
    "MetadataManager",
    # Metadata
    "MetadataValidator",
    "create_agent_registry",
    "get_agent_registry",
]
