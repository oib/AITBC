"""
Message Protocols Tests
Tests for message types, routing, filtering, and message handling
"""

import sys
from pathlib import Path

# Add coordinator path for imports
coordinator_path = Path("/opt/aitbc/apps/agent-coordinator/src")
if str(coordinator_path) not in sys.path:
    sys.path.insert(0, str(coordinator_path))

from datetime import UTC, datetime, timedelta  # noqa: E402

import pytest  # noqa: E402
from app.protocols.communication import AgentMessage, MessageType, Priority  # noqa: E402
from app.protocols.message_types import (  # noqa: E402
    ConsensusMessage,
    CoordinationMessage,
    DiscoveryMessage,
    LoadBalancer,
    MessageQueue,
    MessageRouter,
    RoutingRule,
    StatusMessage,
    TaskMessage,
    create_consensus_message,
    create_coordination_message,
    create_discovery_message,
    create_status_message,
    create_task_message,
)


class TestMessageTypes:
    """Test message type creation and validation"""

    def test_task_message_creation(self):
        """Test creating a task message"""
        task_msg = TaskMessage(
            task_id="task_001", task_type="data_processing", task_data={"input": "test_data"}, priority=Priority.HIGH
        )

        assert task_msg.task_id == "task_001"
        assert task_msg.task_type == "data_processing"
        assert task_msg.priority == Priority.HIGH
        assert task_msg.status == "pending"

    def test_task_message_deadline_validation(self):
        """Test task message deadline validation"""
        past_deadline = datetime.now(UTC) - timedelta(hours=1)

        with pytest.raises(ValueError):
            TaskMessage(task_id="task_002", task_type="test", deadline=past_deadline)

    def test_coordination_message_creation(self):
        """Test creating a coordination message"""
        coord_msg = CoordinationMessage(
            coordination_id="coord_001",
            coordination_type="consensus",
            participants=["agent_001", "agent_002"],
            coordination_data={"proposal": "test"},
        )

        assert coord_msg.coordination_id == "coord_001"
        assert coord_msg.coordination_type == "consensus"
        assert len(coord_msg.participants) == 2
        assert coord_msg.consensus_threshold == 0.5

    def test_status_message_creation(self):
        """Test creating a status message"""
        status_msg = StatusMessage(
            agent_id="agent_001",
            status_type="health",
            status_data={"cpu": 80, "memory": 60},
            health_score=0.95,
            capabilities=["compute", "storage"],
        )

        assert status_msg.agent_id == "agent_001"
        assert status_msg.status_type == "health"
        assert status_msg.health_score == 0.95
        assert len(status_msg.capabilities) == 2

    def test_discovery_message_creation(self):
        """Test creating a discovery message"""
        discovery_msg = DiscoveryMessage(
            agent_id="agent_001",
            agent_type="compute",
            capabilities=["gpu", "cpu"],
            services=["inference", "training"],
            endpoints={"http": "http://localhost:8080"},
        )

        assert discovery_msg.agent_id == "agent_001"
        assert discovery_msg.agent_type == "compute"
        assert len(discovery_msg.capabilities) == 2
        assert len(discovery_msg.services) == 2

    def test_consensus_message_creation(self):
        """Test creating a consensus message"""
        voting_deadline = datetime.now(UTC) + timedelta(hours=1)
        consensus_msg = ConsensusMessage(
            consensus_id="consensus_001",
            proposal={"action": "deploy"},
            voting_options=[{"id": "yes"}, {"id": "no"}],
            voting_deadline=voting_deadline,
        )

        assert consensus_msg.consensus_id == "consensus_001"
        assert consensus_msg.consensus_algorithm == "majority"
        assert len(consensus_msg.voting_options) == 2


class TestRoutingRules:
    """Test routing rule creation and matching"""

    def test_routing_rule_creation(self):
        """Test creating a routing rule"""
        rule = RoutingRule(
            name="high_priority_filter", condition={"priority": "high"}, action="forward", target="special_queue"
        )

        assert rule.name == "high_priority_filter"
        assert rule.action == "forward"
        assert rule.target == "special_queue"
        assert rule.enabled is True

    def test_routing_rule_matching(self):
        """Test routing rule message matching"""
        rule = RoutingRule(condition={"message_type": MessageType.TASK_ASSIGNMENT}, action="forward")

        message = AgentMessage(
            sender_id="agent_001", receiver_id="agent_002", message_type=MessageType.TASK_ASSIGNMENT, priority=Priority.NORMAL
        )

        assert rule.matches(message) is True

    def test_routing_rule_non_matching(self):
        """Test routing rule non-matching"""
        rule = RoutingRule(condition={"message_type": MessageType.BROADCAST}, action="forward")

        message = AgentMessage(
            sender_id="agent_001", receiver_id="agent_002", message_type=MessageType.TASK_ASSIGNMENT, priority=Priority.NORMAL
        )

        assert rule.matches(message) is False


