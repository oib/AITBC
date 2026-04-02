#!/bin/bash

# Phase 4: Agent Network Scaling Setup Script
# Implements agent discovery, reputation system, and communication protocols

set -e

echo "=== PHASE 4: AGENT NETWORK SCALING SETUP ==="

# Configuration
AGENT_SERVICES_DIR="/opt/aitbc/apps/agent-services"
AGENT_REGISTRY_DIR="$AGENT_SERVICES_DIR/agent-registry/src"
AGENT_COORDINATOR_DIR="$AGENT_SERVICES_DIR/agent-coordinator/src"
AGENT_BRIDGE_DIR="$AGENT_SERVICES_DIR/agent-bridge/src"
AGENT_COMPLIANCE_DIR="$AGENT_SERVICES_DIR/agent-compliance/src"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_debug() {
    echo -e "${BLUE}[DEBUG]${NC} $1"
}

# Function to backup existing agent services
backup_agent_services() {
    log_info "Backing up existing agent services..."
    if [ -d "$AGENT_SERVICES_DIR" ]; then
        cp -r "$AGENT_SERVICES_DIR" "${AGENT_SERVICES_DIR}_backup_$(date +%Y%m%d_%H%M%S)"
        log_info "Backup completed"
    fi
}

# Function to create agent registration system
create_agent_registration() {
    log_info "Creating agent registration system..."
    
    cat > "$AGENT_REGISTRY_DIR/registration.py" << 'EOF'
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
EOF

    log_info "Agent registration system created"
}

# Function to create agent capability matching
create_capability_matching() {
    log_info "Creating agent capability matching system..."
    
    cat > "$AGENT_REGISTRY/src/matching.py" << 'EOF'
"""
Agent Capability Matching System
Matches job requirements with agent capabilities
"""

import asyncio
import time
import json
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass
from enum import Enum
from decimal import Decimal

from .registration import AgentRegistry, AgentInfo, AgentCapability, CapabilityType, AgentStatus

class MatchScore(Enum):
    PERFECT = 1.0
    EXCELLENT = 0.9
    GOOD = 0.8
    FAIR = 0.7
    POOR = 0.6

@dataclass
class JobRequirement:
    capability_type: CapabilityType
    name: str
    min_version: str
    required_parameters: Dict
    performance_requirements: Dict
    max_cost_per_use: Decimal
    min_availability: float
    priority: str  # low, medium, high, urgent

@dataclass
class MatchResult:
    agent_id: str
    agent_name: str
    match_score: float
    cost_per_use: Decimal
    availability: float
    estimated_completion_time: float
    confidence: float
    match_details: Dict

class CapabilityMatcher:
    """Matches job requirements with agent capabilities"""
    
    def __init__(self, agent_registry: AgentRegistry):
        self.agent_registry = agent_registry
        self.match_history: List[Dict] = []
        self.performance_weights = {
            'reputation': 0.3,
            'cost': 0.2,
            'availability': 0.2,
            'performance': 0.2,
            'experience': 0.1
        }
    
    async def find_matches(self, requirement: JobRequirement, limit: int = 10) -> List[MatchResult]:
        """Find best matching agents for a job requirement"""
        try:
            # Get candidate agents
            candidates = await self.agent_registry.find_agents_by_capability(
                requirement.capability_type,
                {
                    'max_cost_per_use': float(requirement.max_cost_per_use),
                    'min_availability': requirement.min_availability
                }
            )
            
            if not candidates:
                return []
            
            # Score each candidate
            scored_candidates = []
            for agent in candidates:
                match_result = await self._score_agent_match(agent, requirement)
                if match_result:
                    scored_candidates.append(match_result)
            
            # Sort by match score (highest first)
            scored_candidates.sort(key=lambda x: x.match_score, reverse=True)
            
            # Apply priority-based filtering
            filtered_candidates = await self._apply_priority_filter(scored_candidates, requirement.priority)
            
            return filtered_candidates[:limit]
            
        except Exception as e:
            log_error(f"Error finding matches: {e}")
            return []
    
    async def _score_agent_match(self, agent: AgentInfo, requirement: JobRequirement) -> Optional[MatchResult]:
        """Score how well an agent matches a requirement"""
        try:
            # Find matching capability
            matching_capability = None
            for capability in agent.capabilities:
                if (capability.capability_type == requirement.capability_type and
                    capability.name == requirement.name):
                    matching_capability = capability
                    break
            
            if not matching_capability:
                return None
            
            # Calculate component scores
            version_score = self._score_version_compatibility(matching_capability.version, requirement.min_version)
            parameter_score = self._score_parameter_compatibility(matching_capability.parameters, requirement.required_parameters)
            performance_score = self._score_performance_compatibility(matching_capability.performance_metrics, requirement.performance_requirements)
            cost_score = self._score_cost_compatibility(matching_capability.cost_per_use, requirement.max_cost_per_use)
            availability_score = self._score_availability_compatibility(matching_capability.availability, requirement.min_availability)
            
            # Calculate overall match score
            component_scores = [version_score, parameter_score, performance_score, cost_score, availability_score]
            base_match_score = sum(component_scores) / len(component_scores)
            
            # Apply reputation weighting
            reputation_weighted_score = base_match_score * (0.7 + 0.3 * agent.reputation_score)
            
            # Calculate confidence
            confidence = min(1.0, agent.total_jobs_completed / 100) if agent.total_jobs_completed > 0 else 0.1
            
            # Estimate completion time (simplified)
            estimated_time = self._estimate_completion_time(matching_capability, requirement)
            
            # Create match result
            match_result = MatchResult(
                agent_id=agent.agent_id,
                agent_name=agent.name,
                match_score=reputation_weighted_score,
                cost_per_use=matching_capability.cost_per_use,
                availability=matching_capability.availability,
                estimated_completion_time=estimated_time,
                confidence=confidence,
                match_details={
                    'version_score': version_score,
                    'parameter_score': parameter_score,
                    'performance_score': performance_score,
                    'cost_score': cost_score,
                    'availability_score': availability_score,
                    'reputation_score': agent.reputation_score,
                    'capability_version': matching_capability.version,
                    'required_version': requirement.min_version
                }
            )
            
            return match_result
            
        except Exception as e:
            log_error(f"Error scoring agent match: {e}")
            return None
    
    def _score_version_compatibility(self, agent_version: str, required_version: str) -> float:
        """Score version compatibility"""
        try:
            # Simple version comparison (semantic versioning)
            agent_parts = [int(x) for x in agent_version.split('.')]
            required_parts = [int(x) for x in required_version.split('.')]
            
            # Pad shorter version
            max_len = max(len(agent_parts), len(required_parts))
            agent_parts.extend([0] * (max_len - len(agent_parts)))
            required_parts.extend([0] * (max_len - len(required_parts)))
            
            # Compare versions
            for i in range(max_len):
                if agent_parts[i] > required_parts[i]:
                    return 1.0  # Better version
                elif agent_parts[i] < required_parts[i]:
                    return 0.0  # Worse version
            
            return 1.0  # Exact match
            
        except Exception:
            return 0.5  # Default score if version parsing fails
    
    def _score_parameter_compatibility(self, agent_params: Dict, required_params: Dict) -> float:
        """Score parameter compatibility"""
        if not required_params:
            return 1.0  # No requirements
        
        if not agent_params:
            return 0.0  # Agent has no parameters
        
        matched_params = 0
        total_params = len(required_params)
        
        for param_name, required_value in required_params.items():
            agent_value = agent_params.get(param_name)
            
            if agent_value is not None:
                # Simple compatibility check (can be more sophisticated)
                if isinstance(required_value, (int, float)):
                    if isinstance(agent_value, (int, float)):
                        if agent_value >= required_value:
                            matched_params += 1
                elif isinstance(required_value, str):
                    if agent_value == required_value:
                        matched_params += 1
                elif isinstance(required_value, list):
                    if agent_value in required_value:
                        matched_params += 1
                elif isinstance(required_value, dict):
                    # Check if all required keys exist
                    if all(k in agent_value for k in required_value.keys()):
                        matched_params += 1
        
        return matched_params / total_params if total_params > 0 else 0.0
    
    def _score_performance_compatibility(self, agent_performance: Dict, required_performance: Dict) -> float:
        """Score performance compatibility"""
        if not required_performance:
            return 1.0  # No requirements
        
        if not agent_performance:
            return 0.0  # No performance data
        
        matched_metrics = 0
        total_metrics = len(required_performance)
        
        for metric_name, required_value in required_performance.items():
            agent_value = agent_performance.get(metric_name)
            
            if agent_value is not None:
                # Check if agent meets or exceeds requirement
                if isinstance(required_value, (int, float)):
                    if isinstance(agent_value, (int, float)):
                        if agent_value >= required_value:
                            matched_metrics += 1
                elif isinstance(required_value, str):
                    if agent_value.lower() == required_value.lower():
                        matched_metrics += 1
        
        return matched_metrics / total_metrics if total_metrics > 0 else 0.0
    
    def _score_cost_compatibility(self, agent_cost: Decimal, max_cost: Decimal) -> float:
        """Score cost compatibility"""
        if agent_cost <= max_cost:
            # Better score for lower cost
            return 1.0 - (agent_cost / max_cost) * 0.5
        else:
            # Penalize overpriced agents
            return max(0.0, 1.0 - ((agent_cost - max_cost) / max_cost))
    
    def _score_availability_compatibility(self, agent_availability: float, min_availability: float) -> float:
        """Score availability compatibility"""
        if agent_availability >= min_availability:
            return 1.0
        else:
            return agent_availability / min_availability
    
    def _estimate_completion_time(self, capability: AgentCapability, requirement: JobRequirement) -> float:
        """Estimate job completion time"""
        # Base time on capability type
        base_times = {
            CapabilityType.TEXT_GENERATION: 30.0,  # 30 seconds
            CapabilityType.IMAGE_GENERATION: 120.0,  # 2 minutes
            CapabilityType.DATA_ANALYSIS: 300.0,  # 5 minutes
            CapabilityType.PREDICTION: 60.0,  # 1 minute
            CapabilityType.VALIDATION: 15.0,  # 15 seconds
            CapabilityType.COMPUTATION: 180.0  # 3 minutes
        }
        
        base_time = base_times.get(capability.capability_type, 60.0)
        
        # Adjust based on performance metrics
        if 'speed' in capability.performance_metrics:
            speed_factor = capability.performance_metrics['speed']
            base_time /= speed_factor
        
        # Adjust based on job priority
        priority_multipliers = {
            'low': 1.5,
            'medium': 1.0,
            'high': 0.7,
            'urgent': 0.5
        }
        
        priority_multiplier = priority_multipliers.get(requirement.priority, 1.0)
        
        return base_time * priority_multiplier
    
    async def _apply_priority_filter(self, candidates: List[MatchResult], priority: str) -> List[MatchResult]:
        """Apply priority-based filtering to candidates"""
        if priority == 'urgent':
            # For urgent jobs, prefer high-availability, high-reputation agents
            candidates.sort(key=lambda x: (x.availability, x.match_score, x.confidence), reverse=True)
        elif priority == 'high':
            # For high priority jobs, balance cost and quality
            candidates.sort(key=lambda x: (x.match_score, x.availability, -float(x.cost_per_use)), reverse=True)
        elif priority == 'medium':
            # For medium priority, optimize for cost-effectiveness
            candidates.sort(key=lambda x: (x.match_score / float(x.cost_per_use), x.availability), reverse=True)
        else:  # low priority
            # For low priority, minimize cost
            candidates.sort(key=lambda x: (float(x.cost_per_use), x.match_score))
        
        return candidates
    
    async def batch_match(self, requirements: List[JobRequirement]) -> Dict[str, List[MatchResult]]:
        """Match multiple job requirements in batch"""
        results = {}
        
        for i, requirement in enumerate(requirements):
            matches = await self.find_matches(requirement, limit=5)
            results[f"job_{i}"] = matches
        
        return results
    
    async def get_matching_statistics(self) -> Dict:
        """Get matching system statistics"""
        if not self.match_history:
            return {
                'total_matches': 0,
                'average_match_score': 0.0,
                'most_common_capability': None,
                'success_rate': 0.0
            }
        
        total_matches = len(self.match_history)
        avg_score = sum(match.get('score', 0) for match in self.match_history) / total_matches
        
        # Count capability types
        capability_counts = {}
        for match in self.match_history:
            capability = match.get('capability_type')
            if capability:
                capability_counts[capability] = capability_counts.get(capability, 0) + 1
        
        most_common_capability = max(capability_counts.items(), key=lambda x: x[1])[0] if capability_counts else None
        
        # Calculate success rate (matches that resulted in job completion)
        successful_matches = len([m for m in self.match_history if m.get('completed', False)])
        success_rate = successful_matches / total_matches if total_matches > 0 else 0
        
        return {
            'total_matches': total_matches,
            'average_match_score': avg_score,
            'most_common_capability': most_common_capability,
            'success_rate': success_rate,
            'capability_distribution': capability_counts
        }

# Global capability matcher
capability_matcher: Optional[CapabilityMatcher] = None

def get_capability_matcher() -> Optional[CapabilityMatcher]:
    """Get global capability matcher"""
    return capability_matcher

def create_capability_matcher(agent_registry: AgentRegistry) -> CapabilityMatcher:
    """Create and set global capability matcher"""
    global capability_matcher
    capability_matcher = CapabilityMatcher(agent_registry)
    return capability_matcher
EOF

    log_info "Agent capability matching created"
}

