"""Tests for load balancer module"""

import sys
from pathlib import Path

# Add coordinator path for imports
coordinator_path = Path("/opt/aitbc/apps/agent-coordinator/src")
if str(coordinator_path) not in sys.path:
    sys.path.insert(0, str(coordinator_path))

import pytest
from datetime import UTC, datetime

from app.routing.load_balancer import (
    LoadBalancingStrategy,
    LoadMetrics,
    TaskAssignment,
    AgentWeight,
    LoadBalancer,
)
from app.routing.agent_discovery import AgentRegistry


class TestLoadMetrics:
    """Test LoadMetrics dataclass"""

    def test_load_metrics_creation(self):
        """Test creating LoadMetrics with default values"""
        metrics = LoadMetrics()
        assert metrics.cpu_usage == 0.0
        assert metrics.memory_usage == 0.0
        assert metrics.active_connections == 0
        assert metrics.pending_tasks == 0
        assert metrics.completed_tasks == 0
        assert metrics.failed_tasks == 0
        assert metrics.avg_response_time == 0.0
        assert isinstance(metrics.last_updated, datetime)

    def test_load_metrics_with_values(self):
        """Test creating LoadMetrics with custom values"""
        metrics = LoadMetrics(
            cpu_usage=50.0,
            memory_usage=60.0,
            active_connections=5,
            pending_tasks=10,
            completed_tasks=100,
            failed_tasks=5,
            avg_response_time=1.5,
        )
        assert metrics.cpu_usage == 50.0
        assert metrics.memory_usage == 60.0
        assert metrics.active_connections == 5
        assert metrics.pending_tasks == 10
        assert metrics.completed_tasks == 100
        assert metrics.failed_tasks == 5
        assert metrics.avg_response_time == 1.5

    def test_load_metrics_to_dict(self):
        """Test converting LoadMetrics to dictionary"""
        metrics = LoadMetrics(cpu_usage=50.0, memory_usage=60.0)
        result = metrics.to_dict()
        assert result["cpu_usage"] == 50.0
        assert result["memory_usage"] == 60.0
        assert "last_updated" in result
        assert isinstance(result["last_updated"], str)


class TestTaskAssignment:
    """Test TaskAssignment dataclass"""

    def test_task_assignment_creation(self):
        """Test creating TaskAssignment"""
        assignment = TaskAssignment(
            task_id="task-123",
            agent_id="agent-456",
            assigned_at=datetime.now(UTC),
        )
        assert assignment.task_id == "task-123"
        assert assignment.agent_id == "agent-456"
        assert assignment.status == "pending"
        assert assignment.success is False

    def test_task_assignment_completed(self):
        """Test marking task as completed"""
        assignment = TaskAssignment(
            task_id="task-123",
            agent_id="agent-456",
            assigned_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            status="completed",
            success=True,
            response_time=2.5,
        )
        assert assignment.status == "completed"
        assert assignment.success is True
        assert assignment.response_time == 2.5

    def test_task_assignment_to_dict(self):
        """Test converting TaskAssignment to dictionary"""
        assignment = TaskAssignment(
            task_id="task-123",
            agent_id="agent-456",
            assigned_at=datetime.now(UTC),
        )
        result = assignment.to_dict()
        assert result["task_id"] == "task-123"
        assert result["agent_id"] == "agent-456"
        assert result["status"] == "pending"
        assert isinstance(result["assigned_at"], str)


class TestAgentWeight:
    """Test AgentWeight dataclass"""

    def test_agent_weight_creation(self):
        """Test creating AgentWeight with default values"""
        weight = AgentWeight(agent_id="agent-123")
        assert weight.agent_id == "agent-123"
        assert weight.weight == 1.0
        assert weight.capacity == 100
        assert weight.performance_score == 1.0
        assert weight.reliability_score == 1.0
        assert isinstance(weight.last_updated, datetime)

    def test_agent_weight_custom_values(self):
        """Test creating AgentWeight with custom values"""
        weight = AgentWeight(
            agent_id="agent-123",
            weight=2.0,
            capacity=200,
            performance_score=0.9,
            reliability_score=0.95,
        )
        assert weight.weight == 2.0
        assert weight.capacity == 200
        assert weight.performance_score == 0.9
        assert weight.reliability_score == 0.95


