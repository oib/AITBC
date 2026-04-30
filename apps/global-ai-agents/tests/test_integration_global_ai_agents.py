"""Integration tests for global AI agents service"""

import pytest
import sys
import sys
from pathlib import Path
from fastapi.testclient import TestClient
from datetime import datetime, UTC, timedelta


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


@pytest.mark.integration
def test_root_endpoint():
    """Test root endpoint"""
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "AITBC Global AI Agent Communication Service"
    assert data["status"] == "running"


@pytest.mark.integration
def test_health_check_endpoint():
    """Test health check endpoint"""
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "total_agents" in data


@pytest.mark.integration
def test_register_agent():
    """Test registering a new agent"""
    client = TestClient(app)
    agent = Agent(
        agent_id="agent_123",
        name="Test Agent",
        type="ai",
        region="us-east-1",
        capabilities=["trading"],
        status="active",
        languages=["english"],
        specialization="trading",
        performance_score=4.5
    )
    response = client.post("/api/v1/agents/register", json=agent.model_dump())
    assert response.status_code == 200
    data = response.json()
    assert data["agent_id"] == "agent_123"
    assert data["status"] == "registered"


@pytest.mark.integration
def test_register_duplicate_agent():
    """Test registering duplicate agent"""
    client = TestClient(app)
    agent = Agent(
        agent_id="agent_123",
        name="Test Agent",
        type="ai",
        region="us-east-1",
        capabilities=["trading"],
        status="active",
        languages=["english"],
        specialization="trading",
        performance_score=4.5
    )
    client.post("/api/v1/agents/register", json=agent.model_dump())
    
    response = client.post("/api/v1/agents/register", json=agent.model_dump())
    assert response.status_code == 400


@pytest.mark.integration
def test_list_agents():
    """Test listing all agents"""
    client = TestClient(app)
    response = client.get("/api/v1/agents")
    assert response.status_code == 200
    data = response.json()
    assert "agents" in data
    assert "total_agents" in data


@pytest.mark.integration
def test_list_agents_with_filters():
    """Test listing agents with filters"""
    client = TestClient(app)
    # Register an agent first
    agent = Agent(
        agent_id="agent_123",
        name="Test Agent",
        type="trading",
        region="us-east-1",
        capabilities=["trading"],
        status="active",
        languages=["english"],
        specialization="trading",
        performance_score=4.5
    )
    client.post("/api/v1/agents/register", json=agent.model_dump())
    
    response = client.get("/api/v1/agents?region=us-east-1&type=trading&status=active")
    assert response.status_code == 200
    data = response.json()
    assert "filters" in data


@pytest.mark.integration
def test_get_agent():
    """Test getting specific agent"""
    client = TestClient(app)
    agent = Agent(
        agent_id="agent_123",
        name="Test Agent",
        type="ai",
        region="us-east-1",
        capabilities=["trading"],
        status="active",
        languages=["english"],
        specialization="trading",
        performance_score=4.5
    )
    client.post("/api/v1/agents/register", json=agent.model_dump())
    
    response = client.get("/api/v1/agents/agent_123")
    assert response.status_code == 200
    data = response.json()
    assert data["agent_id"] == "agent_123"


@pytest.mark.integration
def test_get_agent_not_found():
    """Test getting nonexistent agent"""
    client = TestClient(app)
    response = client.get("/api/v1/agents/nonexistent")
    assert response.status_code == 404


