"""
Message Types and Routing System for AITBC Agent Coordination
"""

import asyncio
import json
from enum import Enum
from typing import Dict, List, Optional, Any, Callable, Union
from dataclasses import dataclass, field
from datetime import datetime, UTC, timedelta
import uuid
import hashlib
from pydantic import BaseModel, Field, validator
from .communication import AgentMessage, MessageType, Priority

from aitbc import get_logger

logger = get_logger(__name__)

class MessageStatus(str, Enum):
    """Message processing status"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"

class RoutingStrategy(str, Enum):
    """Message routing strategies"""
    ROUND_ROBIN = "round_robin"
    LOAD_BALANCED = "load_balanced"
    PRIORITY_BASED = "priority_based"
    RANDOM = "random"
    DIRECT = "direct"
    BROADCAST = "broadcast"

class DeliveryMode(str, Enum):
    """Message delivery modes"""
    FIRE_AND_FORGET = "fire_and_forget"
    AT_LEAST_ONCE = "at_least_once"
    EXACTLY_ONCE = "exactly_once"
    PERSISTENT = "persistent"

@dataclass
class RoutingRule:
    """Routing rule for message processing"""
    rule_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    condition: Dict[str, Any] = field(default_factory=dict)
    action: str = "forward"  # forward, transform, filter, route
    target: Optional[str] = None
    priority: int = 0
    enabled: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    def matches(self, message: AgentMessage) -> bool:
        """Check if message matches routing rule conditions"""
        for key, value in self.condition.items():
            message_value = getattr(message, key, None)
            if message_value != value:
                return False
        return True

class TaskMessage(BaseModel):
    """Task-specific message structure"""
    task_id: str = Field(..., description="Unique task identifier")
    task_type: str = Field(..., description="Type of task")
    task_data: Dict[str, Any] = Field(default_factory=dict, description="Task data")
    requirements: Dict[str, Any] = Field(default_factory=dict, description="Task requirements")
    deadline: Optional[datetime] = Field(None, description="Task deadline")
    priority: Priority = Field(Priority.NORMAL, description="Task priority")
    assigned_agent: Optional[str] = Field(None, description="Assigned agent ID")
    status: str = Field("pending", description="Task status")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    @validator('deadline')
    def validate_deadline(cls, v):
        if v and v < datetime.now(datetime.UTC):
            raise ValueError("Deadline cannot be in the past")
        return v

class CoordinationMessage(BaseModel):
    """Coordination-specific message structure"""
    coordination_id: str = Field(..., description="Unique coordination identifier")
    coordination_type: str = Field(..., description="Type of coordination")
    participants: List[str] = Field(default_factory=list, description="Participating agents")
    coordination_data: Dict[str, Any] = Field(default_factory=dict, description="Coordination data")
    decision_deadline: Optional[datetime] = Field(None, description="Decision deadline")
    consensus_threshold: float = Field(0.5, description="Consensus threshold")
    status: str = Field("pending", description="Coordination status")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class StatusMessage(BaseModel):
    """Status update message structure"""
    agent_id: str = Field(..., description="Agent ID")
    status_type: str = Field(..., description="Type of status")
    status_data: Dict[str, Any] = Field(default_factory=dict, description="Status data")
    health_score: float = Field(1.0, description="Agent health score")
    load_metrics: Dict[str, float] = Field(default_factory=dict, description="Load metrics")
    capabilities: List[str] = Field(default_factory=list, description="Agent capabilities")
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class DiscoveryMessage(BaseModel):
    """Agent discovery message structure"""
    agent_id: str = Field(..., description="Agent ID")
    agent_type: str = Field(..., description="Type of agent")
    capabilities: List[str] = Field(default_factory=list, description="Agent capabilities")
    services: List[str] = Field(default_factory=list, description="Available services")
    endpoints: Dict[str, str] = Field(default_factory=dict, description="Service endpoints")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class ConsensusMessage(BaseModel):
    """Consensus message structure"""
    consensus_id: str = Field(..., description="Unique consensus identifier")
    proposal: Dict[str, Any] = Field(..., description="Consensus proposal")
    voting_options: List[Dict[str, Any]] = Field(default_factory=list, description="Voting options")
    votes: Dict[str, str] = Field(default_factory=dict, description="Agent votes")
    voting_deadline: datetime = Field(..., description="Voting deadline")
    consensus_algorithm: str = Field("majority", description="Consensus algorithm")
    status: str = Field("pending", description="Consensus status")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class MessageRouter:
    """Advanced message routing system"""
    
    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.routing_rules: List[RoutingRule] = []
        self.message_queue: asyncio.Queue = asyncio.Queue(maxsize=10000)
        self.dead_letter_queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self.routing_stats: Dict[str, Any] = {
            "messages_processed": 0,
            "messages_failed": 0,
            "messages_expired": 0,
            "routing_time_total": 0.0
        }
        self.active_routes: Dict[str, str] = {}  # message_id -> route
        self.load_balancer_index = 0
        
    def add_routing_rule(self, rule: RoutingRule):
        """Add a routing rule"""
        self.routing_rules.append(rule)
        # Sort by priority (higher priority first)
        self.routing_rules.sort(key=lambda r: r.priority, reverse=True)
        logger.info(f"Added routing rule: {rule.name}")
    
    def remove_routing_rule(self, rule_id: str):
        """Remove a routing rule"""
        self.routing_rules = [r for r in self.routing_rules if r.rule_id != rule_id]
        logger.info(f"Removed routing rule: {rule_id}")
    
    async def route_message(self, message: AgentMessage) -> Optional[str]:
        """Route message based on routing rules"""
        start_time = datetime.now(datetime.UTC)
        
        try:
            # Check if message is expired
            if self._is_message_expired(message):
                await self.dead_letter_queue.put(message)
                self.routing_stats["messages_expired"] += 1
                return None
            
            # Apply routing rules
            for rule in self.routing_rules:
                if rule.enabled and rule.matches(message):
                    route = await self._apply_routing_rule(rule, message)
                    if route:
                        self.active_routes[message.id] = route
                        self.routing_stats["messages_processed"] += 1
                        return route
            
            # Default routing
            default_route = await self._default_routing(message)
            if default_route:
                self.active_routes[message.id] = default_route
                self.routing_stats["messages_processed"] += 1
                return default_route
            
            # No route found
            await self.dead_letter_queue.put(message)
            self.routing_stats["messages_failed"] += 1
            return None
            
        except Exception as e:
            logger.error(f"Error routing message {message.id}: {e}")
            await self.dead_letter_queue.put(message)
            self.routing_stats["messages_failed"] += 1
            return None
        finally:
            routing_time = (datetime.now(datetime.UTC) - start_time).total_seconds()
            self.routing_stats["routing_time_total"] += routing_time
    
    async def _apply_routing_rule(self, rule: RoutingRule, message: AgentMessage) -> Optional[str]:
        """Apply a specific routing rule"""
        if rule.action == "forward":
            return rule.target
        elif rule.action == "transform":
            return await self._transform_message(message, rule)
        elif rule.action == "filter":
            return await self._filter_message(message, rule)
        elif rule.action == "route":
            return await self._custom_routing(message, rule)
        return None
    
    async def _transform_message(self, message: AgentMessage, rule: RoutingRule) -> Optional[str]:
        """Transform message based on rule"""
        # Apply transformation logic here
        transformed_message = AgentMessage(
            sender_id=message.sender_id,
            receiver_id=message.receiver_id,
            message_type=message.message_type,
            priority=message.priority,
            payload={**message.payload, **rule.condition.get("transform", {})}
        )
        # Route transformed message
        return await self._default_routing(transformed_message)
    
    async def _filter_message(self, message: AgentMessage, rule: RoutingRule) -> Optional[str]:
        """Filter message based on rule"""
        filter_condition = rule.condition.get("filter", {})
        for key, value in filter_condition.items():
            if message.payload.get(key) != value:
                return None  # Filter out message
        return await self._default_routing(message)
    
    async def _custom_routing(self, message: AgentMessage, rule: RoutingRule) -> Optional[str]:
        """Custom routing logic"""
        # Implement custom routing logic here
        return rule.target
    
    async def _default_routing(self, message: AgentMessage) -> Optional[str]:
        """Default message routing"""
        if message.receiver_id:
            return message.receiver_id
        elif message.message_type == MessageType.BROADCAST:
            return "broadcast"
        else:
            return None
    
    def _is_message_expired(self, message: AgentMessage) -> bool:
        """Check if message is expired"""
        age = (datetime.now(datetime.UTC) - message.timestamp).total_seconds()
        return age > message.ttl
    
    async def get_routing_stats(self) -> Dict[str, Any]:
        """Get routing statistics"""
        total_messages = self.routing_stats["messages_processed"]
        avg_routing_time = (
            self.routing_stats["routing_time_total"] / total_messages 
            if total_messages > 0 else 0
        )
        
        return {
            **self.routing_stats,
            "avg_routing_time": avg_routing_time,
            "active_routes": len(self.active_routes),
            "queue_size": self.message_queue.qsize(),
            "dead_letter_queue_size": self.dead_letter_queue.qsize()
        }

class LoadBalancer:
    """Load balancer for message distribution"""
    
    def __init__(self):
        self.agent_loads: Dict[str, float] = {}
        self.agent_weights: Dict[str, float] = {}
        self.last_updated = datetime.now(datetime.UTC)
        
    def update_agent_load(self, agent_id: str, load: float):
        """Update agent load information"""
        self.agent_loads[agent_id] = load
        self.last_updated = datetime.now(datetime.UTC)
    
    def set_agent_weight(self, agent_id: str, weight: float):
        """Set agent weight for load balancing"""
        self.agent_weights[agent_id] = weight
    
    def select_agent(self, available_agents: List[str], strategy: RoutingStrategy = RoutingStrategy.LOAD_BALANCED) -> Optional[str]:
        """Select agent based on load balancing strategy"""
        if not available_agents:
            return None
        
        if strategy == RoutingStrategy.ROUND_ROBIN:
            return self._round_robin_selection(available_agents)
        elif strategy == RoutingStrategy.LOAD_BALANCED:
            return self._load_balanced_selection(available_agents)
        elif strategy == RoutingStrategy.PRIORITY_BASED:
            return self._priority_based_selection(available_agents)
        elif strategy == RoutingStrategy.RANDOM:
            return self._random_selection(available_agents)
        else:
            return available_agents[0]
    
    def _round_robin_selection(self, agents: List[str]) -> str:
        """Round-robin agent selection"""
        agent = agents[self.load_balancer_index % len(agents)]
        self.load_balancer_index += 1
        return agent
    
    def _load_balanced_selection(self, agents: List[str]) -> str:
        """Load-balanced agent selection"""
        # Select agent with lowest load
        min_load = float('inf')
        selected_agent = None
        
        for agent in agents:
            load = self.agent_loads.get(agent, 0.0)
            weight = self.agent_weights.get(agent, 1.0)
            weighted_load = load / weight
            
            if weighted_load < min_load:
                min_load = weighted_load
                selected_agent = agent
        
        return selected_agent or agents[0]
    
    def _priority_based_selection(self, agents: List[str]) -> str:
        """Priority-based agent selection"""
        # Sort by weight (higher weight = higher priority)
        weighted_agents = sorted(
            agents,
            key=lambda a: self.agent_weights.get(a, 1.0),
            reverse=True
        )
        return weighted_agents[0]
    
    def _random_selection(self, agents: List[str]) -> str:
        """Random agent selection"""
        import random
        return random.choice(agents)

class MessageQueue:
    """Advanced message queue with priority and persistence"""
    
    def __init__(self, max_size: int = 10000):
        self.max_size = max_size
        self.queues: Dict[Priority, asyncio.Queue] = {
            Priority.CRITICAL: asyncio.Queue(maxsize=max_size // 4),
            Priority.HIGH: asyncio.Queue(maxsize=max_size // 4),
            Priority.NORMAL: asyncio.Queue(maxsize=max_size // 2),
            Priority.LOW: asyncio.Queue(maxsize=max_size // 4)
        }
        self.message_store: Dict[str, AgentMessage] = {}
        self.delivery_confirmations: Dict[str, bool] = {}
        
    async def enqueue(self, message: AgentMessage) -> bool:
        """Enqueue message with priority"""
        try:
            # Store message for persistence
            self.message_store[message.id] = message
            
            # Add to appropriate priority queue
            queue = self.queues[message.priority]
            await queue.put(message)
            
            logger.debug(f"Enqueued message {message.id} with priority {message.priority}")
            return True
            
        except asyncio.QueueFull:
            logger.error(f"Queue full, cannot enqueue message {message.id}")
            return False
    
    async def dequeue(self) -> Optional[AgentMessage]:
        """Dequeue message with priority order"""
        # Check queues in priority order
        for priority in [Priority.CRITICAL, Priority.HIGH, Priority.NORMAL, Priority.LOW]:
            queue = self.queues[priority]
            try:
                message = queue.get_nowait()
                logger.debug(f"Dequeued message {message.id} with priority {priority}")
                return message
            except asyncio.QueueEmpty:
                continue
        
        return None
    
    async def confirm_delivery(self, message_id: str):
        """Confirm message delivery"""
        self.delivery_confirmations[message_id] = True
        
        # Clean up if exactly once delivery
        if message_id in self.message_store:
            del self.message_store[message_id]
    
    def get_queue_stats(self) -> Dict[str, Any]:
        """Get queue statistics"""
        return {
            "queue_sizes": {
                priority.value: queue.qsize()
                for priority, queue in self.queues.items()
            },
            "stored_messages": len(self.message_store),
            "delivery_confirmations": len(self.delivery_confirmations),
            "max_size": self.max_size
        }

class MessageProcessor:
    """Message processor with async handling"""
    
    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.router = MessageRouter(agent_id)
        self.load_balancer = LoadBalancer()
        self.message_queue = MessageQueue()
        self.processors: Dict[str, Callable] = {}
        self.processing_stats: Dict[str, Any] = {
            "messages_processed": 0,
            "processing_time_total": 0.0,
            "errors": 0
        }
        
    def register_processor(self, message_type: MessageType, processor: Callable):
        """Register message processor"""
        self.processors[message_type.value] = processor
        logger.info(f"Registered processor for {message_type.value}")
    
    async def process_message(self, message: AgentMessage) -> bool:
        """Process a message"""
        start_time = datetime.now(datetime.UTC)
        
        try:
            # Route message
            route = await self.router.route_message(message)
            if not route:
                logger.warning(f"No route found for message {message.id}")
                return False
            
            # Process message
            processor = self.processors.get(message.message_type.value)
            if processor:
                await processor(message)
            else:
                logger.warning(f"No processor found for {message.message_type.value}")
                return False
            
            # Update stats
            self.processing_stats["messages_processed"] += 1
            processing_time = (datetime.now(datetime.UTC) - start_time).total_seconds()
            self.processing_stats["processing_time_total"] += processing_time
            
            return True
            
        except Exception as e:
            logger.error(f"Error processing message {message.id}: {e}")
            self.processing_stats["errors"] += 1
            return False
    
    async def start_processing(self):
        """Start message processing loop"""
        while True:
            try:
                # Dequeue message
                message = await self.message_queue.dequeue()
                if message:
                    await self.process_message(message)
                else:
                    await asyncio.sleep(0.01)  # Small delay if no messages
                    
            except Exception as e:
                logger.error(f"Error in processing loop: {e}")
                await asyncio.sleep(1)
    
    def get_processing_stats(self) -> Dict[str, Any]:
        """Get processing statistics"""
        total_processed = self.processing_stats["messages_processed"]
        avg_processing_time = (
            self.processing_stats["processing_time_total"] / total_processed
            if total_processed > 0 else 0
        )
        
        return {
            **self.processing_stats,
            "avg_processing_time": avg_processing_time,
            "queue_stats": self.message_queue.get_queue_stats(),
            "routing_stats": self.router.get_routing_stats()
        }

# Factory functions for creating message types
def create_task_message(sender_id: str, receiver_id: str, task_type: str, task_data: Dict[str, Any]) -> AgentMessage:
    """Create a task message"""
    task_msg = TaskMessage(
        task_id=str(uuid.uuid4()),
        task_type=task_type,
        task_data=task_data
    )
    
    return AgentMessage(
        sender_id=sender_id,
        receiver_id=receiver_id,
        message_type=MessageType.TASK_ASSIGNMENT,
        payload=task_msg.dict()
    )

def create_coordination_message(sender_id: str, coordination_type: str, participants: List[str], data: Dict[str, Any]) -> AgentMessage:
    """Create a coordination message"""
    coord_msg = CoordinationMessage(
        coordination_id=str(uuid.uuid4()),
        coordination_type=coordination_type,
        participants=participants,
        coordination_data=data
    )
    
    return AgentMessage(
        sender_id=sender_id,
        message_type=MessageType.COORDINATION,
        payload=coord_msg.dict()
    )

def create_status_message(agent_id: str, status_type: str, status_data: Dict[str, Any]) -> AgentMessage:
    """Create a status message"""
    status_msg = StatusMessage(
        agent_id=agent_id,
        status_type=status_type,
        status_data=status_data
    )
    
    return AgentMessage(
        sender_id=agent_id,
        message_type=MessageType.STATUS_UPDATE,
        payload=status_msg.dict()
    )

def create_discovery_message(agent_id: str, agent_type: str, capabilities: List[str], services: List[str]) -> AgentMessage:
    """Create a discovery message"""
    discovery_msg = DiscoveryMessage(
        agent_id=agent_id,
        agent_type=agent_type,
        capabilities=capabilities,
        services=services
    )
    
    return AgentMessage(
        sender_id=agent_id,
        message_type=MessageType.DISCOVERY,
        payload=discovery_msg.dict()
    )

def create_consensus_message(sender_id: str, proposal: Dict[str, Any], voting_options: List[Dict[str, Any]], deadline: datetime) -> AgentMessage:
    """Create a consensus message"""
    consensus_msg = ConsensusMessage(
        consensus_id=str(uuid.uuid4()),
        proposal=proposal,
        voting_options=voting_options,
        voting_deadline=deadline
    )
    
    return AgentMessage(
        sender_id=sender_id,
        message_type=MessageType.CONSENSUS,
        payload=consensus_msg.dict()
    )

# Example usage
async def example_usage():
    """Example of how to use the message routing system"""
    
    # Create message processor
    processor = MessageProcessor("agent-001")
    
    # Register processors
    async def process_task(message: AgentMessage):
        task_data = TaskMessage(**message.payload)
        logger.info(f"Processing task: {task_data.task_id}")
    
    processor.register_processor(MessageType.TASK_ASSIGNMENT, process_task)
    
    # Create and route message
    task_message = create_task_message(
        sender_id="agent-001",
        receiver_id="agent-002",
        task_type="data_processing",
        task_data={"input": "test_data"}
    )
    
    await processor.message_queue.enqueue(task_message)
    
    # Start processing (in real implementation, this would run in background)
    # await processor.start_processing()

if __name__ == "__main__":
    asyncio.run(example_usage())
