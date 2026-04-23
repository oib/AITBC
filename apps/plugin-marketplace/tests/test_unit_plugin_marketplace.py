"""Unit tests for plugin marketplace service"""

import pytest
import sys
import sys
from pathlib import Path


from main import app, MarketplaceReview, PluginPurchase, DeveloperApplication


@pytest.mark.unit
def test_app_initialization():
    """Test that the FastAPI app initializes correctly"""
    assert app is not None
    assert app.title == "AITBC Plugin Marketplace"
    assert app.version == "1.0.0"


@pytest.mark.unit
def test_marketplace_review_model():
    """Test MarketplaceReview model"""
    review = MarketplaceReview(
        plugin_id="plugin_123",
        user_id="user_123",
        rating=5,
        title="Great plugin",
        content="Excellent functionality",
        pros=["Easy to use", "Fast"],
        cons=["Learning curve"]
    )
    assert review.plugin_id == "plugin_123"
    assert review.rating == 5
    assert review.title == "Great plugin"
    assert review.pros == ["Easy to use", "Fast"]
    assert review.cons == ["Learning curve"]


@pytest.mark.unit
def test_marketplace_review_defaults():
    """Test MarketplaceReview with default values"""
    review = MarketplaceReview(
        plugin_id="plugin_123",
        user_id="user_123",
        rating=4,
        title="Good plugin",
        content="Nice functionality"
    )
    assert review.pros == []
    assert review.cons == []


@pytest.mark.unit
def test_plugin_purchase_model():
    """Test PluginPurchase model"""
    purchase = PluginPurchase(
        plugin_id="plugin_123",
        user_id="user_123",
        price=99.99,
        payment_method="credit_card"
    )
    assert purchase.plugin_id == "plugin_123"
    assert purchase.price == 99.99
    assert purchase.payment_method == "credit_card"


@pytest.mark.unit
def test_plugin_purchase_negative_price():
    """Test PluginPurchase with negative price"""
    purchase = PluginPurchase(
        plugin_id="plugin_123",
        user_id="user_123",
        price=-99.99,
        payment_method="credit_card"
    )
    assert purchase.price == -99.99


@pytest.mark.unit
def test_developer_application_model():
    """Test DeveloperApplication model"""
    application = DeveloperApplication(
        developer_name="Dev Name",
        email="dev@example.com",
        company="Dev Corp",
        experience="5 years",
        portfolio_url="https://portfolio.com",
        github_username="devuser",
        description="Experienced developer"
    )
    assert application.developer_name == "Dev Name"
    assert application.email == "dev@example.com"
    assert application.company == "Dev Corp"
    assert application.github_username == "devuser"


@pytest.mark.unit
def test_developer_application_defaults():
    """Test DeveloperApplication with optional fields"""
    application = DeveloperApplication(
        developer_name="Dev Name",
        email="dev@example.com",
        experience="3 years",
        description="New developer"
    )
    assert application.company is None
    assert application.portfolio_url is None
    assert application.github_username is None