# Function to create agent reputation system
create_reputation_system() {
    log_info "Creating agent reputation system..."
    
    cat > "$AGENT_COORDINATOR_DIR/reputation.py" << 'EOF'
"""
Agent Reputation System
Manages agent trust scoring, reputation updates, and incentives
"""

import asyncio
import time
import json
import math
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
from decimal import Decimal

class ReputationEvent(Enum):
    JOB_COMPLETED = "job_completed"
    JOB_FAILED = "job_failed"
    JOB_CANCELLED = "job_cancelled"
    QUALITY_HIGH = "quality_high"
    QUALITY_LOW = "quality_low"
    TIMELY_DELIVERY = "timely_delivery"
    LATE_DELIVERY = "late_delivery"
    DISPUTE_WON = "dispute_won"
    DISPUTE_LOST = "dispute_lost"
    POSITIVE_FEEDBACK = "positive_feedback"
    NEGATIVE_FEEDBACK = "negative_feedback"

class ReputationLevel(Enum):
    BEGINNER = "beginner"          # 0.0 - 0.3
    INTERMEDIATE = "intermediate"  # 0.3 - 0.6
    ADVANCED = "advanced"        # 0.6 - 0.8
    EXPERT = "expert"            # 0.8 - 0.9
    MASTER = "master"            # 0.9 - 1.0

@dataclass
class ReputationScore:
    agent_id: str
    overall_score: float
    component_scores: Dict[str, float]
    level: ReputationLevel
    last_updated: float
    total_events: int
    recent_events: List[Dict]

@dataclass
class ReputationEvent:
    event_type: ReputationEvent
    agent_id: str
    score_change: float
    weight: float
    timestamp: float
    job_id: Optional[str]
    feedback: str
    metadata: Dict

class ReputationManager:
    """Manages agent reputation scoring and updates"""
    
    def __init__(self):
        self.reputation_scores: Dict[str, ReputationScore] = {}
        self.reputation_events: List[ReputationEvent] = []
        self.reputation_incentives: Dict[str, Dict] = {}
        
        # Reputation parameters
        self.base_score = 0.5  # Starting reputation
        self.max_score = 1.0
        self.min_score = 0.0
        self.decay_factor = 0.95  # Score decay over time
        self.decay_interval = 86400 * 30  # 30 days
        
        # Component weights
        self.component_weights = {
            'job_completion': 0.3,
            'job_quality': 0.25,
            'timeliness': 0.2,
            'dispute_resolution': 0.15,
            'customer_feedback': 0.1
        }
        
        # Event score multipliers
        self.event_multipliers = {
            ReputationEvent.JOB_COMPLETED: 0.1,
            ReputationEvent.JOB_FAILED: -0.2,
            ReputationEvent.JOB_CANCELLED: -0.05,
            ReputationEvent.QUALITY_HIGH: 0.15,
            ReputationEvent.QUALITY_LOW: -0.1,
            ReputationEvent.TIMELY_DELIVERY: 0.05,
            ReputationEvent.LATE_DELIVERY: -0.05,
            ReputationEvent.DISPUTE_WON: 0.1,
            ReputationEvent.DISPUTE_LOST: -0.15,
            ReputationEvent.POSITIVE_FEEDBACK: 0.05,
            ReputationEvent.NEGATIVE_FEEDBACK: -0.1
        }
        
        # Initialize reputation incentives
        self._initialize_incentives()
    
    def _initialize_incentives(self):
        """Initialize reputation-based incentives"""
        self.reputation_incentives = {
            'job_priority': {
                'expert': 1.2,    # 20% priority boost
                'master': 1.5    # 50% priority boost
            },
            'fee_discount': {
                'expert': 0.9,    # 10% discount
                'master': 0.8    # 20% discount
            },
            'visibility_boost': {
                'advanced': 1.1,  # 10% more visibility
                'expert': 1.2,    # 20% more visibility
                'master': 1.3    # 30% more visibility
            },
            'reward_multiplier': {
                'expert': 1.1,    # 10% reward bonus
                'master': 1.2    # 20% reward bonus
            }
        }
    
    async def initialize_agent_reputation(self, agent_id: str, initial_score: float = None) -> ReputationScore:
        """Initialize reputation for a new agent"""
        if agent_id in self.reputation_scores:
            return self.reputation_scores[agent_id]
        
        score = initial_score if initial_score is not None else self.base_score
        
        reputation_score = ReputationScore(
            agent_id=agent_id,
            overall_score=score,
            component_scores={
                'job_completion': score,
                'job_quality': score,
                'timeliness': score,
                'dispute_resolution': score,
                'customer_feedback': score
            },
            level=self._get_reputation_level(score),
            last_updated=time.time(),
            total_events=0,
            recent_events=[]
        )
        
        self.reputation_scores[agent_id] = reputation_score
        return reputation_score
    
    async def add_reputation_event(self, event_type: ReputationEvent, agent_id: str, 
                                   job_id: Optional[str] = None, feedback: str = "",
                                   weight: float = 1.0, metadata: Dict = None) -> Tuple[bool, str]:
        """Add a reputation event and update scores"""
        try:
            # Get or initialize reputation score
            reputation_score = self.reputation_scores.get(agent_id)
            if not reputation_score:
                reputation_score = await self.initialize_agent_reputation(agent_id)
            
            # Calculate score change
            multiplier = self.event_multipliers.get(event_type, 0.0)
            score_change = multiplier * weight
            
            # Create event
            event = ReputationEvent(
                event_type=event_type,
                agent_id=agent_id,
                score_change=score_change,
                weight=weight,
                timestamp=time.time(),
                job_id=job_id,
                feedback=feedback,
                metadata=metadata or {}
            )
            
            # Update component scores
            component = self._get_event_component(event_type)
            if component:
                current_score = reputation_score.component_scores[component]
                new_score = max(0.0, min(1.0, current_score + score_change))
                reputation_score.component_scores[component] = new_score
            
            # Update overall score
            await self._update_overall_score(reputation_score)
            
            # Update metadata
            reputation_score.last_updated = time.time()
            reputation_score.total_events += 1
            
            # Add to recent events
            event_data = {
                'type': event_type.value,
                'score_change': score_change,
                'timestamp': event.timestamp,
                'job_id': job_id,
                'feedback': feedback
            }
            
            reputation_score.recent_events.append(event_data)
            if len(reputation_score.recent_events) > 100:  # Keep last 100 events
                reputation_score.recent_events.pop(0)
            
            # Store event
            self.reputation_events.append(event)
            if len(self.reputation_events) > 10000:  # Keep last 10000 events
                self.reputation_events.pop(0)
            
            log_info(f"Reputation event added for {agent_id}: {event_type.value} ({score_change:+.3f})")
            return True, "Reputation event added successfully"
            
        except Exception as e:
            return False, f"Failed to add reputation event: {str(e)}"
    
    def _get_event_component(self, event_type: ReputationEvent) -> Optional[str]:
        """Get which reputation component an event affects"""
        component_mapping = {
            ReputationEvent.JOB_COMPLETED: 'job_completion',
            ReputationEvent.JOB_FAILED: 'job_completion',
            ReputationEvent.JOB_CANCELLED: 'job_completion',
            ReputationEvent.QUALITY_HIGH: 'job_quality',
            ReputationEvent.QUALITY_LOW: 'job_quality',
            ReputationEvent.TIMELY_DELIVERY: 'timeliness',
            ReputationEvent.LATE_DELIVERY: 'timeliness',
            ReputationEvent.DISPUTE_WON: 'dispute_resolution',
            ReputationEvent.DISPUTE_LOST: 'dispute_resolution',
            ReputationEvent.POSITIVE_FEEDBACK: 'customer_feedback',
            ReputationEvent.NEGATIVE_FEEDBACK: 'customer_feedback'
        }
        
        return component_mapping.get(event_type)
    
    async def _update_overall_score(self, reputation_score: ReputationScore):
        """Update overall reputation score from component scores"""
        weighted_sum = 0.0
        total_weight = 0.0
        
        for component, score in reputation_score.component_scores.items():
            weight = self.component_weights.get(component, 0.0)
            weighted_sum += score * weight
            total_weight += weight
        
        if total_weight > 0:
            reputation_score.overall_score = weighted_sum / total_weight
        else:
            reputation_score.overall_score = self.base_score
        
        # Update level
        reputation_score.level = self._get_reputation_level(reputation_score.overall_score)
    
    def _get_reputation_level(self, score: float) -> ReputationLevel:
        """Get reputation level from score"""
        if score < 0.3:
            return ReputationLevel.BEGINNER
        elif score < 0.6:
            return ReputationLevel.INTERMEDIATE
        elif score < 0.8:
            return ReputationLevel.ADVANCED
        elif score < 0.9:
            return ReputationLevel.EXPERT
        else:
            return ReputationLevel.MASTER
    
    async def get_reputation_score(self, agent_id: str) -> Optional[ReputationScore]:
        """Get reputation score for agent"""
        return self.reputation_scores.get(agent_id)
    
    async def update_reputation_decay(self):
        """Apply reputation score decay over time"""
        current_time = time.time()
        
        for reputation_score in self.reputation_scores.values():
            # Check if decay should be applied
            time_since_update = current_time - reputation_score.last_updated
            
            if time_since_update >= self.decay_interval:
                # Apply decay to component scores
                for component in reputation_score.component_scores:
                    current_score = reputation_score.component_scores[component]
                    decayed_score = current_score * self.decay_factor
                    reputation_score.component_scores[component] = max(self.min_score, decayed_score)
                
                # Update overall score
                await self._update_overall_score(reputation_score)
                
                # Update timestamp
                reputation_score.last_updated = current_time
                
                log_info(f"Applied reputation decay to {reputation_score.agent_id}")
    
    async def get_top_agents(self, limit: int = 50, capability_type: Optional[str] = None) -> List[ReputationScore]:
        """Get top agents by reputation score"""
        all_scores = list(self.reputation_scores.values())
        
        # Filter by capability if specified
        if capability_type:
            # This would require integration with agent registry
            # For now, return all agents
            pass
        
        # Sort by overall score
        all_scores.sort(key=lambda x: x.overall_score, reverse=True)
        
        return all_scores[:limit]
    
    async def get_reputation_incentives(self, agent_id: str) -> Dict:
        """Get reputation-based incentives for agent"""
        reputation_score = self.reputation_scores.get(agent_id)
        if not reputation_score:
            return {}
        
        level = reputation_score.level.value
        incentives = {}
        
        # Get incentives for this level and above
        for incentive_type, level_multipliers in self.reputation_incentives.items():
            multiplier = level_multipliers.get(level, 1.0)
            if multiplier != 1.0:
                incentives[incentive_type] = multiplier
        
        return incentives
    
    async def get_reputation_history(self, agent_id: str, limit: int = 50) -> List[Dict]:
        """Get reputation history for agent"""
        agent_events = [
            {
                'type': event.event_type.value,
                'score_change': event.score_change,
                'timestamp': event.timestamp,
                'job_id': event.job_id,
                'feedback': event.feedback,
                'weight': event.weight
            }
            for event in self.reputation_events
            if event.agent_id == agent_id
        ]
        
        # Sort by timestamp (newest first)
        agent_events.sort(key=lambda x: x['timestamp'], reverse=True)
        
        return agent_events[:limit]
    
    async def get_reputation_statistics(self, agent_id: Optional[str] = None) -> Dict:
        """Get reputation statistics"""
        if agent_id:
            # Statistics for specific agent
            reputation_score = self.reputation_scores.get(agent_id)
            if not reputation_score:
                return {}
            
            return {
                'agent_id': agent_id,
                'overall_score': reputation_score.overall_score,
                'level': reputation_score.level.value,
                'component_scores': reputation_score.component_scores,
                'total_events': reputation_score.total_events,
                'last_updated': reputation_score.last_updated,
                'recent_events': reputation_score.recent_events[-10:]  # Last 10 events
            }
        else:
            # Global statistics
            if not self.reputation_scores:
                return {
                    'total_agents': 0,
                    'average_score': 0.0,
                    'level_distribution': {},
                    'total_events': 0
                }
            
            scores = [rs.overall_score for rs in self.reputation_scores.values()]
            avg_score = sum(scores) / len(scores)
            
            # Level distribution
            level_counts = {}
            for rs in self.reputation_scores.values():
                level = rs.level.value
                level_counts[level] = level_counts.get(level, 0) + 1
            
            return {
                'total_agents': len(self.reputation_scores),
                'average_score': avg_score,
                'level_distribution': level_counts,
                'total_events': len(self.reputation_events),
                'component_averages': self._calculate_component_averages()
            }
    
    def _calculate_component_averages(self) -> Dict[str, float]:
        """Calculate average scores for each component"""
        if not self.reputation_scores:
            return {}
        
        component_averages = {}
        
        for component in self.component_weights.keys():
            scores = [rs.component_scores.get(component, 0.0) for rs in self.reputation_scores.values()]
            if scores:
                component_averages[component] = sum(scores) / len(scores)
            else:
                component_averages[component] = 0.0
        
        return component_averages
    
    async def batch_update_reputations(self, events: List[Dict]) -> Tuple[int, int]:
        """Update multiple reputations in batch"""
        success_count = 0
        error_count = 0
        
        for event_data in events:
            try:
                event_type = ReputationEvent(event_data['event_type'])
                agent_id = event_data['agent_id']
                job_id = event_data.get('job_id')
                feedback = event_data.get('feedback', '')
                weight = event_data.get('weight', 1.0)
                metadata = event_data.get('metadata', {})
                
                success, _ = await self.add_reputation_event(
                    event_type, agent_id, job_id, feedback, weight, metadata
                )
                
                if success:
                    success_count += 1
                else:
                    error_count += 1
                    
            except Exception as e:
                log_error(f"Error processing batch event: {e}")
                error_count += 1
        
        return success_count, error_count

# Global reputation manager
reputation_manager: Optional[ReputationManager] = None

def get_reputation_manager() -> Optional[ReputationManager]:
    """Get global reputation manager"""
    return reputation_manager

def create_reputation_manager() -> ReputationManager:
    """Create and set global reputation manager"""
    global reputation_manager
    reputation_manager = ReputationManager()
    return reputation_manager
EOF

    log_info "Agent reputation system created"
}

