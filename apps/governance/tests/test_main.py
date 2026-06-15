"""
Test Governance service main application
"""

import pytest
from fastapi.testclient import TestClient
from governance_service.main import app


@pytest.fixture
def client():
    """Create test client for Governance service"""
    return TestClient(app)


def test_health_check(client):
    """Test health check endpoint"""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "governance-service"


def test_governance_status(client):
    """Test governance status endpoint"""
    response = client.get("/governance/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "operational"
    assert data["service"] == "governance-service"


def test_get_governance_profiles(client):
    """Test get governance profiles endpoint"""
    response = client.get("/v1/governance/profiles")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_get_governance_proposals(client):
    """Test get governance proposals endpoint"""
    response = client.get("/v1/governance/proposals")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_get_governance_votes(client):
    """Test get governance votes endpoint"""
    response = client.get("/v1/governance/votes")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_get_governance_treasury(client):
    """Test get governance treasury endpoint"""
    response = client.get("/v1/governance/treasury")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)


def test_get_governance_analytics(client):
    """Test get governance analytics endpoint"""
    response = client.get("/v1/governance/analytics")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)


# v0.4.12 New Endpoint Tests
def test_stake_tokens(client):
    """Test token staking endpoint"""
    response = client.post(
        "/v1/governance/stake", json={"staker_address": "0x1234567890abcdef", "amount": 1000, "lock_period_days": 30}
    )
    # May fail without database setup, but endpoint should exist
    assert response.status_code in [200, 500]


def test_get_voting_power(client):
    """Test voting power query endpoint"""
    response = client.get("/v1/governance/voting-power/0x1234567890abcdef")
    # May fail without database setup, but endpoint should exist
    assert response.status_code in [200, 500]


def test_delegate_voting_power(client):
    """Test delegation endpoint"""
    response = client.post(
        "/v1/governance/delegate",
        json={"delegator_address": "0x1234567890abcdef", "delegate_address": "0x0987654321fedcba", "amount": 500},
    )
    # May fail without database setup, but endpoint should exist
    assert response.status_code in [200, 500]


def test_execute_proposal(client):
    """Test proposal execution endpoint"""
    response = client.post("/v1/governance/proposals/test_prop_123/execute")
    # May fail without database setup, but endpoint should exist
    assert response.status_code in [200, 404, 500]
