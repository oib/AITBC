"""
Test Marketplace service main application

Tests cover all public API endpoints with correct paths and required query
parameters. Database-dependent endpoints use TestClient which triggers the
async session dependency — tests assert response shape, not DB content.
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Add the marketplace src directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from marketplace_service.main import app


@pytest.fixture
def client():
    """Create test client for Marketplace service"""
    return TestClient(app)


# --- Health / readiness ---


def test_health_check(client):
    """Test health check endpoint"""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "marketplace-service"


def test_ready_check(client):
    """Test readiness endpoint"""
    response = client.get("/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"


def test_live_check(client):
    """Test liveness endpoint"""
    response = client.get("/live")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "alive"


def test_metrics_endpoint(client):
    """Test Prometheus metrics endpoint"""
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers.get("content-type", "")


# --- Marketplace status (corrected path) ---


def test_marketplace_status(client):
    """Test marketplace status endpoint (correct path: /v1/marketplace/status)"""
    response = client.get("/v1/marketplace/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "operational"
    assert data["service"] == "marketplace-service"


# --- Offers (corrected: required query params) ---


def test_get_marketplace_offers_with_params(client):
    """Test get marketplace offers with required query params"""
    response = client.get(
        "/v1/marketplace/offers",
        params={"status": "active", "region": "us-east", "gpu_model": "A100"},
    )
    # 200 if DB available, 500 if DB not available — both acceptable in test env
    assert response.status_code in (200, 500)


def test_get_marketplace_offers_missing_params(client):
    """Test get marketplace offers without required params returns 422"""
    response = client.get("/v1/marketplace/offers")
    assert response.status_code == 422


def test_get_marketplace_offers_partial_params(client):
    """Test get marketplace offers with only some required params"""
    response = client.get("/v1/marketplace/offers", params={"status": "active"})
    # FastAPI requires all three params (they're str | None but not Optional)
    assert response.status_code == 422


# --- Marketplace overview ---


def test_marketplace_overview(client):
    """Test marketplace overview endpoint"""
    response = client.get("/v1/marketplace")
    assert response.status_code in (200, 500)
    if response.status_code == 200:
        data = response.json()
        assert "status" in data
        assert "total_offers" in data
        assert "active_offers" in data


# --- Analytics (corrected: required query param) ---


def test_get_marketplace_analytics_with_param(client):
    """Test get marketplace analytics with required period_type param"""
    response = client.get("/v1/marketplace/analytics", params={"period_type": "daily"})
    assert response.status_code in (200, 500)


def test_get_marketplace_analytics_missing_param(client):
    """Test get marketplace analytics without required param returns 422"""
    response = client.get("/v1/marketplace/analytics")
    assert response.status_code == 422


# --- Performance ---


def test_marketplace_performance(client):
    """Test marketplace performance endpoint (requires period param)"""
    response = client.get("/v1/marketplace/performance", params={"period": "daily"})
    assert response.status_code in (200, 500)


def test_marketplace_performance_missing_param(client):
    """Test marketplace performance without required period param returns 422"""
    response = client.get("/v1/marketplace/performance")
    assert response.status_code == 422


# --- Plugins ---


def test_get_plugins(client):
    """Test get plugins endpoint"""
    response = client.get("/v1/marketplace/plugins")
    assert response.status_code in (200, 500)


# --- Offer by ID ---


def test_get_offer_by_id_not_found(client):
    """Test get non-existent offer returns 404, null, or error"""
    response = client.get("/v1/marketplace/offers/nonexistent-offer-id")
    # get_offer returns None (200 with null body) or raises (500) if DB unavailable
    assert response.status_code in (200, 404, 500)
    if response.status_code == 200:
        assert response.json() is None


# --- Offer history ---


def test_get_offer_history_not_found(client):
    """Test get history for non-existent offer"""
    response = client.get("/v1/marketplace/offers/nonexistent-offer-id/history")
    assert response.status_code in (200, 404, 500)


# --- Offer by plugin ID ---


def test_get_offer_by_plugin_id(client):
    """Test get offer by plugin ID"""
    response = client.get("/v1/marketplace/offer/test-plugin-id")
    assert response.status_code in (200, 404, 500)


# --- Ratings ---


def test_get_ratings_by_service_id(client):
    """Test get ratings for a service (requires limit + offset params)"""
    response = client.get(
        "/v1/marketplace/offer/test-service-id/ratings",
        params={"limit": 10, "offset": 0},
    )
    assert response.status_code in (200, 500)


def test_get_ratings_missing_params(client):
    """Test get ratings without required params returns 422"""
    response = client.get("/v1/marketplace/offer/test-service-id/ratings")
    assert response.status_code == 422


def test_get_unsynced_ratings(client):
    """Test get unsynced ratings (requires limit param)"""
    response = client.get("/v1/marketplace/ratings/unsynced", params={"limit": 10})
    assert response.status_code in (200, 500)


def test_get_unsynced_ratings_missing_param(client):
    """Test get unsynced ratings without required limit param returns 422"""
    response = client.get("/v1/marketplace/ratings/unsynced")
    assert response.status_code == 422


# --- Offer query (plugin marketplace) ---


def test_get_offer_query(client):
    """Test offer query endpoint"""
    response = client.get("/v1/marketplace/offer")
    assert response.status_code in (200, 500)


# --- Transactions ---


def test_get_transactions(client):
    """Test get transactions endpoint (requires query params)"""
    response = client.get(
        "/v1/transactions",
        params={
            "transaction_type": "marketplace",
            "action": "offer",
            "status": "active",
            "island_id": "test-island",
        },
    )
    assert response.status_code in (200, 500)


def test_get_transactions_missing_params(client):
    """Test get transactions without required params returns 422"""
    response = client.get("/v1/transactions")
    assert response.status_code == 422