@pytest.mark.integration
def test_send_direct_message():
    """Test sending direct message"""
    client = TestClient(app)
    # Register two agents
    agent1 = Agent(
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
    agent2 = Agent(
        agent_id="agent_456",
        name="Agent 2",
        type="ai",
        region="us-east-1",
        capabilities=["trading"],
        status="active",
        languages=["english"],
        specialization="trading",
        performance_score=4.5
    )
    client.post("/api/v1/agents/register", json=agent1.model_dump())
    client.post("/api/v1/agents/register", json=agent2.model_dump())
    
    message = AgentMessage(
        message_id="msg_123",
        sender_id="agent_123",
        recipient_id="agent_456",
        message_type="request",
        content={"data": "test"},
        priority="high",
        language="english",
        timestamp=datetime.now(datetime.UTC)
    )
    response = client.post("/api/v1/messages/send", json=message.model_dump(mode='json'))
    assert response.status_code == 200
    data = response.json()
    assert data["message_id"] == "msg_123"
    assert data["status"] == "delivered"


@pytest.mark.integration
def test_send_broadcast_message():
    """Test sending broadcast message"""
    client = TestClient(app)
    # Register two agents
    agent1 = Agent(
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
    agent2 = Agent(
        agent_id="agent_456",
        name="Agent 2",
        type="ai",
        region="us-east-1",
        capabilities=["trading"],
        status="active",
        languages=["english"],
        specialization="trading",
        performance_score=4.5
    )
    client.post("/api/v1/agents/register", json=agent1.model_dump())
    client.post("/api/v1/agents/register", json=agent2.model_dump())
    
    message = AgentMessage(
        message_id="msg_123",
        sender_id="agent_123",
        recipient_id=None,
        message_type="broadcast",
        content={"data": "test"},
        priority="medium",
        language="english",
        timestamp=datetime.now(datetime.UTC)
    )
    response = client.post("/api/v1/messages/send", json=message.model_dump(mode='json'))
    assert response.status_code == 200
    data = response.json()
    assert data["message_id"] == "msg_123"


@pytest.mark.integration
def test_send_message_sender_not_found():
    """Test sending message with nonexistent sender"""
    client = TestClient(app)
    message = AgentMessage(
        message_id="msg_123",
        sender_id="nonexistent",
        recipient_id="agent_456",
        message_type="request",
        content={"data": "test"},
        priority="high",
        language="english",
        timestamp=datetime.now(datetime.UTC)
    )
    response = client.post("/api/v1/messages/send", json=message.model_dump(mode='json'))
    assert response.status_code == 400


@pytest.mark.integration
def test_send_message_recipient_not_found():
    """Test sending message with nonexistent recipient"""
    client = TestClient(app)
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
    
    message = AgentMessage(
        message_id="msg_123",
        sender_id="agent_123",
        recipient_id="nonexistent",
        message_type="request",
        content={"data": "test"},
        priority="high",
        language="english",
        timestamp=datetime.now(datetime.UTC)
    )
    response = client.post("/api/v1/messages/send", json=message.model_dump(mode='json'))
    assert response.status_code == 400


@pytest.mark.integration
def test_get_agent_messages():
    """Test getting agent messages"""
    client = TestClient(app)
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
    
    response = client.get("/api/v1/messages/agent_123")
    assert response.status_code == 200
    data = response.json()
    assert data["agent_id"] == "agent_123"


@pytest.mark.integration
def test_get_agent_messages_with_limit():
    """Test getting agent messages with limit parameter"""
    client = TestClient(app)
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
    
    response = client.get("/api/v1/messages/agent_123?limit=10")
    assert response.status_code == 200


@pytest.mark.integration
def test_create_collaboration():
    """Test creating collaboration session"""
    client = TestClient(app)
    # Register two agents
    agent1 = Agent(
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
    agent2 = Agent(
        agent_id="agent_456",
        name="Agent 2",
        type="ai",
        region="us-east-1",
        capabilities=["trading"],
        status="active",
        languages=["english"],
        specialization="trading",
        performance_score=4.5
    )
    client.post("/api/v1/agents/register", json=agent1.model_dump())
    client.post("/api/v1/agents/register", json=agent2.model_dump())
    
    session = CollaborationSession(
        session_id="session_123",
        participants=["agent_123", "agent_456"],
        session_type="task_force",
        objective="Complete task",
        created_at=datetime.now(datetime.UTC),
        expires_at=datetime.now(datetime.UTC) + timedelta(hours=1),
        status="active"
    )
    response = client.post("/api/v1/collaborations/create", json=session.model_dump(mode='json'))
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == "session_123"


@pytest.mark.integration
def test_create_collaboration_participant_not_found():
    """Test creating collaboration with nonexistent participant"""
    client = TestClient(app)
    session = CollaborationSession(
        session_id="session_123",
        participants=["nonexistent"],
        session_type="task_force",
        objective="Complete task",
        created_at=datetime.now(datetime.UTC),
        expires_at=datetime.now(datetime.UTC) + timedelta(hours=1),
        status="active"
    )
    response = client.post("/api/v1/collaborations/create", json=session.model_dump(mode='json'))
    assert response.status_code == 400


@pytest.mark.integration
def test_get_collaboration():
    """Test getting collaboration session"""
    client = TestClient(app)
    # Register agents and create collaboration
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
        created_at=datetime.now(datetime.UTC),
        expires_at=datetime.now(datetime.UTC) + timedelta(hours=1),
        status="active"
    )
    client.post("/api/v1/collaborations/create", json=session.model_dump(mode='json'))
    
    response = client.get("/api/v1/collaborations/session_123")
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == "session_123"


@pytest.mark.integration
def test_send_collaboration_message():
    """Test sending message within collaboration session"""
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
        created_at=datetime.now(datetime.UTC),
        expires_at=datetime.now(datetime.UTC) + timedelta(hours=1),
        status="active"
    )
    client.post("/api/v1/collaborations/create", json=session.model_dump(mode='json'))
    
    response = client.post("/api/v1/collaborations/session_123/message", params={"sender_id": "agent_123"}, json={"content": "test message"})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "delivered"


@pytest.mark.integration
def test_record_agent_performance():
    """Test recording agent performance"""
    client = TestClient(app)
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
    
    performance = AgentPerformance(
        agent_id="agent_123",
        timestamp=datetime.now(datetime.UTC),
        tasks_completed=10,
        response_time_ms=50.5,
        accuracy_score=0.95,
        collaboration_score=0.9,
        resource_usage={"cpu": 50.0}
    )
    response = client.post("/api/v1/performance/record", json=performance.model_dump(mode='json'))
    assert response.status_code == 200
    data = response.json()
    assert data["performance_id"]
    assert data["status"] == "recorded"


@pytest.mark.integration
def test_record_performance_agent_not_found():
    """Test recording performance for nonexistent agent"""
    client = TestClient(app)
    performance = AgentPerformance(
        agent_id="nonexistent",
        timestamp=datetime.now(datetime.UTC),
        tasks_completed=10,
        response_time_ms=50.5,
        accuracy_score=0.95,
        collaboration_score=0.9,
        resource_usage={}
    )
    response = client.post("/api/v1/performance/record", json=performance.model_dump(mode='json'))
    assert response.status_code == 404


@pytest.mark.integration
def test_get_agent_performance():
    """Test getting agent performance"""
    client = TestClient(app)
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
    
    response = client.get("/api/v1/performance/agent_123")
    assert response.status_code == 200
    data = response.json()
    assert data["agent_id"] == "agent_123"


@pytest.mark.integration
def test_get_agent_performance_hours_parameter():
    """Test getting agent performance with custom hours parameter"""
    client = TestClient(app)
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
    
    response = client.get("/api/v1/performance/agent_123?hours=12")
    assert response.status_code == 200
    data = response.json()
    assert data["period_hours"] == 12


@pytest.mark.integration
def test_get_network_dashboard():
    """Test getting network dashboard"""
    client = TestClient(app)
    response = client.get("/api/v1/network/dashboard")
    assert response.status_code == 200
    data = response.json()
    assert "dashboard" in data


@pytest.mark.integration
def test_optimize_network():
    """Test network optimization"""
    client = TestClient(app)
    response = client.get("/api/v1/network/optimize")
    assert response.status_code == 200
    data = response.json()
    assert "optimization_results" in data
