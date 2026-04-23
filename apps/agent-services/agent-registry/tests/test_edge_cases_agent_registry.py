"""Edge case and error handling tests for agent registry service"""

import pytest
import sys
import sys
from pathlib import Path
import os



@pytest.fixture(autouse=True)
def reset_db():
    """Reset database before each test"""
    import app
    # Delete the database file if it exists
    db_path = Path("agent_registry.db")
    if db_path.exists():
        db_path.unlink()
    
    app.init_db()
    yield
    
    # Clean up after test
    if db_path.exists():
        db_path.unlink()


@pytest.mark.unit
def test_agent_empty_name():
    """Test Agent with empty name"""
    from app import Agent
    agent = Agent(
        id="agent_123",
        name="",
        type="trading",
        capabilities=["trading"],
        chain_id="ait-devnet",
        endpoint="http://localhost:8000"
    )
    assert agent.name == ""


@pytest.mark.unit
def test_agent_empty_chain_id():
    """Test Agent with empty chain_id"""
    from app import Agent
    agent = Agent(
        id="agent_123",
        name="Test Agent",
        type="trading",
        capabilities=["trading"],
        chain_id="",
        endpoint="http://localhost:8000"
    )
    assert agent.chain_id == ""


@pytest.mark.unit
def test_agent_empty_endpoint():
    """Test Agent with empty endpoint"""
    from app import Agent
    agent = Agent(
        id="agent_123",
        name="Test Agent",
        type="trading",
        capabilities=["trading"],
        chain_id="ait-devnet",
        endpoint=""
    )
    assert agent.endpoint == ""


@pytest.mark.unit
def test_agent_registration_empty_name():
    """Test AgentRegistration with empty name"""
    from app import AgentRegistration
    registration = AgentRegistration(
        name="",
        type="trading",
        capabilities=["trading"],
        chain_id="ait-devnet",
        endpoint="http://localhost:8000"
    )
    assert registration.name == ""


@pytest.mark.unit
def test_agent_registration_empty_chain_id():
    """Test AgentRegistration with empty chain_id"""
    from app import AgentRegistration
    registration = AgentRegistration(
        name="Test Agent",
        type="trading",
        capabilities=["trading"],
        chain_id="",
        endpoint="http://localhost:8000"
    )
    assert registration.chain_id == ""


@pytest.mark.integration
def test_list_agents_no_match_filter():
    """Test listing agents with filter that matches nothing"""
    import app
    from fastapi.testclient import TestClient
    client = TestClient(app.app)
    
    # Register an agent
    registration = app.AgentRegistration(
        name="Test Agent",
        type="trading",
        capabilities=["trading"],
        chain_id="ait-devnet",
        endpoint="http://localhost:8000"
    )
    client.post("/api/agents/register", json=registration.model_dump())
    
    # Filter for non-existent type
    response = client.get("/api/agents?agent_type=compliance")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 0


@pytest.mark.integration
def test_list_agents_multiple_filters():
    """Test listing agents with multiple filters"""
    import app
    from fastapi.testclient import TestClient
    client = TestClient(app.app)
    
    # Register agents
    registration1 = app.AgentRegistration(
        name="Trading Agent",
        type="trading",
        capabilities=["trading", "analysis"],
        chain_id="ait-devnet",
        endpoint="http://localhost:8000"
    )
    registration2 = app.AgentRegistration(
        name="Compliance Agent",
        type="compliance",
        capabilities=["compliance"],
        chain_id="ait-testnet",
        endpoint="http://localhost:8001"
    )
    client.post("/api/agents/register", json=registration1.model_dump())
    client.post("/api/agents/register", json=registration2.model_dump())
    
    # Filter by both type and chain
    response = client.get("/api/agents?agent_type=trading&chain_id=ait-devnet")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["type"] == "trading"
    assert data[0]["chain_id"] == "ait-devnet"