# Function to create cross-agent communication protocols
create_communication_protocols() {
    log_info "Creating cross-agent communication protocols..."
    
    cat > "$AGENT_BRIDGE/src/protocols.py" << 'EOF'
"""
Cross-Agent Communication Protocols
Defines standardized communication protocols for AI agents
"""

import asyncio
import time
import json
import hashlib
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict
from enum import Enum
from decimal import Decimal

class MessageType(Enum):
    HEARTBEAT = "heartbeat"
    JOB_OFFER = "job_offer"
    JOB_ACCEPT = "job_accept"
    JOB_REJECT = "job_reject"
    JOB_STATUS = "job_status"
    JOB_RESULT = "job_result"
    RESOURCE_REQUEST = "resource_request"
    RESOURCE_RESPONSE = "resource_response"
    COLLABORATION_REQUEST = "collaboration_request"
    COLLABORATION_RESPONSE = "collaboration_response"
    DISCOVERY_QUERY = "discovery_query"
    DISCOVERY_RESPONSE = "discovery_response"
    REPUTATION_QUERY = "reputation_query"
    REPUTATION_RESPONSE = "reputation_response"
    ERROR = "error"

class Priority(Enum):
    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4

@dataclass
class Message:
    message_id: str
    sender_id: str
    receiver_id: str
    message_type: MessageType
    priority: Priority
    payload: Dict
    timestamp: float
    signature: str
    ttl: int  # Time to live in seconds
    metadata: Dict

@dataclass
class ProtocolVersion:
    version: str
    supported_types: List[MessageType]
    encryption_required: bool
    compression_enabled: bool
    max_message_size: int

class CommunicationProtocol:
    """Standardized communication protocol for AI agents"""
    
    def __init__(self, agent_id: str, encryption_key: str = None):
        self.agent_id = agent_id
        self.encryption_key = encryption_key
        self.protocol_version = ProtocolVersion(
            version="1.0",
            supported_types=list(MessageType),
            encryption_required=encryption_key is not None,
            compression_enabled=True,
            max_message_size=1024 * 1024  # 1MB
        )
        
        self.message_handlers: Dict[MessageType, callable] = {}
        self.pending_messages: Dict[str, Message] = {}
        self.message_history: List[Message] = []
        
        # Communication parameters
        self.max_pending_messages = 1000
        self.message_timeout = 300  # 5 minutes
        self.heartbeat_interval = 60  # 1 minute
        self.retry_attempts = 3
        self.retry_delay = 5  # seconds
        
        # Initialize default handlers
        self._initialize_default_handlers()
    
    def _initialize_default_handlers(self):
        """Initialize default message handlers"""
        self.message_handlers[MessageType.HEARTBEAT] = self._handle_heartbeat
        self.message_handlers[MessageType.JOB_OFFER] = self._handle_job_offer
        self.message_handlers[MessageType.JOB_ACCEPT] = self._handle_job_accept
        self.message_handlers[MessageType.JOB_REJECT] = self._handle_job_reject
        self.message_handlers[MessageType.JOB_STATUS] = self._handle_job_status
        self.message_handlers[MessageType.JOB_RESULT] = self._handle_job_result
        self.message_handlers[MessageType.RESOURCE_REQUEST] = self._handle_resource_request
        self.message_handlers[MessageType.RESOURCE_RESPONSE] = self._handle_resource_response
        self.message_handlers[MessageType.DISCOVERY_QUERY] = self._handle_discovery_query
        self.message_handlers[MessageType.DISCOVERY_RESPONSE] = self._handle_discovery_response
        self.message_handlers[MessageType.ERROR] = self._handle_error
    
    async def send_message(self, receiver_id: str, message_type: MessageType, 
                          payload: Dict, priority: Priority = Priority.NORMAL,
                          ttl: int = 300, metadata: Dict = None) -> Tuple[bool, str, Optional[str]]:
        """Send message to another agent"""
        try:
            # Validate message
            if not self._validate_message(message_type, payload):
                return False, "Message validation failed", None
            
            # Create message
            message_id = self._generate_message_id()
            message = Message(
                message_id=message_id,
                sender_id=self.agent_id,
                receiver_id=receiver_id,
                message_type=message_type,
                priority=priority,
                payload=payload,
                timestamp=time.time(),
                signature="",  # Would sign with encryption key
                ttl=ttl,
                metadata=metadata or {}
            )
            
            # Sign message if encryption is enabled
            if self.encryption_key:
                message.signature = await self._sign_message(message)
            
            # Compress payload if enabled
            if self.protocol_version.compression_enabled:
                message.payload = await self._compress_payload(message.payload)
            
            # Send message (in real implementation, this would use network communication)
            success = await self._transmit_message(message)
            
            if success:
                # Store in pending messages
                self.pending_messages[message_id] = message
                
                # Add to history
                self.message_history.append(message)
                if len(self.message_history) > 1000:
                    self.message_history.pop(0)
                
                return True, "Message sent successfully", message_id
            else:
                return False, "Failed to transmit message", None
                
        except Exception as e:
            return False, f"Error sending message: {str(e)}", None
    
    async def receive_message(self, message_data: Dict) -> Tuple[bool, str]:
        """Receive and process incoming message"""
        try:
            # Deserialize message
            message = self._deserialize_message(message_data)
            
            if not message:
                return False, "Invalid message format"
            
            # Verify signature if encryption is enabled
            if self.encryption_key and not await self._verify_signature(message):
                return False, "Invalid message signature"
            
            # Decompress payload if needed
            if self.protocol_version.compression_enabled:
                message.payload = await self._decompress_payload(message.payload)
            
            # Check TTL
            if time.time() - message.timestamp > message.ttl:
                return False, "Message expired"
            
            # Handle message
            handler = self.message_handlers.get(message.message_type)
            if handler:
                success, response = await handler(message)
                if success:
                    return True, response
                else:
                    return False, f"Handler failed: {response}"
            else:
                return False, f"No handler for message type: {message.message_type.value}"
                
        except Exception as e:
            return False, f"Error processing message: {str(e)}"
    
    def _validate_message(self, message_type: MessageType, payload: Dict) -> bool:
        """Validate message format and content"""
        # Check if message type is supported
        if message_type not in self.protocol_version.supported_types:
            return False
        
        # Check payload size
        payload_size = len(json.dumps(payload).encode())
        if payload_size > self.protocol_version.max_message_size:
            return False
        
        # Type-specific validation
        if message_type == MessageType.JOB_OFFER:
            required_fields = ['job_id', 'capability_type', 'requirements', 'payment']
            return all(field in payload for field in required_fields)
        elif message_type == MessageType.JOB_RESULT:
            required_fields = ['job_id', 'result', 'status']
            return all(field in payload for field in required_fields)
        
        return True
    
    def _generate_message_id(self) -> str:
        """Generate unique message ID"""
        content = f"{self.agent_id}:{time.time()}:{hash(str(time.time()))}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    async def _sign_message(self, message: Message) -> str:
        """Sign message with encryption key"""
        # In real implementation, this would use cryptographic signing
        content = f"{message.sender_id}:{message.receiver_id}:{message.message_type.value}:{message.timestamp}"
        return hashlib.sha256(f"{content}:{self.encryption_key}".encode()).hexdigest()
    
    async def _verify_signature(self, message: Message) -> bool:
        """Verify message signature"""
        # In real implementation, this would verify cryptographic signature
        return True  # Placeholder
    
    async def _compress_payload(self, payload: Dict) -> Dict:
        """Compress message payload"""
        # In real implementation, this would use compression algorithm
        return payload  # Placeholder
    
    async def _decompress_payload(self, payload: Dict) -> Dict:
        """Decompress message payload"""
        # In real implementation, this would decompress the payload
        return payload  # Placeholder
    
    async def _transmit_message(self, message: Message) -> bool:
        """Transmit message to receiver"""
        # In real implementation, this would use network communication
        # For now, simulate successful transmission
        return True
    
    def _deserialize_message(self, message_data: Dict) -> Optional[Message]:
        """Deserialize message from dictionary"""
        try:
            return Message(
                message_id=message_data['message_id'],
                sender_id=message_data['sender_id'],
                receiver_id=message_data['receiver_id'],
                message_type=MessageType(message_data['message_type']),
                priority=Priority(message_data['priority']),
                payload=message_data['payload'],
                timestamp=message_data['timestamp'],
                signature=message_data['signature'],
                ttl=message_data['ttl'],
                metadata=message_data.get('metadata', {})
            )
        except Exception as e:
            log_error(f"Error deserializing message: {e}")
            return None
    
    # Default message handlers
    async def _handle_heartbeat(self, message: Message) -> Tuple[bool, str]:
        """Handle heartbeat message"""
        payload = message.payload
        
        # Update agent status
        status = {
            'agent_id': message.sender_id,
            'timestamp': message.timestamp,
            'status': payload.get('status', 'active'),
            'capabilities': payload.get('capabilities', []),
            'load': payload.get('load', 0.0),
            'location': payload.get('location', 'unknown')
        }
        
        # Store heartbeat status
        # In real implementation, this would update agent registry
        
        return True, "Heartbeat received"
    
    async def _handle_job_offer(self, message: Message) -> Tuple[bool, str]:
        """Handle job offer message"""
        payload = message.payload
        
        # Validate job offer
        required_fields = ['job_id', 'capability_type', 'requirements', 'payment']
        if not all(field in payload for field in required_fields):
            return False, "Invalid job offer format"
        
        # Check if agent can handle the job
        # In real implementation, this would check agent capabilities
        
        # Send response
        response_payload = {
            'job_id': payload['job_id'],
            'response': 'accept',  # or 'reject'
            'estimated_time': 300,  # seconds
            'cost': payload['payment']
        }
        
        await self.send_message(
            message.sender_id,
            MessageType.JOB_ACCEPT,
            response_payload,
            Priority.HIGH
        )
        
        return True, "Job offer processed"
    
    async def _handle_job_accept(self, message: Message) -> Tuple[bool, str]:
        """Handle job acceptance message"""
        payload = message.payload
        
        # Process job acceptance
        job_id = payload.get('job_id')
        response = payload.get('response')
        
        if response == 'accept':
            # Start job execution
            log_info(f"Job {job_id} accepted by {message.sender_id}")
        else:
            log_info(f"Job {job_id} rejected by {message.sender_id}")
        
        return True, "Job acceptance processed"
    
    async def _handle_job_reject(self, message: Message) -> Tuple[bool, str]:
        """Handle job rejection message"""
        payload = message.payload
        
        job_id = payload.get('job_id')
        reason = payload.get('reason', 'No reason provided')
        
        log_info(f"Job {job_id} rejected by {message.sender_id}: {reason}")
        
        return True, "Job rejection processed"
    
    async def _handle_job_status(self, message: Message) -> Tuple[bool, str]:
        """Handle job status update"""
        payload = message.payload
        
        job_id = payload.get('job_id')
        status = payload.get('status')
        progress = payload.get('progress', 0)
        
        log_info(f"Job {job_id} status: {status} ({progress}% complete)")
        
        return True, "Job status processed"
    
    async def _handle_job_result(self, message: Message) -> Tuple[bool, str]:
        """Handle job result"""
        payload = message.payload
        
        job_id = payload.get('job_id')
        result = payload.get('result')
        status = payload.get('status')
        
        log_info(f"Job {job_id} completed with status: {status}")
        
        # Process result
        # In real implementation, this would validate and store the result
        
        return True, "Job result processed"
    
    async def _handle_resource_request(self, message: Message) -> Tuple[bool, str]:
        """Handle resource request"""
        payload = message.payload
        
        resource_type = payload.get('resource_type')
        amount = payload.get('amount')
        
        # Check resource availability
        # In real implementation, this would check actual resources
        
        response_payload = {
            'resource_type': resource_type,
            'amount': amount,
            'available': True,
            'cost': 0.001 * amount
        }
        
        await self.send_message(
            message.sender_id,
            MessageType.RESOURCE_RESPONSE,
            response_payload
        )
        
        return True, "Resource request processed"
    
    async def _handle_resource_response(self, message: Message) -> Tuple[bool, str]:
        """Handle resource response"""
        payload = message.payload
        
        resource_type = payload.get('resource_type')
        available = payload.get('available')
        cost = payload.get('cost')
        
        log_info(f"Resource response for {resource_type}: available={available}, cost={cost}")
        
        return True, "Resource response processed"
    
    async def _handle_discovery_query(self, message: Message) -> Tuple[bool, str]:
        """Handle agent discovery query"""
        payload = message.payload
        
        query_type = payload.get('query_type')
        criteria = payload.get('criteria', {})
        
        # Search for agents
        # In real implementation, this would query the agent registry
        
        response_payload = {
            'query_type': query_type,
            'criteria': criteria,
            'agents': [],  # Would contain matching agents
            'total_count': 0
        }
        
        await self.send_message(
            message.sender_id,
            MessageType.DISCOVERY_RESPONSE,
            response_payload
        )
        
        return True, "Discovery query processed"
    
    async def _handle_discovery_response(self, message: Message) -> Tuple[bool, str]:
        """Handle discovery response"""
        payload = message.payload
        
        agents = payload.get('agents', [])
        total_count = payload.get('total_count', 0)
        
        log_info(f"Discovery response: {total_count} agents found")
        
        return True, "Discovery response processed"
    
    async def _handle_error(self, message: Message) -> Tuple[bool, str]:
        """Handle error message"""
        payload = message.payload
        
        error_code = payload.get('error_code')
        error_message = payload.get('error_message')
        original_message_id = payload.get('original_message_id')
        
        log_error(f"Error from {message.sender_id}: {error_code} - {error_message}")
        
        # Handle error (e.g., retry message, notify user, etc.)
        
        return True, "Error processed"
    
    async def start_heartbeat(self):
        """Start sending periodic heartbeat messages"""
        while True:
            try:
                # Create heartbeat payload
                payload = {
                    'status': 'active',
                    'capabilities': [],  # Would include agent capabilities
                    'load': 0.5,  # Would include actual load
                    'location': 'unknown'  # Would include actual location
                }
                
                # Send heartbeat to coordinator
                await self.send_message(
                    'coordinator',
                    MessageType.HEARTBEAT,
                    payload,
                    Priority.NORMAL
                )
                
                # Wait for next heartbeat
                await asyncio.sleep(self.heartbeat_interval)
                
            except Exception as e:
                log_error(f"Heartbeat error: {e}")
                await asyncio.sleep(10)
    
    async def get_communication_statistics(self) -> Dict:
        """Get communication statistics"""
        total_messages = len(self.message_history)
        pending_count = len(self.pending_messages)
        
        # Message type distribution
        type_counts = {}
        for message in self.message_history:
            msg_type = message.message_type.value
            type_counts[msg_type] = type_counts.get(msg_type, 0) + 1
        
        # Priority distribution
        priority_counts = {}
        for message in self.message_history:
            priority = message.priority.value
            priority_counts[priority] = priority_counts.get(priority, 0) + 1
        
        return {
            'total_messages': total_messages,
            'pending_messages': pending_count,
            'message_types': type_counts,
            'priorities': priority_counts,
            'protocol_version': self.protocol_version.version,
            'encryption_enabled': self.protocol_version.encryption_required,
            'compression_enabled': self.protocol_version.compression_enabled
        }

# Global communication protocol instances
communication_protocols: Dict[str, CommunicationProtocol] = {}

def get_communication_protocol(agent_id: str) -> Optional[CommunicationProtocol]:
    """Get communication protocol for agent"""
    return communication_protocols.get(agent_id)

def create_communication_protocol(agent_id: str, encryption_key: str = None) -> CommunicationProtocol:
    """Create communication protocol for agent"""
    protocol = CommunicationProtocol(agent_id, encryption_key)
    communication_protocols[agent_id] = protocol
    return protocol
EOF

    log_info "Cross-agent communication protocols created"
}