class TestMessageRouter:
    """Test message routing functionality"""

    @pytest.mark.asyncio
    async def test_router_initialization(self):
        """Test router initialization"""
        router = MessageRouter(agent_id="agent_001")

        assert router.agent_id == "agent_001"
        assert len(router.routing_rules) == 0
        assert router.routing_stats["messages_processed"] == 0

    @pytest.mark.asyncio
    async def test_add_routing_rule(self):
        """Test adding routing rules"""
        router = MessageRouter(agent_id="agent_001")

        rule = RoutingRule(
            name="test_rule",
            condition={"message_type": MessageType.TASK_ASSIGNMENT},
            action="forward",
            target="queue_1",
            priority=10,
        )

        router.add_routing_rule(rule)
        assert len(router.routing_rules) == 1
        assert router.routing_rules[0].name == "test_rule"

    @pytest.mark.asyncio
    async def test_remove_routing_rule(self):
        """Test removing routing rules"""
        router = MessageRouter(agent_id="agent_001")

        rule = RoutingRule(name="test_rule", condition={"message_type": MessageType.TASK_ASSIGNMENT}, action="forward")

        router.add_routing_rule(rule)
        router.remove_routing_rule(rule.rule_id)
        assert len(router.routing_rules) == 0

    @pytest.mark.asyncio
    async def test_message_routing(self):
        """Test message routing"""
        router = MessageRouter(agent_id="agent_001")

        rule = RoutingRule(condition={"message_type": MessageType.TASK_ASSIGNMENT}, action="forward", target="agent_002")
        router.add_routing_rule(rule)

        message = AgentMessage(
            sender_id="agent_001", receiver_id="agent_002", message_type=MessageType.TASK_ASSIGNMENT, priority=Priority.NORMAL
        )

        route = await router.route_message(message)
        assert route == "agent_002"

    @pytest.mark.asyncio
    async def test_routing_stats(self):
        """Test routing statistics"""
        router = MessageRouter(agent_id="agent_001")

        rule = RoutingRule(condition={"message_type": MessageType.TASK_ASSIGNMENT}, action="forward", target="agent_002")
        router.add_routing_rule(rule)

        message = AgentMessage(
            sender_id="agent_001", receiver_id="agent_002", message_type=MessageType.TASK_ASSIGNMENT, priority=Priority.NORMAL
        )

        await router.route_message(message)
        stats = await router.get_routing_stats()

        assert stats["messages_processed"] == 1
        assert stats["messages_failed"] == 0


class TestLoadBalancer:
    """Test load balancing functionality"""

    def test_load_balancer_initialization(self):
        """Test load balancer initialization"""
        balancer = LoadBalancer()

        assert len(balancer.agent_loads) == 0
        assert len(balancer.agent_weights) == 0

    def test_update_agent_load(self):
        """Test updating agent load"""
        balancer = LoadBalancer()

        balancer.update_agent_load("agent_001", 0.5)
        assert balancer.agent_loads["agent_001"] == 0.5

    def test_set_agent_weight(self):
        """Test setting agent weight"""
        balancer = LoadBalancer()

        balancer.set_agent_weight("agent_001", 2.0)
        assert balancer.agent_weights["agent_001"] == 2.0

    def test_load_balanced_selection(self):
        """Test load-balanced agent selection"""
        balancer = LoadBalancer()
        balancer.update_agent_load("agent_001", 0.8)
        balancer.update_agent_load("agent_002", 0.3)

        agents = ["agent_001", "agent_002"]
        selected = balancer._load_balanced_selection(agents)

        # Should select agent with lower load
        assert selected == "agent_002"

    def test_priority_based_selection(self):
        """Test priority-based agent selection"""
        balancer = LoadBalancer()
        balancer.set_agent_weight("agent_001", 2.0)
        balancer.set_agent_weight("agent_002", 1.0)

        agents = ["agent_001", "agent_002"]
        selected = balancer._priority_based_selection(agents)

        # Should select agent with higher weight
        assert selected == "agent_001"

    def test_random_selection(self):
        """Test random agent selection"""
        balancer = LoadBalancer()
        agents = ["agent_001", "agent_002", "agent_003"]

        selected = balancer._random_selection(agents)
        assert selected in agents


