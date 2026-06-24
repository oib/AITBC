"""
Agent Registration System
Handles AI agent registration, capability management, and discovery
"""

import hashlib
import logging
import time
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


def log_info(msg: str):
    logger.info(msg)


def log_error(msg: str):
    logger.error(msg)


class AgentType(Enum):
    AI_MODEL = "ai_model"
    DATA_PROVIDER = "data_provider"
    VALIDATOR = "validator"
    MARKET_MAKER = "market_maker"
    BROKER = "broker"
    ORACLE = "oracle"


class AgentStatus(Enum):
    REGISTERED = "registered"
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    BANNED = "banned"


class CapabilityType(Enum):
    TEXT_GENERATION = "text_generation"
    IMAGE_GENERATION = "image_generation"
    DATA_ANALYSIS = "data_analysis"
    PREDICTION = "prediction"
    VALIDATION = "validation"
    COMPUTATION = "computation"


@dataclass
class AgentCapability:
    capability_type: CapabilityType
    name: str
    version: str
    parameters: dict
    performance_metrics: dict
    cost_per_use: Decimal
    availability: float
    max_concurrent_jobs: int


@dataclass
class AgentInfo:
    agent_id: str
    agent_type: AgentType
    name: str
    owner_address: str
    public_key: str
    endpoint_url: str
    capabilities: list[AgentCapability]
    reputation_score: float
    total_jobs_completed: int
    total_earnings: Decimal
    registration_time: float
    last_active: float
    status: AgentStatus
    metadata: dict


class AgentRegistry:
    """Manages AI agent registration and discovery"""

    def __init__(self):
        self.agents: dict[str, AgentInfo] = {}
        self.capability_index: dict[CapabilityType, set[str]] = {}  # capability -> agent_ids
        self.type_index: dict[AgentType, set[str]] = {}  # agent_type -> agent_ids
        self.reputation_scores: dict[str, float] = {}
        self.registration_queue: list[dict] = []

        # Registry parameters
        self.min_reputation_threshold = 0.5
        self.max_agents_per_type = 1000
        self.registration_fee = Decimal("100.0")
        self.inactivity_threshold = 86400 * 7  # 7 days

        # Initialize capability index
        for capability_type in CapabilityType:
            self.capability_index[capability_type] = set()

        # Initialize type index
        for agent_type in AgentType:
            self.type_index[agent_type] = set()

    async def register_agent(
        self,
        agent_type: AgentType,
        name: str,
        owner_address: str,
        public_key: str,
        endpoint_url: str,
        capabilities: list[dict],
        metadata: dict[str, Any] | None = None,
    ) -> tuple[bool, str, str | None]:
        """Register a new AI agent"""
        try:
            # Validate inputs
            if not self._validate_registration_inputs(agent_type, name, owner_address, public_key, endpoint_url):
                return False, "Invalid registration inputs", None

            # Check if agent already exists
            agent_id = self._generate_agent_id(owner_address, name)
            if agent_id in self.agents:
                return False, "Agent already registered", None

            # Check type limits
            if len(self.type_index[agent_type]) >= self.max_agents_per_type:
                return False, f"Maximum agents of type {agent_type.value} reached", None

            # Convert capabilities
            agent_capabilities = []
            for cap_data in capabilities:
                capability = self._create_capability_from_data(cap_data)
                if capability:
                    agent_capabilities.append(capability)

            if not agent_capabilities:
                return False, "Agent must have at least one valid capability", None

            # Create agent info
            agent_info = AgentInfo(
                agent_id=agent_id,
                agent_type=agent_type,
                name=name,
                owner_address=owner_address,
                public_key=public_key,
                endpoint_url=endpoint_url,
                capabilities=agent_capabilities,
                reputation_score=1.0,  # Start with neutral reputation
                total_jobs_completed=0,
                total_earnings=Decimal("0"),
                registration_time=time.time(),
                last_active=time.time(),
                status=AgentStatus.REGISTERED,
                metadata=metadata or {},
            )

            # Add to registry
            self.agents[agent_id] = agent_info

            # Update indexes
            self.type_index[agent_type].add(agent_id)
            for capability in agent_capabilities:
                self.capability_index[capability.capability_type].add(agent_id)

            log_info(f"Agent registered: {agent_id} ({name})")
            return True, "Registration successful", agent_id

        except Exception as e:
            return False, f"Registration failed: {str(e)}", None

    def _validate_registration_inputs(
        self, agent_type: AgentType, name: str, owner_address: str, public_key: str, endpoint_url: str
    ) -> bool:
        """Validate registration inputs"""
        # Check required fields
        if not all([agent_type, name, owner_address, public_key, endpoint_url]):
            return False

        # Validate address format (simplified)
        if not owner_address.startswith("0x") or len(owner_address) != 42:
            return False

        # Validate URL format (simplified)
        if not endpoint_url.startswith(("http://", "https://")):
            return False

        # Validate name
        if len(name) < 3 or len(name) > 100:
            return False

        return True

    def _generate_agent_id(self, owner_address: str, name: str) -> str:
        """Generate unique agent ID"""
        content = f"{owner_address}:{name}:{time.time()}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _create_capability_from_data(self, cap_data: dict) -> AgentCapability | None:
        """Create capability from data dictionary"""
        try:
            # Validate required fields
            required_fields = ["type", "name", "version", "cost_per_use"]
            if not all(field in cap_data for field in required_fields):
                return None

            # Parse capability type
            try:
                capability_type = CapabilityType(cap_data["type"])
            except ValueError:
                return None

            # Create capability
            return AgentCapability(
                capability_type=capability_type,
                name=cap_data["name"],
                version=cap_data["version"],
                parameters=cap_data.get("parameters", {}),
                performance_metrics=cap_data.get("performance_metrics", {}),
                cost_per_use=Decimal(str(cap_data["cost_per_use"])),
                availability=cap_data.get("availability", 1.0),
                max_concurrent_jobs=cap_data.get("max_concurrent_jobs", 1),
            )

        except Exception as e:
            log_error(f"Error creating capability: {e}")
            return None

    async def update_agent_capabilities(self, agent_id: str, capabilities: list[dict]) -> tuple[bool, str]:
        """Update agent capabilities"""
        if agent_id not in self.agents:
            return False, "Agent not found"

        agent = self.agents[agent_id]

        # Remove old capabilities from index
        for old_capability in agent.capabilities:
            self.capability_index[old_capability.capability_type].discard(agent_id)

        # Add new capabilities
        new_capabilities = []
        for cap_data in capabilities:
            capability = self._create_capability_from_data(cap_data)
            if capability:
                new_capabilities.append(capability)
                self.capability_index[capability.capability_type].add(agent_id)

        if not new_capabilities:
            return False, "No valid capabilities provided"

        agent.capabilities = new_capabilities
        agent.last_active = time.time()

        return True, "Capabilities updated successfully"

    async def get_agent_info(self, agent_id: str) -> AgentInfo | None:
        """Get agent information"""
        return self.agents.get(agent_id)


# Global agent registry
agent_registry: AgentRegistry | None = None


def get_agent_registry() -> AgentRegistry | None:
    """Get global agent registry"""
    return agent_registry


def create_agent_registry() -> AgentRegistry:
    """Create and set global agent registry"""
    global agent_registry
    agent_registry = AgentRegistry()
    return agent_registry
