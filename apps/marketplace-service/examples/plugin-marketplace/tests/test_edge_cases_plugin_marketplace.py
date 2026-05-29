"""Edge case and error handling tests for plugin marketplace service"""

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


@pytest.mark.unit
def test_marketplace_review_out_of_range_rating():
    """Test MarketplaceReview with out of range rating"""
    review = MarketplaceReview(
        plugin_id="plugin_123",
        user_id="user_123",
        rating=10,
        title="Great plugin",
        content="Excellent"
    )
    assert review.rating == 10


@pytest.mark.unit
def test_marketplace_review_zero_rating():
    """Test MarketplaceReview with zero rating"""
    review = MarketplaceReview(
        plugin_id="plugin_123",
        user_id="user_123",
        rating=0,
        title="Bad plugin",
        content="Poor"
    )
    assert review.rating == 0


@pytest.mark.unit
def test_marketplace_review_negative_rating():
    """Test MarketplaceReview with negative rating"""
    review = MarketplaceReview(
        plugin_id="plugin_123",
        user_id="user_123",
        rating=-5,
        title="Terrible",
        content="Worst"
    )
    assert review.rating == -5


@pytest.mark.unit
def test_marketplace_review_empty_fields():
    """Test MarketplaceReview with empty fields"""
    review = MarketplaceReview(
        plugin_id="",
        user_id="",
        rating=3,
        title="",
        content=""
    )
    assert review.plugin_id == ""
    assert review.title == ""


@pytest.mark.unit
def test_plugin_purchase_zero_price():
    """Test PluginPurchase with zero price"""
    purchase = PluginPurchase(
        plugin_id="plugin_123",
        user_id="user_123",
        price=0.0,
        payment_method="free"
    )
    assert purchase.price == 0.0


@pytest.mark.unit
def test_developer_application_empty_fields():
    """Test DeveloperApplication with empty fields"""
    application = DeveloperApplication(
        developer_name="",
        email="",
        experience="",
        description=""
    )
    assert application.developer_name == ""
    assert application.email == ""


@pytest.mark.integration
def test_get_popular_plugins_with_limit():
    """Test getting popular plugins with limit parameter"""
    client = TestClient(app)
    response = client.get("/api/v1/marketplace/popular?limit=5")
    assert response.status_code == 200
    data = response.json()
    assert "popular_plugins" in data


@pytest.mark.integration
def test_get_recent_plugins_with_limit():
    """Test getting recent plugins with limit parameter"""
    client = TestClient(app)
    response = client.get("/api/v1/marketplace/recent?limit=5")
    assert response.status_code == 200
    data = response.json()
    assert "recent_plugins" in data


@pytest.mark.integration
def test_create_multiple_reviews():
    """Test creating multiple reviews for same plugin"""
    client = TestClient(app)
    
    for i in range(3):
        review = MarketplaceReview(
            plugin_id="plugin_123",
            user_id=f"user_{i}",
            rating=5,
            title="Great",
            content="Excellent"
        )
        client.post("/api/v1/reviews", json=review.model_dump())
    
    response = client.get("/api/v1/reviews/plugin_123")
    assert response.status_code == 200
    data = response.json()
    assert data["total_reviews"] == 3


@pytest.mark.integration
def test_create_multiple_purchases():
    """Test creating multiple purchases for same plugin"""
    client = TestClient(app)
    
    for i in range(3):
        purchase = PluginPurchase(
            plugin_id="plugin_123",
            user_id=f"user_{i}",
            price=99.99,
            payment_method="credit_card"
        )
        client.post("/api/v1/purchases", json=purchase.model_dump())
    
    response = client.get("/api/v1/revenue/revenue_sharing")
    assert response.status_code == 200


@pytest.mark.integration
def test_developer_application_with_company():
    """Test developer application with company"""
    client = TestClient(app)
    application = DeveloperApplication(
        developer_name="Dev Name",
        email="dev@example.com",
        company="Dev Corp",
        experience="5 years",
        description="Experienced"
    )
    response = client.post("/api/v1/developers/apply", json=application.model_dump())
    assert response.status_code == 200
    data = response.json()
    assert data["application_id"]