class TestMessageQueue:
    """Test message queue functionality"""

    @pytest.mark.asyncio
    async def test_queue_initialization(self):
        """Test queue initialization"""
        queue = MessageQueue(max_size=1000)

        assert queue.max_size == 1000
        assert len(queue.queues) == 4  # CRITICAL, HIGH, NORMAL, LOW

    @pytest.mark.asyncio
    async def test_enqueue_message(self):
        """Test enqueuing message"""
        queue = MessageQueue()

        message = AgentMessage(
            sender_id="agent_001", receiver_id="agent_002", message_type=MessageType.TASK_ASSIGNMENT, priority=Priority.HIGH
        )

        success = await queue.enqueue(message)
        assert success is True
        assert message.id in queue.message_store

    @pytest.mark.asyncio
    async def test_dequeue_message(self):
        """Test dequeuing message"""
        queue = MessageQueue()

        message = AgentMessage(
            sender_id="agent_001",
            receiver_id="agent_002",
            message_type=MessageType.TASK_ASSIGNMENT,
            priority=Priority.CRITICAL,
        )

        await queue.enqueue(message)
        dequeued = await queue.dequeue()

        assert dequeued is not None
        assert dequeued.id == message.id

    @pytest.mark.asyncio
    async def test_priority_order(self):
        """Test messages are dequeued in priority order"""
        queue = MessageQueue()

        # Add messages with different priorities
        low_msg = AgentMessage(
            sender_id="agent_001", receiver_id="agent_002", message_type=MessageType.TASK_ASSIGNMENT, priority=Priority.LOW
        )

        high_msg = AgentMessage(
            sender_id="agent_001", receiver_id="agent_002", message_type=MessageType.TASK_ASSIGNMENT, priority=Priority.HIGH
        )

        critical_msg = AgentMessage(
            sender_id="agent_001",
            receiver_id="agent_002",
            message_type=MessageType.TASK_ASSIGNMENT,
            priority=Priority.CRITICAL,
        )

        await queue.enqueue(low_msg)
        await queue.enqueue(high_msg)
        await queue.enqueue(critical_msg)

        # Critical should be dequeued first
        first = await queue.dequeue()
        assert first.priority == Priority.CRITICAL

    @pytest.mark.asyncio
    async def test_delivery_confirmation(self):
        """Test delivery confirmation"""
        queue = MessageQueue()

        message = AgentMessage(
            sender_id="agent_001", receiver_id="agent_002", message_type=MessageType.TASK_ASSIGNMENT, priority=Priority.NORMAL
        )

        await queue.enqueue(message)
        await queue.confirm_delivery(message.id)

        assert message.id in queue.delivery_confirmations
        assert message.id not in queue.message_store

    @pytest.mark.asyncio
    async def test_queue_stats(self):
        """Test queue statistics"""
        queue = MessageQueue()

        message = AgentMessage(
            sender_id="agent_001", receiver_id="agent_002", message_type=MessageType.TASK_ASSIGNMENT, priority=Priority.NORMAL
        )

        await queue.enqueue(message)
        stats = queue.get_queue_stats()

        assert stats["stored_messages"] == 1
        assert stats["max_size"] == 10000


class TestMessageFactoryFunctions:
    """Test message factory functions"""

    def test_create_task_message(self):
        """Test task message factory function"""
        message = create_task_message(
            sender_id="agent_001", receiver_id="agent_002", task_type="inference", task_data={"model": "gpt-4"}
        )

        assert message.sender_id == "agent_001"
        assert message.receiver_id == "agent_002"
        assert message.message_type == MessageType.TASK_ASSIGNMENT
        assert "task_id" in message.payload

    def test_create_coordination_message(self):
        """Test coordination message factory function"""
        message = create_coordination_message(
            sender_id="agent_001",
            coordination_type="consensus",
            participants=["agent_001", "agent_002"],
            data={"proposal": "test"},
        )

        assert message.sender_id == "agent_001"
        assert message.message_type == MessageType.COORDINATION
        assert "coordination_id" in message.payload

    def test_create_status_message(self):
        """Test status message factory function"""
        message = create_status_message(agent_id="agent_001", status_type="health", status_data={"cpu": 80})

        assert message.sender_id == "agent_001"
        assert message.message_type == MessageType.STATUS_UPDATE
        assert "status_type" in message.payload

    def test_create_discovery_message(self):
        """Test discovery message factory function"""
        message = create_discovery_message(
            agent_id="agent_001", agent_type="compute", capabilities=["gpu"], services=["inference"]
        )

        assert message.sender_id == "agent_001"
        assert message.message_type == MessageType.DISCOVERY
        assert "agent_type" in message.payload

    def test_create_consensus_message(self):
        """Test consensus message factory function"""
        deadline = datetime.now(UTC) + timedelta(hours=1)
        message = create_consensus_message(
            sender_id="agent_001", proposal={"action": "deploy"}, voting_options=[{"id": "yes"}], deadline=deadline
        )

        assert message.sender_id == "agent_001"
        assert message.message_type == MessageType.CONSENSUS
        assert "consensus_id" in message.payload


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
