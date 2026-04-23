"""Unit tests for global AI agents service"""

import pytest
import sys
import sys
from pathlib import Path
from datetime import datetime


from main import app, Agent, AgentMessage, CollaborationSession, AgentPerformance


@pytest.mark.unit
def test_app_initialization():
    """Test that the FastAPI app initializes correctly"""
    assert app is not None
    assert app.title == "AITBC Global AI Agent Communication Service"
    assert app.version == "1.0.0"


@pytest.mark.unit
def test_agent_model():
    """Test Agent model"""
    agent = Agent(
        agent_id="agent_123",
        name="Test Agent",
        type="ai",
        region="us-east-1",
        capabilities=["trading", "analysis"],
        status="active",
        languages=["english", "chinese"],
        specialization="trading",
        performance_score=4.5
    )
    assert agent.agent_id == "agent_123"
    assert agent.name == "Test Agent"
    assert agent.type == "ai"
    assert agent.status == "active"
    assert agent.performance_score == 4.5


@pytest.mark.unit
def test_agent_empty_capabilities():
    """Test Agent with empty capabilities"""
    agent = Agent(
        agent_id="agent_123",
        name="Test Agent",
        type="ai",
        region="us-east-1",
        capabilities=[],
        status="active",
        languages=["english"],
        specialization="general",
        performance_score=4.5
    )
    assert agent.capabilities == []


@pytest.mark.unit
def test_agent_message_model():
    """Test AgentMessage model"""
    message = AgentMessage(
        message_id="msg_123",
        sender_id="agent_123",
        recipient_id="agent_456",
        message_type="request",
        content={"data": "test"},
        priority="high",
        language="english",
        timestamp=datetime.utcnow()
    )
    assert message.message_id == "msg_123"
    assert message.sender_id == "agent_123"
    assert message.recipient_id == "agent_456"
    assert message.message_type == "request"
    assert message.priority == "high"


@pytest.mark.unit
def test_agent_message_broadcast():
    """Test AgentMessage with None recipient (broadcast)"""
    message = AgentMessage(
        message_id="msg_123",
        sender_id="agent_123",
        recipient_id=None,
        message_type="broadcast",
        content={"data": "test"},
        priority="medium",
        language="english",
        timestamp=datetime.utcnow()
    )
    assert message.recipient_id is None


@pytest.mark.unit
def test_collaboration_session_model():
    """Test CollaborationSession model"""
    session = CollaborationSession(
        session_id="session_123",
        participants=["agent_123", "agent_456"],
        session_type="task_force",
        objective="Complete trading task",
        created_at=datetime.utcnow(),
        expires_at=datetime.utcnow(),
        status="active"
    )
    assert session.session_id == "session_123"
    assert session.participants == ["agent_123", "agent_456"]
    assert session.session_type == "task_force"


@pytest.mark.unit
def test_collaboration_session_empty_participants():
    """Test CollaborationSession with empty participants"""
    session = CollaborationSession(
        session_id="session_123",
        participants=[],
        session_type="research",
        objective="Research task",
        created_at=datetime.utcnow(),
        expires_at=datetime.utcnow(),
        status="active"
    )
    assert session.participants == []


@pytest.mark.unit
def test_agent_performance_model():
    """Test AgentPerformance model"""
    performance = AgentPerformance(
        agent_id="agent_123",
        timestamp=datetime.utcnow(),
        tasks_completed=10,
        response_time_ms=50.5,
        accuracy_score=0.95,
        collaboration_score=0.9,
        resource_usage={"cpu": 50.0, "memory": 60.0}
    )
    assert performance.agent_id == "agent_123"
    assert performance.tasks_completed == 10
    assert performance.response_time_ms == 50.5
    assert performance.accuracy_score == 0.95


@pytest.mark.unit
def test_agent_performance_negative_values():
    """Test AgentPerformance with negative values"""
    performance = AgentPerformance(
        agent_id="agent_123",
        timestamp=datetime.utcnow(),
        tasks_completed=-10,
        response_time_ms=-50.5,
        accuracy_score=-0.95,
        collaboration_score=-0.9,
        resource_usage={}
    )
    assert performance.tasks_completed == -10
    assert performance.response_time_ms == -50.5