class TestLoadBalancer:
    """Test LoadBalancer class"""

    def test_load_balancer_initialization(self, agent_registry):
        """Test LoadBalancer initialization"""
        balancer = LoadBalancer(agent_registry)
        assert balancer.strategy == LoadBalancingStrategy.LEAST_CONNECTIONS
        assert balancer.agent_weights == {}
        assert balancer.agent_metrics == {}
        assert balancer.task_assignments == {}
        assert balancer.total_assignments == 0
        assert balancer.successful_assignments == 0
        assert balancer.failed_assignments == 0

    def test_set_strategy(self, agent_registry):
        """Test setting load balancing strategy"""
        balancer = LoadBalancer(agent_registry)
        balancer.set_strategy(LoadBalancingStrategy.ROUND_ROBIN)
        assert balancer.strategy == LoadBalancingStrategy.ROUND_ROBIN

    def test_set_agent_weight(self, agent_registry):
        """Test setting agent weight"""
        balancer = LoadBalancer(agent_registry)
        balancer.set_agent_weight("agent-123", weight=2.0, capacity=200)
        assert "agent-123" in balancer.agent_weights
        assert balancer.agent_weights["agent-123"].weight == 2.0
        assert balancer.agent_weights["agent-123"].capacity == 200

    def test_update_agent_metrics(self, agent_registry):
        """Test updating agent metrics"""
        balancer = LoadBalancer(agent_registry)
        metrics = LoadMetrics(cpu_usage=50.0, memory_usage=60.0)
        balancer.update_agent_metrics("agent-123", metrics)
        assert "agent-123" in balancer.agent_metrics
        assert balancer.agent_metrics["agent-123"].cpu_usage == 50.0

    def test_get_agent_load(self, agent_registry):
        """Test getting agent load"""
        balancer = LoadBalancer(agent_registry)
        metrics = LoadMetrics(active_connections=5, pending_tasks=3)
        balancer.agent_metrics["agent-123"] = metrics
        load = balancer._get_agent_load("agent-123")
        assert load == 8  # 5 + 3

    def test_get_agent_load_no_metrics(self, agent_registry):
        """Test getting agent load when no metrics exist"""
        balancer = LoadBalancer(agent_registry)
        load = balancer._get_agent_load("agent-123")
        assert load == 0

    def test_round_robin_selection(self, agent_registry):
        """Test round-robin selection"""
        balancer = LoadBalancer(agent_registry)
        agents = ["agent-1", "agent-2", "agent-3"]
        selected = balancer._round_robin_selection(agents)
        assert selected == "agent-1"
        assert balancer.round_robin_index == 1
        selected = balancer._round_robin_selection(agents)
        assert selected == "agent-2"

    def test_least_connections_selection(self, agent_registry):
        """Test least connections selection"""
        balancer = LoadBalancer(agent_registry)
        balancer.agent_metrics["agent-1"] = LoadMetrics(pending_tasks=5)
        balancer.agent_metrics["agent-2"] = LoadMetrics(pending_tasks=2)
        balancer.agent_metrics["agent-3"] = LoadMetrics(pending_tasks=10)
        agents = ["agent-1", "agent-2", "agent-3"]
        selected = balancer._least_connections_selection(agents)
        assert selected == "agent-2"

    def test_least_response_time_selection(self, agent_registry):
        """Test least response time selection"""
        balancer = LoadBalancer(agent_registry)
        balancer.agent_metrics["agent-1"] = LoadMetrics(avg_response_time=2.0)
        balancer.agent_metrics["agent-2"] = LoadMetrics(avg_response_time=0.5)
        balancer.agent_metrics["agent-3"] = LoadMetrics(avg_response_time=1.5)
        agents = ["agent-1", "agent-2", "agent-3"]
        selected = balancer._least_response_time_selection(agents)
        assert selected == "agent-2"

    def test_get_load_balancing_stats(self, agent_registry):
        """Test getting load balancing statistics"""
        balancer = LoadBalancer(agent_registry)
        balancer.total_assignments = 100
        balancer.successful_assignments = 95
        balancer.agent_metrics["agent-1"] = LoadMetrics(pending_tasks=5)
        stats = balancer.get_load_balancing_stats()
        assert stats["total_assignments"] == 100
        assert stats["successful_assignments"] == 95
        assert stats["active_agents"] == 1
        assert stats["success_rate"] == 0.95

    def test_get_agent_stats(self, agent_registry):
        """Test getting agent statistics"""
        balancer = LoadBalancer(agent_registry)
        metrics = LoadMetrics(cpu_usage=50.0, pending_tasks=5)
        balancer.agent_metrics["agent-123"] = metrics
        balancer.set_agent_weight("agent-123", weight=2.0)
        stats = balancer.get_agent_stats("agent-123")
        assert stats is not None
        assert stats["agent_id"] == "agent-123"
        assert stats["metrics"]["cpu_usage"] == 50.0
        assert stats["weight"]["weight"] == 2.0

    def test_get_agent_stats_not_found(self, agent_registry):
        """Test getting stats for non-existent agent"""
        balancer = LoadBalancer(agent_registry)
        stats = balancer.get_agent_stats("non-existent")
        assert stats is None


@pytest.fixture
def agent_registry():
    """Fixture for AgentRegistry"""
    return AgentRegistry()