# Function to create agent lifecycle management
create_lifecycle_management() {
    log_info "Creating agent lifecycle management..."
    
    cat > "$AGENT_COORDINATOR_DIR/lifecycle.py" << 'EOF'
"""
Agent Lifecycle Management
Handles agent onboarding, offboarding, and lifecycle transitions
"""

import asyncio
import time
import json
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass
from enum import Enum

class LifecycleState(Enum):
    INITIALIZING = "initializing"
    REGISTERING = "registering"
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    DECOMMISSIONING = "decommissioning"
    DECOMMISSIONED = "decommissioned"

class LifecycleEvent(Enum):
    AGENT_CREATED = "agent_created"
    REGISTRATION_STARTED = "registration_started"
    REGISTRATION_COMPLETED = "registration_completed"
    ACTIVATION_STARTED = "activation_started"
    ACTIVATION_COMPLETED = "activation_completed"
    DEACTIVATION_STARTED = "deactivation_started"
    DEACTIVATION_COMPLETED = "deactivation_completed"
    SUSPENSION_STARTED = "suspension_started"
    SUSPENSION_COMPLETED = "suspension_completed"
    DECOMMISSIONING_STARTED = "decommissioning_started"
    DECOMMISSIONING_COMPLETED = "decommissioning_completed"

@dataclass
class AgentLifecycle:
    agent_id: str
    agent_type: str
    current_state: LifecycleState
    previous_state: LifecycleState
    created_at: float
    last_state_change: float
    total_state_changes: int
    events: List[Dict]
    metadata: Dict

class AgentLifecycleManager:
    """Manages agent lifecycle transitions and events"""
    
    def __init__(self):
        self.agent_lifecycles: Dict[str, AgentLifecycle] = {}
        self.state_transitions: Dict[LifecycleState, Set[LifecycleState]] = self._initialize_transitions()
        self.lifecycle_events: List[Dict] = []
        
        # Lifecycle parameters
        self.max_inactive_time = 86400 * 7  # 7 days
        self.max_suspension_time = 86400 * 30  # 30 days
        self.min_active_time = 3600  # 1 hour before deactivation
        self.auto_decommission_enabled = True
        
        # Initialize state machine
        self._initialize_state_machine()
    
    def _initialize_transitions(self) -> Dict[LifecycleState, Set[LifecycleState]]:
        """Initialize valid state transitions"""
        return {
            LifecycleState.INITIALIZING: {LifecycleState.REGISTERING},
            LifecycleState.REGISTERING: {LifecycleState.ACTIVE, LifecycleState.DECOMMISSIONING},
            LifecycleState.ACTIVE: {LifecycleState.INACTIVE, LifecycleState.SUSPENDED, LifecycleState.DECOMMISSIONING},
            LifecycleState.INACTIVE: {LifecycleState.ACTIVE, LifecycleState.DECOMMISSIONING},
            LifecycleState.SUSPENDED: {LifecycleState.ACTIVE, LifecycleState.DECOMMISSIONING},
            LifecycleState.DECOMMISSIONING: {LifecycleState.DECOMMISSIONED},
            LifecycleState.DECOMMISSIONED: set()
        }
    
    def _initialize_state_machine(self):
        """Initialize state machine handlers"""
        self.state_handlers = {
            LifecycleState.INITIALIZING: self._handle_initializing,
            LifecycleState.REGISTERING: self._handle_registering,
            LifecycleState.ACTIVE: self._handle_active,
            LifecycleState.INACTIVE: self._handle_inactive,
            LifecycleState.SUSPENDED: self._handle_suspended,
            LifecycleState.DECOMMISSIONING: self._handle_decommissioning,
            LifecycleState.DECOMMISSIONED: self._handle_decommissioned
        }
    
    async def create_agent_lifecycle(self, agent_id: str, agent_type: str, metadata: Dict = None) -> AgentLifecycle:
        """Create new agent lifecycle"""
        current_time = time.time()
        
        lifecycle = AgentLifecycle(
            agent_id=agent_id,
            agent_type=agent_type,
            current_state=LifecycleState.INITIALIZING,
            previous_state=LifecycleState.INITIALIZING,
            created_at=current_time,
            last_state_change=current_time,
            total_state_changes=0,
            events=[],
            metadata=metadata or {}
        )
        
        # Add initial event
        await self._add_lifecycle_event(lifecycle, LifecycleEvent.AGENT_CREATED, "Agent lifecycle created")
        
        self.agent_lifecycles[agent_id] = lifecycle
        
        log_info(f"Created lifecycle for agent {agent_id} ({agent_type})")
        return lifecycle
    
    async def transition_state(self, agent_id: str, new_state: LifecycleState, 
                              reason: str = "", metadata: Dict = None) -> Tuple[bool, str]:
        """Transition agent to new state"""
        lifecycle = self.agent_lifecycles.get(agent_id)
        if not lifecycle:
            return False, "Agent lifecycle not found"
        
        # Check if transition is valid
        valid_transitions = self.state_transitions.get(lifecycle.current_state, set())
        if new_state not in valid_transitions:
            return False, f"Invalid transition from {lifecycle.current_state.value} to {new_state.value}"
        
        # Record previous state
        previous_state = lifecycle.current_state
        
        # Update state
        lifecycle.current_state = new_state
        lifecycle.previous_state = previous_state
        lifecycle.last_state_change = time.time()
        lifecycle.total_state_changes += 1
        
        # Add transition event
        event_type = self._get_transition_event(new_state)
        await self._add_lifecycle_event(lifecycle, event_type, reason, metadata)
        
        # Handle state entry
        handler = self.state_handlers.get(new_state)
        if handler:
            await handler(lifecycle)
        
        log_info(f"Agent {agent_id} transitioned: {previous_state.value} -> {new_state.value}")
        return True, "State transition successful"
    
    def _get_transition_event(self, new_state: LifecycleState) -> LifecycleEvent:
        """Get lifecycle event for state transition"""
        event_mapping = {
            LifecycleState.REGISTERING: LifecycleEvent.REGISTRATION_STARTED,
            LifecycleState.ACTIVE: LifecycleEvent.ACTIVATION_STARTED,
            LifecycleState.INACTIVE: LifecycleEvent.DEACTIVATION_STARTED,
            LifecycleState.SUSPENDED: LifecycleEvent.SUSPENSION_STARTED,
            LifecycleState.DECOMMISSIONING: LifecycleEvent.DECOMMISSIONING_STARTED,
            LifecycleState.DECOMMISSIONED: LifecycleEvent.DECOMMISSIONING_COMPLETED
        }
        
        return event_mapping.get(new_state, LifecycleEvent.AGENT_CREATED)
    
    async def _add_lifecycle_event(self, lifecycle: AgentLifecycle, event_type: LifecycleEvent, 
                                  description: str = "", metadata: Dict = None):
        """Add lifecycle event"""
        event = {
            'event_type': event_type.value,
            'timestamp': time.time(),
            'description': description,
            'metadata': metadata or {}
        }
        
        lifecycle.events.append(event)
        if len(lifecycle.events) > 100:  # Keep last 100 events
            lifecycle.events.pop(0)
        
        # Add to global events
        self.lifecycle_events.append({
            'agent_id': lifecycle.agent_id,
            'event_type': event_type.value,
            'timestamp': event['timestamp'],
            'description': description,
            'metadata': event['metadata']
        })
        
        if len(self.lifecycle_events) > 10000:  # Keep last 10000 events
            self.lifecycle_events.pop(0)
    
    # State handlers
    async def _handle_initializing(self, lifecycle: AgentLifecycle):
        """Handle initializing state"""
        # Perform initialization tasks
        # In real implementation, this would set up agent infrastructure
        await asyncio.sleep(1)  # Simulate initialization time
        
        # Transition to registering
        await self.transition_state(lifecycle.agent_id, LifecycleState.REGISTERING, "Initialization completed")
    
    async def _handle_registering(self, lifecycle: AgentLifecycle):
        """Handle registering state"""
        # Perform registration tasks
        # In real implementation, this would register with agent registry
        await asyncio.sleep(2)  # Simulate registration time
        
        # Transition to active
        await self.transition_state(lifecycle.agent_id, LifecycleState.ACTIVE, "Registration completed")
    
    async def _handle_active(self, lifecycle: AgentLifecycle):
        """Handle active state"""
        # Agent is now active and can handle jobs
        # Periodic health checks will be performed
        pass
    
    async def _handle_inactive(self, lifecycle: AgentLifecycle):
        """Handle inactive state"""
        # Agent is temporarily inactive
        # Will be automatically reactivated or decommissioned based on time
        pass
    
    async def _handle_suspended(self, lifecycle: AgentLifecycle):
        """Handle suspended state"""
        # Agent is suspended due to policy violations or other issues
        # Will be reactivated after suspension period or decommissioned
        pass
    
    async def _handle_decommissioning(self, lifecycle: AgentLifecycle):
        """Handle decommissioning state"""
        # Perform cleanup tasks
        # In real implementation, this would clean up resources and data
        await asyncio.sleep(1)  # Simulate cleanup time
        
        # Transition to decommissioned
        await self.transition_state(lifecycle.agent_id, LifecycleState.DECOMMISSIONED, "Decommissioning completed")
    
    async def _handle_decommissioned(self, lifecycle: AgentLifecycle):
        """Handle decommissioned state"""
        # Agent is permanently decommissioned
        # Lifecycle will be archived or removed
        pass
    
    async def get_agent_lifecycle(self, agent_id: str) -> Optional[AgentLifecycle]:
        """Get agent lifecycle information"""
        return self.agent_lifecycles.get(agent_id)
    
    async def get_agents_by_state(self, state: LifecycleState) -> List[AgentLifecycle]:
        """Get agents in specific state"""
        return [
            lifecycle for lifecycle in self.agent_lifecycles.values()
            if lifecycle.current_state == state
        ]
    
    async def get_lifecycle_statistics(self) -> Dict:
        """Get lifecycle statistics"""
        if not self.agent_lifecycles:
            return {
                'total_agents': 0,
                'state_distribution': {},
                'average_lifecycle_duration': 0,
                'total_events': 0
            }
        
        # State distribution
        state_counts = {}
        for lifecycle in self.agent_lifecycles.values():
            state = lifecycle.current_state.value
            state_counts[state] = state_counts.get(state, 0) + 1
        
        # Average lifecycle duration
        current_time = time.time()
        durations = [
            current_time - lifecycle.created_at
            for lifecycle in self.agent_lifecycles.values()
        ]
        avg_duration = sum(durations) / len(durations) if durations else 0
        
        return {
            'total_agents': len(self.agent_lifecycles),
            'state_distribution': state_counts,
            'average_lifecycle_duration': avg_duration,
            'total_events': len(self.lifecycle_events),
            'recent_events': self.lifecycle_events[-10:]  # Last 10 events
        }
    
    async def cleanup_inactive_agents(self) -> Tuple[int, str]:
        """Clean up agents that have been inactive too long"""
        current_time = time.time()
        cleaned_count = 0
        
        for agent_id, lifecycle in list(self.agent_lifecycles.items()):
            if (lifecycle.current_state == LifecycleState.INACTIVE and
                current_time - lifecycle.last_state_change > self.max_inactive_time):
                
                # Decommission inactive agent
                success, message = await self.transition_state(
                    agent_id, LifecycleState.DECOMMISSIONING,
                    f"Auto-decommissioned after {self.max_inactive_time} seconds inactive"
                )
                
                if success:
                    cleaned_count += 1
        
        if cleaned_count > 0:
            log_info(f"Auto-decommissioned {cleaned_count} inactive agents")
        
        return cleaned_count, f"Auto-decommissioned {cleaned_count} inactive agents"
    
    async def cleanup_suspended_agents(self) -> Tuple[int, str]:
        """Clean up agents that have been suspended too long"""
        current_time = time.time()
        cleaned_count = 0
        
        for agent_id, lifecycle in list(self.agent_lifecycles.items()):
            if (lifecycle.current_state == LifecycleState.SUSPENDED and
                current_time - lifecycle.last_state_change > self.max_suspension_time):
                
                # Decommission suspended agent
                success, message = await self.transition_state(
                    agent_id, LifecycleState.DECOMMISSIONING,
                    f"Auto-decommissioned after {self.max_suspension_time} seconds suspended"
                )
                
                if success:
                    cleaned_count += 1
        
        if cleaned_count > 0:
            log_info(f"Auto-decommissioned {cleaned_count} suspended agents")
        
        return cleaned_count, f"Auto-decommissioned {cleaned_count} suspended agents"
    
    async def start_lifecycle_monitoring(self):
        """Start lifecycle monitoring service"""
        log_info("Starting agent lifecycle monitoring")
        
        while True:
            try:
                # Clean up inactive agents
                await self.cleanup_inactive_agents()
                
                # Clean up suspended agents
                await self.cleanup_suspended_agents()
                
                # Wait for next check
                await asyncio.sleep(3600)  # Check every hour
                
            except Exception as e:
                log_error(f"Lifecycle monitoring error: {e}")
                await asyncio.sleep(300)  # Retry after 5 minutes

# Global lifecycle manager
lifecycle_manager: Optional[AgentLifecycleManager] = None

def get_lifecycle_manager() -> Optional[AgentLifecycleManager]:
    """Get global lifecycle manager"""
    return lifecycle_manager

def create_lifecycle_manager() -> AgentLifecycleManager:
    """Create and set global lifecycle manager"""
    global lifecycle_manager
    lifecycle_manager = AgentLifecycleManager()
    return lifecycle_manager
EOF

    log_info "Agent lifecycle management created"
}

