"""Unit tests for agent registry service"""

import pytest
import sys
import sys
from pathlib import Path


from app import app, Agent, AgentRegistration


@pytest.mark.unit
def test_app_initialization():
    """Test that the FastAPI app initializes correctly"""
    assert app is not None
    assert app.title == "AITBC Agent Registry API"
    assert app.version == "1.0.0"


@pytest.mark.unit
def test_agent_model():
    """Test Agent model"""
    agent = Agent(
        id="agent_123",
        name="Test Agent",
        type="trading",
        capabilities=["trading", "analysis"],
        chain_id="ait-devnet",
        endpoint="http://localhost:8000",
        metadata={"region": "us-east"}
    )
    assert agent.id == "agent_123"
    assert agent.name == "Test Agent"
    assert agent.type == "trading"
    assert agent.capabilities == ["trading", "analysis"]


@pytest.mark.unit
def test_agent_model_empty_capabilities():
    """Test Agent model with empty capabilities"""
    agent = Agent(
        id="agent_123",
        name="Test Agent",
        type="trading",
        capabilities=[],
        chain_id="ait-devnet",
        endpoint="http://localhost:8000"
    )
    assert agent.capabilities == []


@pytest.mark.unit
def test_agent_model_no_metadata():
    """Test Agent model with default metadata"""
    agent = Agent(
        id="agent_123",
        name="Test Agent",
        type="trading",
        capabilities=["trading"],
        chain_id="ait-devnet",
        endpoint="http://localhost:8000"
    )
    assert agent.metadata == {}


@pytest.mark.unit
def test_agent_registration_model():
    """Test AgentRegistration model"""
    registration = AgentRegistration(
        name="Test Agent",
        type="trading",
        capabilities=["trading", "analysis"],
        chain_id="ait-devnet",
        endpoint="http://localhost:8000",
        metadata={"region": "us-east"}
    )
    assert registration.name == "Test Agent"
    assert registration.type == "trading"
    assert registration.capabilities == ["trading", "analysis"]


@pytest.mark.unit
def test_agent_registration_model_empty_capabilities():
    """Test AgentRegistration with empty capabilities"""
    registration = AgentRegistration(
        name="Test Agent",
        type="trading",
        capabilities=[],
        chain_id="ait-devnet",
        endpoint="http://localhost:8000"
    )
    assert registration.capabilities == []


@pytest.mark.unit
def test_agent_registration_model_no_metadata():
    """Test AgentRegistration with default metadata"""
    registration = AgentRegistration(
        name="Test Agent",
        type="trading",
        capabilities=["trading"],
        chain_id="ait-devnet",
        endpoint="http://localhost:8000"
    )
    assert registration.metadata == {}
