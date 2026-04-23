"""Integration tests for agent registry service"""

import pytest
import sys
import sys
from pathlib import Path
from fastapi.testclient import TestClient
import os
import tempfile



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


@pytest.mark.integration
def test_health_check():
    """Test health check endpoint"""
    import app
    client = TestClient(app.app)
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


@pytest.mark.integration
def test_register_agent():
    """Test registering a new agent"""
    import app
    client = TestClient(app.app)
    registration = app.AgentRegistration(
        name="Test Agent",
        type="trading",
        capabilities=["trading", "analysis"],
        chain_id="ait-devnet",
        endpoint="http://localhost:8000",
        metadata={"region": "us-east"}
    )
    response = client.post("/api/agents/register", json=registration.model_dump())
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Test Agent"
    assert data["type"] == "trading"
    assert "id" in data


@pytest.mark.integration
def test_register_agent_no_metadata():
    """Test registering an agent without metadata"""
    import app
    client = TestClient(app.app)
    registration = app.AgentRegistration(
        name="Test Agent",
        type="trading",
        capabilities=["trading"],
        chain_id="ait-devnet",
        endpoint="http://localhost:8000"
    )
    response = client.post("/api/agents/register", json=registration.model_dump())
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Test Agent"


@pytest.mark.integration
def test_list_agents():
    """Test listing all agents"""
    import app
    client = TestClient(app.app)
    
    # Register an agent first
    registration = app.AgentRegistration(
        name="Test Agent",
        type="trading",
        capabilities=["trading"],
        chain_id="ait-devnet",
        endpoint="http://localhost:8000"
    )
    client.post("/api/agents/register", json=registration.model_dump())
    
    response = client.get("/api/agents")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1


@pytest.mark.integration
def test_list_agents_with_type_filter():
    """Test listing agents filtered by type"""
    import app
    client = TestClient(app.app)
    
    # Register agents
    registration1 = app.AgentRegistration(
        name="Trading Agent",
        type="trading",
        capabilities=["trading"],
        chain_id="ait-devnet",
        endpoint="http://localhost:8000"
    )
    registration2 = app.AgentRegistration(
        name="Compliance Agent",
        type="compliance",
        capabilities=["compliance"],
        chain_id="ait-devnet",
        endpoint="http://localhost:8001"
    )
    client.post("/api/agents/register", json=registration1.model_dump())
    client.post("/api/agents/register", json=registration2.model_dump())
    
    response = client.get("/api/agents?agent_type=trading")
    assert response.status_code == 200
    data = response.json()
    assert all(agent["type"] == "trading" for agent in data)


@pytest.mark.integration
def test_list_agents_with_chain_filter():
    """Test listing agents filtered by chain"""
    import app
    client = TestClient(app.app)
    
    # Register agents
    registration1 = app.AgentRegistration(
        name="Devnet Agent",
        type="trading",
        capabilities=["trading"],
        chain_id="ait-devnet",
        endpoint="http://localhost:8000"
    )
    registration2 = app.AgentRegistration(
        name="Testnet Agent",
        type="trading",
        capabilities=["trading"],
        chain_id="ait-testnet",
        endpoint="http://localhost:8001"
    )
    client.post("/api/agents/register", json=registration1.model_dump())
    client.post("/api/agents/register", json=registration2.model_dump())
    
    response = client.get("/api/agents?chain_id=ait-devnet")
    assert response.status_code == 200
    data = response.json()
    assert all(agent["chain_id"] == "ait-devnet" for agent in data)


@pytest.mark.integration
def test_list_agents_with_capability_filter():
    """Test listing agents filtered by capability"""
    import app
    client = TestClient(app.app)
    
    # Register agents
    registration = app.AgentRegistration(
        name="Trading Agent",
        type="trading",
        capabilities=["trading", "analysis"],
        chain_id="ait-devnet",
        endpoint="http://localhost:8000"
    )
    client.post("/api/agents/register", json=registration.model_dump())
    
    response = client.get("/api/agents?capability=trading")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1


@pytest.mark.integration
def test_list_agents_empty():
    """Test listing agents when none exist"""
    import app
    client = TestClient(app.app)
    
    response = client.get("/api/agents")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 0
