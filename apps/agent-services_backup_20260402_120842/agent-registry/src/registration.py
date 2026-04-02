"""
Agent Registration System
Handles AI agent registration, capability management, and discovery
"""

import asyncio
import time
import json
import hashlib
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
from decimal import Decimal

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
    parameters: Dict
    performance_metrics: Dict
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
    capabilities: List[AgentCapability]
    reputation_score: float
    total_jobs_completed: int
    total_earnings: Decimal
    registration_time: float
    last_active: float
    status: AgentStatus
    metadata: Dict

class AgentRegistry:
    """Manages AI agent registration and discovery"""
    
    def __init__(self):
        self.agents: Dict[str, AgentInfo] = {}
        self.capability_index: Dict[CapabilityType, Set[str]] = {}  # capability -> agent_ids
        self.type_index: Dict[AgentType, Set[str]] = {}  # agent_type -> agent_ids
        self.reputation_scores: Dict[str, float] = {}
        self.registration_queue: List[Dict] = []
        
        # Registry parameters
        self.min_reputation_threshold = 0.5
        self.max_agents_per_type = 1000
        self.registration_fee = Decimal('100.0')
        self.inactivity_threshold = 86400 * 7  # 7 days
        
        # Initialize capability index
        for capability_type in CapabilityType:
            self.capability_index[capability_type] = set()
        
        # Initialize type index
        for agent_type in AgentType:
            self.type_index[agent_type] = set()
    
    async def register_agent(self, agent_type: AgentType, name: str, owner_address: str,
                           public_key: str, endpoint_url: str, capabilities: List[Dict],
                           metadata: Dict = None) -> Tuple[bool, str, Optional[str]]:
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
                total_earnings=Decimal('0'),
                registration_time=time.time(),
                last_active=time.time(),
                status=AgentStatus.REGISTERED,
                metadata=metadata or {}
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
    
    def _validate_registration_inputs(self, agent_type: AgentType, name: str, 
                                   owner_address: str, public_key: str, endpoint_url: str) -> bool:
        """Validate registration inputs"""
        # Check required fields
        if not all([agent_type, name, owner_address, public_key, endpoint_url]):
            return False
        
        # Validate address format (simplified)
        if not owner_address.startswith('0x') or len(owner_address) != 42:
            return False
        
        # Validate URL format (simplified)
        if not endpoint_url.startswith(('http://', 'https://')):
            return False
        
        # Validate name
        if len(name) < 3 or len(name) > 100:
            return False
        
        return True
    
    def _generate_agent_id(self, owner_address: str, name: str) -> str:
        """Generate unique agent ID"""
        content = f"{owner_address}:{name}:{time.time()}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def _create_capability_from_data(self, cap_data: Dict) -> Optional[AgentCapability]:
        """Create capability from data dictionary"""
        try:
            # Validate required fields
            required_fields = ['type', 'name', 'version', 'cost_per_use']
            if not all(field in cap_data for field in required_fields):
                return None
            
            # Parse capability type
            try:
                capability_type = CapabilityType(cap_data['type'])
            except ValueError:
                return None
            
            # Create capability
            return AgentCapability(
                capability_type=capability_type,
                name=cap_data['name'],
                version=cap_data['version'],
                parameters=cap_data.get('parameters', {}),
                performance_metrics=cap_data.get('performance_metrics', {}),
                cost_per_use=Decimal(str(cap_data['cost_per_use'])),
                availability=cap_data.get('availability', 1.0),
                max_concurrent_jobs=cap_data.get('max_concurrent_jobs', 1)
            )
            
        except Exception as e:
            log_error(f"Error creating capability: {e}")
            return None
    
    async def update_agent_status(self, agent_id: str, status: AgentStatus) -> Tuple[bool, str]:
        """Update agent status"""
        if agent_id not in self.agents:
            return False, "Agent not found"
        
        agent = self.agents[agent_id]
        old_status = agent.status
        agent.status = status
        agent.last_active = time.time()
        
        log_info(f"Agent {agent_id} status changed: {old_status.value} -> {status.value}")
        return True, "Status updated successfully"
    
    async def update_agent_capabilities(self, agent_id: str, capabilities: List[Dict]) -> Tuple[bool, str]:
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
    
    async def find_agents_by_capability(self, capability_type: CapabilityType, 
                                     filters: Dict = None) -> List[AgentInfo]:
        """Find agents by capability type"""
        agent_ids = self.capability_index.get(capability_type, set())
        
        agents = []
        for agent_id in agent_ids:
            agent = self.agents.get(agent_id)
            if agent and agent.status == AgentStatus.ACTIVE:
                if self._matches_filters(agent, filters):
                    agents.append(agent)
        
        # Sort by reputation (highest first)
        agents.sort(key=lambda x: x.reputation_score, reverse=True)
        return agents
    
    async def find_agents_by_type(self, agent_type: AgentType, filters: Dict = None) -> List[AgentInfo]:
        """Find agents by type"""
        agent_ids = self.type_index.get(agent_type, set())
        
        agents = []
        for agent_id in agent_ids:
            agent = self.agents.get(agent_id)
            if agent and agent.status == AgentStatus.ACTIVE:
                if self._matches_filters(agent, filters):
                    agents.append(agent)
        
        # Sort by reputation (highest first)
        agents.sort(key=lambda x: x.reputation_score, reverse=True)
        return agents
    
    def _matches_filters(self, agent: AgentInfo, filters: Dict) -> bool:
        """Check if agent matches filters"""
        if not filters:
            return True
        
        # Reputation filter
        if 'min_reputation' in filters:
            if agent.reputation_score < filters['min_reputation']:
                return False
        
        # Cost filter
        if 'max_cost_per_use' in filters:
            max_cost = Decimal(str(filters['max_cost_per_use']))
            if any(cap.cost_per_use > max_cost for cap in agent.capabilities):
                return False
        
        # Availability filter
        if 'min_availability' in filters:
            min_availability = filters['min_availability']
            if any(cap.availability < min_availability for cap in agent.capabilities):
                return False
        
        # Location filter (if implemented)
        if 'location' in filters:
            agent_location = agent.metadata.get('location')
            if agent_location != filters['location']:
                return False
        
        return True
    
    async def get_agent_info(self, agent_id: str) -> Optional[AgentInfo]:
        """Get agent information"""
        return self.agents.get(agent_id)
    
    async def search_agents(self, query: str, limit: int = 50) -> List[AgentInfo]:
        """Search agents by name or capability"""
        query_lower = query.lower()
        results = []
        
        for agent in self.agents.values():
            if agent.status != AgentStatus.ACTIVE:
                continue
            
            # Search in name
            if query_lower in agent.name.lower():
                results.append(agent)
                continue
            
            # Search in capabilities
            for capability in agent.capabilities:
                if (query_lower in capability.name.lower() or
                    query_lower in capability.capability_type.value):
                    results.append(agent)
                    break
        
        # Sort by relevance (reputation)
        results.sort(key=lambda x: x.reputation_score, reverse=True)
        return results[:limit]
    
    async def get_agent_statistics(self, agent_id: str) -> Optional[Dict]:
        """Get detailed statistics for an agent"""
        agent = self.agents.get(agent_id)
        if not agent:
            return None
        
        # Calculate additional statistics
        avg_job_earnings = agent.total_earnings / agent.total_jobs_completed if agent.total_jobs_completed > 0 else Decimal('0')
        days_active = (time.time() - agent.registration_time) / 86400
        jobs_per_day = agent.total_jobs_completed / days_active if days_active > 0 else 0
        
        return {
            'agent_id': agent_id,
            'name': agent.name,
            'type': agent.agent_type.value,
            'status': agent.status.value,
            'reputation_score': agent.reputation_score,
            'total_jobs_completed': agent.total_jobs_completed,
            'total_earnings': float(agent.total_earnings),
            'avg_job_earnings': float(avg_job_earnings),
            'jobs_per_day': jobs_per_day,
            'days_active': int(days_active),
            'capabilities_count': len(agent.capabilities),
            'last_active': agent.last_active,
            'registration_time': agent.registration_time
        }
    
    async def get_registry_statistics(self) -> Dict:
        """Get registry-wide statistics"""
        total_agents = len(self.agents)
        active_agents = len([a for a in self.agents.values() if a.status == AgentStatus.ACTIVE])
        
        # Count by type
        type_counts = {}
        for agent_type in AgentType:
            type_counts[agent_type.value] = len(self.type_index[agent_type])
        
        # Count by capability
        capability_counts = {}
        for capability_type in CapabilityType:
            capability_counts[capability_type.value] = len(self.capability_index[capability_type])
        
        # Reputation statistics
        reputations = [a.reputation_score for a in self.agents.values()]
        avg_reputation = sum(reputations) / len(reputations) if reputations else 0
        
        # Earnings statistics
        total_earnings = sum(a.total_earnings for a in self.agents.values())
        
        return {
            'total_agents': total_agents,
            'active_agents': active_agents,
            'inactive_agents': total_agents - active_agents,
            'agent_types': type_counts,
            'capabilities': capability_counts,
            'average_reputation': avg_reputation,
            'total_earnings': float(total_earnings),
            'registration_fee': float(self.registration_fee)
        }
    
    async def cleanup_inactive_agents(self) -> Tuple[int, str]:
        """Clean up inactive agents"""
        current_time = time.time()
        cleaned_count = 0
        
        for agent_id, agent in list(self.agents.items()):
            if (agent.status == AgentStatus.INACTIVE and
                current_time - agent.last_active > self.inactivity_threshold):
                
                # Remove from registry
                del self.agents[agent_id]
                
                # Update indexes
                self.type_index[agent.agent_type].discard(agent_id)
                for capability in agent.capabilities:
                    self.capability_index[capability.capability_type].discard(agent_id)
                
                cleaned_count += 1
        
        if cleaned_count > 0:
            log_info(f"Cleaned up {cleaned_count} inactive agents")
        
        return cleaned_count, f"Cleaned up {cleaned_count} inactive agents"

# Global agent registry
agent_registry: Optional[AgentRegistry] = None

def get_agent_registry() -> Optional[AgentRegistry]:
    """Get global agent registry"""
    return agent_registry

def create_agent_registry() -> AgentRegistry:
    """Create and set global agent registry"""
    global agent_registry
    agent_registry = AgentRegistry()
    return agent_registry
