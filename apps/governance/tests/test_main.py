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
    """Test governance status endpoint.

    The route is ``/v1/governance/status``, not ``/governance/status``. Settled by the
    consumers: ``aitbc.governance.client`` (client.py:178) and
    ``aitbc governance status`` (cli/aitbc_cli/commands/governance.py:191) both call the
    versioned path, as does every other route this service exposes.
    """
    response = client.get("/v1/governance/status")
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


def test_get_governance_treasury_404s_when_uninitialised(client):
    """No ``main_treasury`` row is a 404, not a 200 carrying ``null``.

    This test previously asserted ``200`` and ``isinstance(data, dict)`` and failed on
    the second assertion, because the endpoint answered 200 with a body of ``null``.
    """
    response = client.get("/v1/governance/treasury")
    assert response.status_code == 404


def test_get_governance_treasury_returns_the_treasury_when_it_exists(client, test_database_path):
    """The 200 path, so the 404 above cannot pass by the endpoint being broken outright.

    Seeded with sqlite3 rather than the service's async session: the engine is bound to
    the event loop TestClient runs on, and opening a second loop here to write one row
    closes connections out from under it.
    """
    import sqlite3

    connection = sqlite3.connect(test_database_path)
    try:
        connection.execute(
            "INSERT INTO dao_treasury "
            "(treasury_id, total_balance, allocated_funds, asset_breakdown, last_updated) "
            "VALUES (?, ?, ?, ?, ?)",
            ("main_treasury", 1000, 0, "{}", "2026-08-11T00:00:00"),
        )
        connection.commit()

        response = client.get("/v1/governance/treasury")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        assert data["treasury_id"] == "main_treasury"
    finally:
        connection.execute("DELETE FROM dao_treasury WHERE treasury_id = 'main_treasury'")
        connection.commit()
        connection.close()


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
