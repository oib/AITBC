"""Edge case and error handling tests for global AI agents service"""

import pytest
import sys
import sys
from pathlib import Path
from fastapi.testclient import TestClient
from datetime import datetime, timedelta


from main import app, Agent, AgentMessage, CollaborationSession, AgentPerformance, global_agents, agent_messages, collaboration_sessions, agent_performance


@pytest.fixture(autouse=True)
def reset_state():
    """Reset global state before each test"""
    global_agents.clear()
    agent_messages.clear()
    collaboration_sessions.clear()
    agent_performance.clear()
    yield
    global_agents.clear()
    agent_messages.clear()
    collaboration_sessions.clear()
    agent_performance.clear()


@pytest.mark.unit
def test_agent_empty_name():
    """Test Agent with empty name"""
    agent = Agent(
        agent_id="agent_123",
        name="",
        type="ai",
        region="us-east-1",
        capabilities=["trading"],
        status="active",
        languages=["english"],
        specialization="trading",
        performance_score=4.5
    )
    assert agent.name == ""


@pytest.mark.unit
def test_agent_negative_performance_score():
    """Test Agent with negative performance score"""
    agent = Agent(
        agent_id="agent_123",
        name="Test Agent",
        type="ai",
        region="us-east-1",
        capabilities=["trading"],
        status="active",
        languages=["english"],
        specialization="trading",
        performance_score=-4.5
    )
    assert agent.performance_score == -4.5


@pytest.mark.unit
def test_agent_performance_out_of_range_score():
    """Test AgentPerformance with out of range scores"""
    performance = AgentPerformance(
        agent_id="agent_123",
        timestamp=datetime.utcnow(),
        tasks_completed=10,
        response_time_ms=50.5,
        accuracy_score=2.0,
        collaboration_score=2.0,
        resource_usage={}
    )
    assert performance.accuracy_score == 2.0
    assert performance.collaboration_score == 2.0


@pytest.mark.unit
def test_agent_message_empty_content():
    """Test AgentMessage with empty content"""
    message = AgentMessage(
        message_id="msg_123",
        sender_id="agent_123",
        recipient_id="agent_456",
        message_type="request",
        content={},
        priority="high",
        language="english",
        timestamp=datetime.utcnow()
    )
    assert message.content == {}


@pytest.mark.integration
def test_list_agents_with_no_agents():
    """Test listing agents when no agents exist"""
    client = TestClient(app)
    response = client.get("/api/v1/agents")
    assert response.status_code == 200
    data = response.json()
    assert data["total_agents"] == 0


@pytest.mark.integration
def test_get_agent_messages_agent_not_found():
    """Test getting messages for nonexistent agent"""
    client = TestClient(app)
    response = client.get("/api/v1/messages/nonexistent")
    assert response.status_code == 404


@pytest.mark.integration
def test_get_collaboration_not_found():
    """Test getting nonexistent collaboration session"""
    client = TestClient(app)
    response = client.get("/api/v1/collaborations/nonexistent")
    assert response.status_code == 404


@pytest.mark.integration
def test_send_collaboration_message_session_not_found():
    """Test sending message to nonexistent collaboration session"""
    client = TestClient(app)
    response = client.post("/api/v1/collaborations/nonexistent/message", params={"sender_id": "agent_123"}, json={"content": "test"})
    assert response.status_code == 404


@pytest.mark.integration
def test_send_collaboration_message_sender_not_participant():
    """Test sending message from non-participant"""
    client = TestClient(app)
    # Register agent and create collaboration
    agent = Agent(
        agent_id="agent_123",
        name="Agent 1",
        type="ai",
        region="us-east-1",
        capabilities=["trading"],
        status="active",
        languages=["english"],
        specialization="trading",
        performance_score=4.5
    )
    client.post("/api/v1/agents/register", json=agent.model_dump())
    
    session = CollaborationSession(
        session_id="session_123",
        participants=["agent_123"],
        session_type="research",
        objective="Research task",
        created_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(hours=1),
        status="active"
    )
    client.post("/api/v1/collaborations/create", json=session.model_dump(mode='json'))
    
    response = client.post("/api/v1/collaborations/session_123/message", params={"sender_id": "nonexistent"}, json={"content": "test"})
    assert response.status_code == 400


@pytest.mark.integration
def test_get_agent_performance_agent_not_found():
    """Test getting performance for nonexistent agent"""
    client = TestClient(app)
    response = client.get("/api/v1/performance/nonexistent")
    assert response.status_code == 404


@pytest.mark.integration
def test_dashboard_with_no_data():
    """Test dashboard with no data"""
    client = TestClient(app)
    response = client.get("/api/v1/network/dashboard")
    assert response.status_code == 200
    data = response.json()
    assert data["dashboard"]["network_overview"]["total_agents"] == 0


@pytest.mark.integration
def test_optimize_network_with_no_agents():
    """Test network optimization with no agents"""
    client = TestClient(app)
    response = client.get("/api/v1/network/optimize")
    assert response.status_code == 200
    data = response.json()
    assert "optimization_results" in data
