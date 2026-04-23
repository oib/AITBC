"""Integration tests for plugin marketplace service"""

import pytest
import sys
import sys
from pathlib import Path
from fastapi.testclient import TestClient


from main import app, MarketplaceReview, PluginPurchase, DeveloperApplication, reviews, purchases, developer_applications


@pytest.fixture(autouse=True)
def reset_state():
    """Reset global state before each test"""
    reviews.clear()
    purchases.clear()
    developer_applications.clear()
    yield
    reviews.clear()
    purchases.clear()
    developer_applications.clear()


@pytest.mark.integration
def test_get_featured_plugins_api():
    """Test getting featured plugins API"""
    client = TestClient(app)
    response = client.get("/api/v1/marketplace/featured")
    assert response.status_code == 200
    data = response.json()
    assert "featured_plugins" in data


@pytest.mark.integration
def test_get_popular_plugins_api():
    """Test getting popular plugins API"""
    client = TestClient(app)
    response = client.get("/api/v1/marketplace/popular")
    assert response.status_code == 200
    data = response.json()
    assert "popular_plugins" in data


@pytest.mark.integration
def test_get_recent_plugins_api():
    """Test getting recent plugins API"""
    client = TestClient(app)
    response = client.get("/api/v1/marketplace/recent")
    assert response.status_code == 200
    data = response.json()
    assert "recent_plugins" in data


@pytest.mark.integration
def test_get_marketplace_stats_api():
    """Test getting marketplace stats API"""
    client = TestClient(app)
    response = client.get("/api/v1/marketplace/stats")
    assert response.status_code == 200
    data = response.json()
    assert "stats" in data


@pytest.mark.integration
def test_create_review():
    """Test creating a review"""
    client = TestClient(app)
    review = MarketplaceReview(
        plugin_id="plugin_123",
        user_id="user_123",
        rating=5,
        title="Great plugin",
        content="Excellent functionality"
    )
    response = client.post("/api/v1/reviews", json=review.model_dump())
    assert response.status_code == 200
    data = response.json()
    assert data["review_id"]
    assert data["status"] == "created"


@pytest.mark.integration
def test_get_plugin_reviews_api():
    """Test getting plugin reviews API"""
    client = TestClient(app)
    # Create a review first
    review = MarketplaceReview(
        plugin_id="plugin_123",
        user_id="user_123",
        rating=5,
        title="Great plugin",
        content="Excellent functionality"
    )
    client.post("/api/v1/reviews", json=review.model_dump())
    
    response = client.get("/api/v1/reviews/plugin_123")
    assert response.status_code == 200
    data = response.json()
    assert data["plugin_id"] == "plugin_123"
    assert "reviews" in data


@pytest.mark.integration
def test_get_plugin_reviews_no_reviews():
    """Test getting plugin reviews when no reviews exist"""
    client = TestClient(app)
    response = client.get("/api/v1/reviews/nonexistent")
    assert response.status_code == 200
    data = response.json()
    assert data["total_reviews"] == 0


@pytest.mark.integration
def test_create_purchase():
    """Test creating a purchase"""
    client = TestClient(app)
    purchase = PluginPurchase(
        plugin_id="plugin_123",
        user_id="user_123",
        price=99.99,
        payment_method="credit_card"
    )
    response = client.post("/api/v1/purchases", json=purchase.model_dump())
    assert response.status_code == 200
    data = response.json()
    assert data["purchase_id"]
    assert data["status"] == "completed"


@pytest.mark.integration
def test_apply_developer():
    """Test applying to become a developer"""
    client = TestClient(app)
    application = DeveloperApplication(
        developer_name="Dev Name",
        email="dev@example.com",
        experience="5 years",
        description="Experienced developer"
    )
    response = client.post("/api/v1/developers/apply", json=application.model_dump())
    assert response.status_code == 200
    data = response.json()
    assert data["application_id"]
    assert data["status"] == "pending"


@pytest.mark.integration
def test_get_verified_developers_api():
    """Test getting verified developers API"""
    client = TestClient(app)
    response = client.get("/api/v1/developers/verified")
    assert response.status_code == 200
    data = response.json()
    assert "verified_developers" in data


@pytest.mark.integration
def test_get_developer_revenue():
    """Test getting developer revenue"""
    client = TestClient(app)
    response = client.get("/api/v1/revenue/dev_123")
    assert response.status_code == 200
    data = response.json()
    assert "total_revenue" in data