# Function to create agent behavior monitoring
create_behavior_monitoring() {
    log_info "Creating agent behavior monitoring..."
    
    cat > "$AGENT_COMPLIANCE_DIR/monitoring.py" << 'EOF'
"""
Agent Behavior Monitoring
Monitors agent performance, compliance, and behavior patterns
"""

import asyncio
import time
import json
import statistics
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
from decimal import Decimal

class BehaviorMetric(Enum):
    JOB_COMPLETION_RATE = "job_completion_rate"
    AVERAGE_COMPLETION_TIME = "average_completion_time"
    ERROR_RATE = "error_rate"
    RESPONSE_TIME = "response_time"
    RESOURCE_UTILIZATION = "resource_utilization"
    REPUTATION_TREND = "reputation_trend"
    COMPLIANCE_SCORE = "compliance_score"

class AlertLevel(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

@dataclass
class PerformanceMetric:
    metric_name: str
    current_value: float
    target_value: float
    threshold_min: float
    threshold_max: float
    trend: str  # improving, stable, declining
    last_updated: float

@dataclass
class BehaviorAlert:
    alert_id: str
    agent_id: str
    level: AlertLevel
    metric_name: str
    current_value: float
    threshold_value: float
    message: str
    timestamp: float
    resolved: bool

class AgentBehaviorMonitor:
    """Monitors agent behavior and performance metrics"""
    
    def __init__(self):
        self.agent_metrics: Dict[str, Dict[str, PerformanceMetric]] = {}
        self.behavior_alerts: List[BehaviorAlert] = []
        self.monitoring_rules = self._initialize_monitoring_rules()
        
        # Monitoring parameters
        self.monitoring_interval = 300  # 5 minutes
        self.metric_history_size = 100
        self.alert_retention_period = 86400 * 7  # 7 days
        self.auto_resolve_alerts = True
        
        # Initialize metrics tracking
        self._initialize_metrics_tracking()
    
    def _initialize_monitoring_rules(self) -> Dict[str, Dict]:
        """Initialize monitoring rules and thresholds"""
        return {
            BehaviorMetric.JOB_COMPLETION_RATE.value: {
                'target': 0.95,
                'threshold_min': 0.8,
                'threshold_max': 1.0,
                'alert_levels': {
                    0.8: AlertLevel.WARNING,
                    0.7: AlertLevel.ERROR,
                    0.6: AlertLevel.CRITICAL
                }
            },
            BehaviorMetric.AVERAGE_COMPLETION_TIME.value: {
                'target': 300.0,  # 5 minutes
                'threshold_min': 60.0,
                'threshold_max': 600.0,
                'alert_levels': {
                    500.0: AlertLevel.WARNING,
                    700.0: AlertLevel.ERROR,
                    900.0: AlertLevel.CRITICAL
                }
            },
            BehaviorMetric.ERROR_RATE.value: {
                'target': 0.05,  # 5%
                'threshold_min': 0.0,
                'threshold_max': 0.2,
                'alert_levels': {
                    0.1: AlertLevel.WARNING,
                    0.15: AlertLevel.ERROR,
                    0.2: AlertLevel.CRITICAL
                }
            },
            BehaviorMetric.RESPONSE_TIME.value: {
                'target': 5.0,  # 5 seconds
                'threshold_min': 1.0,
                'threshold_max': 15.0,
                'alert_levels': {
                    10.0: AlertLevel.WARNING,
                    12.0: AlertLevel.ERROR,
                    15.0: AlertLevel.CRITICAL
                }
            },
            BehaviorMetric.RESOURCE_UTILIZATION.value: {
                'target': 0.7,  # 70%
                'threshold_min': 0.2,
                'threshold_max': 0.95,
                'alert_levels': {
                    0.85: AlertLevel.WARNING,
                    0.9: AlertLevel.ERROR,
                    0.95: AlertLevel.CRITICAL
                }
            },
            BehaviorMetric.REPUTATION_TREND.value: {
                'target': 0.0,  # Stable
                'threshold_min': -0.1,
                'threshold_max': 0.1,
                'alert_levels': {
                    0.05: AlertLevel.WARNING,
                    0.1: AlertLevel.ERROR,
                    0.15: AlertLevel.CRITICAL
                }
            },
            BehaviorMetric.COMPLIANCE_SCORE.value: {
                'target': 0.9,
                'threshold_min': 0.7,
                'threshold_max': 1.0,
                'alert_levels': {
                    0.8: AlertLevel.WARNING,
                    0.7: AlertLevel.ERROR,
                    0.6: AlertLevel.CRITICAL
                }
            }
        }
    
    def _initialize_metrics_tracking(self):
        """Initialize metrics tracking for all behavior metrics"""
        for metric_type in BehaviorMetric:
            self.monitoring_rules[metric_type.value]
    
    async def start_monitoring(self):
        """Start behavior monitoring service"""
        log_info("Starting agent behavior monitoring")
        
        while True:
            try:
                # Update metrics for all agents
                await self._update_all_metrics()
                
                # Check for alerts
                await self._check_alert_conditions()
                
                # Resolve old alerts
                if self.auto_resolve_alerts:
                    await self._resolve_old_alerts()
                
                # Wait for next monitoring cycle
                await asyncio.sleep(self.monitoring_interval)
                
            except Exception as e:
                log_error(f"Behavior monitoring error: {e}")
                await asyncio.sleep(60)
    
    async def _update_all_metrics(self):
        """Update metrics for all agents"""
        # In real implementation, this would collect actual metrics from agent activities
        # For now, simulate metrics updates
        
        for agent_id in self.agent_metrics.keys():
            await self._update_agent_metrics(agent_id)
    
    async def _update_agent_metrics(self, agent_id: str):
        """Update metrics for specific agent"""
        if agent_id not in self.agent_metrics:
            self.agent_metrics[agent_id] = {}
        
        agent_metrics = self.agent_metrics[agent_id]
        
        # Update each metric type
        for metric_type in BehaviorMetric:
            current_value = await self._collect_metric_value(agent_id, metric_type)
            
            if current_value is not None:
                # Get existing metric or create new one
                metric = agent_metrics.get(metric_type.value)
                if not metric:
                    rule = self.monitoring_rules[metric_type.value]
                    metric = PerformanceMetric(
                        metric_name=metric_type.value,
                        current_value=current_value,
                        target_value=rule['target'],
                        threshold_min=rule['threshold_min'],
                        threshold_max=rule['threshold_max'],
                        trend='stable',
                        last_updated=time.time()
                    )
                    agent_metrics[metric_type.value] = metric
                else:
                    # Update existing metric
                    old_value = metric.current_value
                    metric.current_value = current_value
                    metric.last_updated = time.time()
                    
                    # Calculate trend
                    if current_value > old_value * 1.05:
                        metric.trend = 'improving'
                    elif current_value < old_value * 0.95:
                        metric.trend = 'declining'
                    else:
                        metric.trend = 'stable'
    
    async def _collect_metric_value(self, agent_id: str, metric_type: BehaviorMetric) -> Optional[float]:
        """Collect current value for a metric"""
        # In real implementation, this would collect actual metrics
        # For now, simulate realistic values
        
        if metric_type == BehaviorMetric.JOB_COMPLETION_RATE:
            # Simulate completion rate between 0.7 and 1.0
            import random
            return random.uniform(0.7, 1.0)
        
        elif metric_type == BehaviorMetric.AVERAGE_COMPLETION_TIME:
            # Simulate completion time between 60 and 600 seconds
            import random
            return random.uniform(60, 600)
        
        elif metric_type == BehaviorMetric.ERROR_RATE:
            # Simulate error rate between 0 and 0.2
            import random
            return random.uniform(0, 0.2)
        
        elif metric_type == BehaviorMetric.RESPONSE_TIME:
            # Simulate response time between 1 and 15 seconds
            import random
            return random.uniform(1, 15)
        
        elif metric_type == BehaviorMetric.RESOURCE_UTILIZATION:
            # Simulate resource utilization between 0.2 and 0.95
            import random
            return random.uniform(0.2, 0.95)
        
        elif metric_type == BehaviorMetric.REPUTATION_TREND:
            # Simulate reputation trend between -0.15 and 0.15
            import random
            return random.uniform(-0.15, 0.15)
        
        elif metric_type == BehaviorMetric.COMPLIANCE_SCORE:
            # Simulate compliance score between 0.6 and 1.0
            import random
            return random.uniform(0.6, 1.0)
        
        return None
    
    async def _check_alert_conditions(self):
        """Check for alert conditions"""
        current_time = time.time()
        
        for agent_id, agent_metrics in self.agent_metrics.items():
            for metric_name, metric in agent_metrics.items():
                rule = self.monitoring_rules.get(metric_name)
                if not rule:
                    continue
                
                # Check if value exceeds thresholds
                if metric.current_value > rule['threshold_max']:
                    await self._create_alert(
                        agent_id, metric_name, metric.current_value,
                        rule['threshold_max'], AlertLevel.ERROR
                    )
                elif metric.current_value < rule['threshold_min']:
                    await self._create_alert(
                        agent_id, metric_name, metric.current_value,
                        rule['threshold_min'], AlertLevel.WARNING
                    )
                
                # Check specific alert levels
                alert_levels = rule.get('alert_levels', {})
                for threshold_value, alert_level in alert_levels.items():
                    if ((metric_name == BehaviorMetric.JOB_COMPLETION_RATE.value and
                         metric.current_value < threshold_value) or
                        (metric_name != BehaviorMetric.JOB_COMPLETION_RATE.value and
                         metric.current_value > threshold_value)):
                        
                        await self._create_alert(
                            agent_id, metric_name, metric.current_value,
                            threshold_value, alert_level
                        )
                        break
    
    async def _create_alert(self, agent_id: str, metric_name: str, current_value: float,
                           threshold_value: float, level: AlertLevel):
        """Create behavior alert"""
        # Check if similar alert already exists
        existing_alert = None
        for alert in self.behavior_alerts:
            if (alert.agent_id == agent_id and
                alert.metric_name == metric_name and
                not alert.resolved and
                alert.level == level):
                existing_alert = alert
                break
        
        if existing_alert:
            # Update existing alert
            existing_alert.current_value = current_value
            existing_alert.timestamp = time.time()
        else:
            # Create new alert
            alert_id = f"alert_{agent_id}_{metric_name}_{int(time.time())}"
            
            alert = BehaviorAlert(
                alert_id=alert_id,
                agent_id=agent_id,
                level=level,
                metric_name=metric_name,
                current_value=current_value,
                threshold_value=threshold_value,
                message=self._generate_alert_message(agent_id, metric_name, current_value, threshold_value, level),
                timestamp=time.time(),
                resolved=False
            )
            
            self.behavior_alerts.append(alert)
            log_info(f"Behavior alert created: {alert_id} - {level.value}")
    
    def _generate_alert_message(self, agent_id: str, metric_name: str, current_value: float,
                              threshold_value: float, level: AlertLevel) -> str:
        """Generate alert message"""
        metric_display = metric_name.replace('_', ' ').title()
        
        if level == AlertLevel.WARNING:
            return f"Warning: {agent_id} {metric_display} is {current_value:.3f} (threshold: {threshold_value:.3f})"
        elif level == AlertLevel.ERROR:
            return f"Error: {agent_id} {metric_display} is {current_value:.3f} (threshold: {threshold_value:.3f})"
        elif level == AlertLevel.CRITICAL:
            return f"Critical: {agent_id} {metric_display} is {current_value:.3f} (threshold: {threshold_value:.3f})"
        else:
            return f"Info: {agent_id} {metric_display} is {current_value:.3f} (threshold: {threshold_value:.3f})"
    
    async def _resolve_old_alerts(self):
        """Resolve old alerts"""
        current_time = time.time()
        resolved_count = 0
        
        for alert in self.behavior_alerts:
            if not alert.resolved and current_time - alert.timestamp > self.alert_retention_period:
                alert.resolved = True
                resolved_count += 1
        
        if resolved_count > 0:
            log_info(f"Resolved {resolved_count} old behavior alerts")
    
    async def get_agent_metrics(self, agent_id: str) -> Optional[Dict[str, PerformanceMetric]]:
        """Get metrics for specific agent"""
        return self.agent_metrics.get(agent_id)
    
    async def get_agent_alerts(self, agent_id: str, resolved: bool = None) -> List[BehaviorAlert]:
        """Get alerts for specific agent"""
        alerts = [alert for alert in self.behavior_alerts if alert.agent_id == agent_id]
        
        if resolved is not None:
            alerts = [alert for alert in alerts if alert.resolved == resolved]
        
        return alerts
    
    async def get_monitoring_statistics(self) -> Dict:
        """Get monitoring statistics"""
        total_agents = len(self.agent_metrics)
        total_alerts = len(self.behavior_alerts)
        active_alerts = len([a for a in self.behavior_alerts if not a.resolved])
        
        # Alert level distribution
        alert_levels = {}
        for alert in self.behavior_alerts:
            level = alert.level.value
            alert_levels[level] = alert_levels.get(level, 0) + 1
        
        # Metric statistics
        metric_stats = {}
        for metric_type in BehaviorMetric:
            values = []
            for agent_metrics in self.agent_metrics.values():
                metric = agent_metrics.get(metric_type.value)
                if metric:
                    values.append(metric.current_value)
            
            if values:
                metric_stats[metric_type.value] = {
                    'count': len(values),
                    'average': statistics.mean(values),
                    'min': min(values),
                    'max': max(values),
                    'std_dev': statistics.stdev(values) if len(values) > 1 else 0
                }
        
        return {
            'total_agents': total_agents,
            'total_alerts': total_alerts,
            'active_alerts': active_alerts,
            'alert_levels': alert_levels,
            'metric_statistics': metric_stats
        }

# Global behavior monitor
behavior_monitor: Optional[AgentBehaviorMonitor] = None

def get_behavior_monitor() -> Optional[AgentBehaviorMonitor]:
    """Get global behavior monitor"""
    return behavior_monitor

def create_behavior_monitor() -> AgentBehaviorMonitor:
    """Create and set global behavior monitor"""
    global behavior_monitor
    behavior_monitor = AgentBehaviorMonitor()
    return behavior_monitor
EOF

    log_info "Agent behavior monitoring created"
}

# Function to create agent tests
create_agent_tests() {
    log_info "Creating agent network test suite..."
    
    mkdir -p "/opt/aitbc/apps/agent-services/tests"
    
    cat > "/opt/aitbc/apps/agent-services/tests/test_registration.py" << 'EOF'
"""
Tests for Agent Registration System
"""

import pytest
import asyncio
import time
from unittest.mock import Mock, patch

from agent_services.agent_registry.src.registration import AgentRegistry, AgentType, AgentStatus, CapabilityType

class TestAgentRegistry:
    """Test cases for agent registry"""
    
    def setup_method(self):
        """Setup test environment"""
        self.registry = AgentRegistry()
    
    def test_register_agent(self):
        """Test agent registration"""
        capabilities = [
            {
                'type': 'text_generation',
                'name': 'GPT-4',
                'version': '1.0',
                'cost_per_use': 0.001,
                'availability': 0.95,
                'max_concurrent_jobs': 5,
                'parameters': {'max_tokens': 1000},
                'performance_metrics': {'speed': 1.0}
            }
        ]
        
        success, message, agent_id = asyncio.run(
            self.registry.register_agent(
                AgentType.AI_MODEL,
                "TestAgent",
                "0x1234567890123456789012345678901234567890",
                "test_public_key",
                "http://localhost:8080",
                capabilities
            )
        )
        
        assert success, f"Registration failed: {message}"
        assert agent_id is not None
        
        # Check agent info
        agent_info = asyncio.run(self.registry.get_agent_info(agent_id))
        assert agent_info is not None
        assert agent_info.name == "TestAgent"
        assert agent_info.agent_type == AgentType.AI_MODEL
        assert len(agent_info.capabilities) == 1
        assert agent_info.status == AgentStatus.REGISTERED
    
    def test_register_agent_invalid_inputs(self):
        """Test agent registration with invalid inputs"""
        capabilities = []
        
        # Invalid address
        success, message, agent_id = asyncio.run(
            self.registry.register_agent(
                AgentType.AI_MODEL,
                "TestAgent",
                "invalid_address",  # Invalid address
                "test_public_key",
                "http://localhost:8080",
                capabilities
            )
        )
        
        assert not success
        assert "invalid" in message.lower()
    
    def test_register_agent_no_capabilities(self):
        """Test agent registration with no capabilities"""
        capabilities = []
        
        success, message, agent_id = asyncio.run(
            self.registry.register_agent(
                AgentType.AI_MODEL,
                "TestAgent",
                "0x1234567890123456789012345678901234567890",
                "test_public_key",
                "http://localhost:8080",
                capabilities
            )
        )
        
        assert not success
        assert "capability" in message.lower()
    
    def test_update_agent_status(self):
        """Test updating agent status"""
        # First register an agent
        capabilities = [{
            'type': 'text_generation',
            'name': 'GPT-4',
            'version': '1.0',
            'cost_per_use': 0.001,
            'availability': 0.95,
            'max_concurrent_jobs': 5
        }]
        
        success, message, agent_id = asyncio.run(
            self.registry.register_agent(
                AgentType.AI_MODEL,
                "TestAgent",
                "0x1234567890123456789012345678901234567890",
                "test_public_key",
                "http://localhost:8080",
                capabilities
            )
        )
        
        assert success
        
        # Update status to active
        success, message = asyncio.run(
            self.registry.update_agent_status(agent_id, AgentStatus.ACTIVE)
        )
        
        assert success, f"Status update failed: {message}"
        
        # Check updated status
        agent_info = asyncio.run(self.registry.get_agent_info(agent_id))
        assert agent_info.status == AgentStatus.ACTIVE
    
    def test_find_agents_by_capability(self):
        """Test finding agents by capability"""
        # Register multiple agents with different capabilities
        capabilities1 = [{
            'type': 'text_generation',
            'name': 'GPT-4',
            'version': '1.0',
            'cost_per_use': 0.001,
            'availability': 0.95,
            'max_concurrent_jobs': 5
        }]
        
        capabilities2 = [{
            'type': 'image_generation',
            'name': 'DALL-E',
            'version': '1.0',
            'cost_per_use': 0.01,
            'availability': 0.8,
            'max_concurrent_jobs': 2
        }]
        
        # Register agents
        success1, _, agent1_id = asyncio.run(
            self.registry.register_agent(
                AgentType.AI_MODEL,
                "TextAgent",
                "0x1234567890123456789012345678901234567891",
                "test_public_key1",
                "http://localhost:8081",
                capabilities1
            )
        )
        
        success2, _, agent2_id = asyncio.run(
            self.registry.register_agent(
                AgentType.AI_MODEL,
                "ImageAgent",
                "0x1234567890123456789012345678901234567892",
                "test_public_key2",
                "http://localhost:8082",
                capabilities2
            )
        )
        
        assert success1 and success2
        
        # Set agents to active
        asyncio.run(self.registry.update_agent_status(agent1_id, AgentStatus.ACTIVE))
        asyncio.run(self.registry.update_agent_status(agent2_id, AgentStatus.ACTIVE))
        
        # Find text generation agents
        text_agents = asyncio.run(
            self.registry.find_agents_by_capability(CapabilityType.TEXT_GENERATION)
        )
        
        assert len(text_agents) == 1
        assert text_agents[0].agent_id == agent1_id
        
        # Find image generation agents
        image_agents = asyncio.run(
            self.registry.find_agents_by_capability(CapabilityType.IMAGE_GENERATION)
        )
        
        assert len(image_agents) == 1
        assert image_agents[0].agent_id == agent2_id
    
    def test_search_agents(self):
        """Test searching agents"""
        # Register an agent
        capabilities = [{
            'type': 'text_generation',
            'name': 'GPT-4',
            'version': '1.0',
            'cost_per_use': 0.001,
            'availability': 0.95,
            'max_concurrent_jobs': 5
        }]
        
        success, _, agent_id = asyncio.run(
            self.registry.register_agent(
                AgentType.AI_MODEL,
                "GPTAgent",
                "0x1234567890123456789012345678901234567890",
                "test_public_key",
                "http://localhost:8080",
                capabilities
            )
        )
        
        assert success
        asyncio.run(self.registry.update_agent_status(agent_id, AgentStatus.ACTIVE))
        
        # Search by name
        results = asyncio.run(self.registry.search_agents("GPT"))
        assert len(results) == 1
        assert results[0].agent_id == agent_id
        
        # Search by capability
        results = asyncio.run(self.registry.search_agents("text_generation"))
        assert len(results) == 1
        assert results[0].agent_id == agent_id
        
        # Search with no results
        results = asyncio.run(self.registry.search_agents("nonexistent"))
        assert len(results) == 0
    
    def test_get_registry_statistics(self):
        """Test getting registry statistics"""
        stats = asyncio.run(self.registry.get_registry_statistics())
        
        assert 'total_agents' in stats
        assert 'active_agents' in stats
        assert 'agent_types' in stats
        assert 'capabilities' in stats
        assert 'average_reputation' in stats
        assert stats['total_agents'] >= 0

if __name__ == "__main__":
    pytest.main([__file__])
EOF

    log_info "Agent network test suite created"
}

# Function to setup test environment
setup_test_environment() {
    log_info "Setting up agent network test environment..."
    
    # Create test configuration
    cat > "/opt/aitbc/config/agent_network_test.json" << 'EOF'
{
    "agent_registry": {
        "min_reputation_threshold": 0.5,
        "max_agents_per_type": 1000,
        "registration_fee": 100.0,
        "inactivity_threshold": 604800
    },
    "capability_matching": {
        "performance_weights": {
            "reputation": 0.3,
            "cost": 0.2,
            "availability": 0.2,
            "performance": 0.2,
            "experience": 0.1
        }
    },
    "reputation": {
        "base_score": 0.5,
        "max_score": 1.0,
        "min_score": 0.0,
        "decay_factor": 0.95,
        "decay_interval": 2592000
    },
    "communication": {
        "max_message_size": 1048576,
        "message_timeout": 300,
        "heartbeat_interval": 60,
        "retry_attempts": 3
    },
    "lifecycle": {
        "max_inactive_time": 604800,
        "max_suspension_time": 2592000,
        "min_active_time": 3600
    },
    "monitoring": {
        "monitoring_interval": 300,
        "alert_retention_period": 604800,
        "auto_resolve_alerts": true
    }
}
EOF

    log_info "Agent network test configuration created"
}

# Function to run agent tests
run_agent_tests() {
    log_info "Running agent network tests..."
    
    cd /opt/aitbc/apps/agent-services
    
    # Install test dependencies if needed
    if ! python -c "import pytest" 2>/dev/null; then
        log_info "Installing pytest..."
        pip install pytest pytest-asyncio
    fi
    
    # Run tests
    python -m pytest tests/ -v
    
    if [ $? -eq 0 ]; then
        log_info "All agent tests passed!"
    else
        log_error "Some agent tests failed!"
        return 1
    fi
}

# Main execution
main() {
    log_info "Starting Phase 4: Agent Network Scaling Setup"
    
    # Create necessary directories
    mkdir -p "$AGENT_REGISTRY_DIR"
    mkdir -p "$AGENT_COORDINATOR_DIR"
    mkdir -p "$AGENT_BRIDGE_DIR"
    mkdir -p "$AGENT_COMPLIANCE_DIR"
    
    # Execute setup steps
    backup_agent_services
    create_agent_registration
    create_capability_matching
    create_reputation_system
    create_communication_protocols
    create_lifecycle_management
    create_behavior_monitoring
    create_agent_tests
    setup_test_environment
    
    # Run tests
    if run_agent_tests; then
        log_info "Phase 4 agent network scaling setup completed successfully!"
        log_info "Next steps:"
        log_info "1. Configure agent network parameters"
        log_info "2. Initialize agent registry services"
        log_info "3. Set up reputation and incentive systems"
        log_info "4. Configure communication protocols"
        log_info "5. Proceed to Phase 5: Smart Contract Infrastructure"
    else
        log_error "Phase 4 setup failed - check test output"
        return 1
    fi
}

# Execute main function
main "$@"
