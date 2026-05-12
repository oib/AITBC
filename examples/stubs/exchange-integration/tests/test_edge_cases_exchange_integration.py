"""Edge case and error handling tests for exchange integration service"""

import pytest
import sys
import sys
from pathlib import Path
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient


# Mock aiohttp before importing
sys.modules['aiohttp'] = Mock()

from main import app, ExchangeRegistration, TradingPair, OrderRequest, exchanges, trading_pairs, orders


@pytest.fixture(autouse=True)
def reset_state():
    """Reset global state before each test"""
    exchanges.clear()
    trading_pairs.clear()
    orders.clear()
    yield
    exchanges.clear()
    trading_pairs.clear()
    orders.clear()


@pytest.mark.unit
def test_exchange_registration_empty_name():
    """Test ExchangeRegistration with empty name"""
    registration = ExchangeRegistration(
        name="",
        api_key="test_key_123"
    )
    assert registration.name == ""


@pytest.mark.unit
def test_exchange_registration_empty_api_key():
    """Test ExchangeRegistration with empty API key"""
    registration = ExchangeRegistration(
        name="TestExchange",
        api_key=""
    )
    assert registration.api_key == ""


@pytest.mark.unit
def test_trading_pair_zero_min_order_size():
    """Test TradingPair with zero min order size"""
    pair = TradingPair(
        symbol="AITBC/BTC",
        base_asset="AITBC",
        quote_asset="BTC",
        min_order_size=0.0,
        price_precision=8,
        quantity_precision=6
    )
    assert pair.min_order_size == 0.0


@pytest.mark.unit
def test_trading_pair_negative_min_order_size():
    """Test TradingPair with negative min order size"""
    pair = TradingPair(
        symbol="AITBC/BTC",
        base_asset="AITBC",
        quote_asset="BTC",
        min_order_size=-0.001,
        price_precision=8,
        quantity_precision=6
    )
    assert pair.min_order_size == -0.001


@pytest.mark.unit
def test_order_request_zero_quantity():
    """Test OrderRequest with zero quantity"""
    order = OrderRequest(
        symbol="AITBC/BTC",
        side="buy",
        type="limit",
        quantity=0.0,
        price=0.00001
    )
    assert order.quantity == 0.0


@pytest.mark.unit
def test_order_request_negative_quantity():
    """Test OrderRequest with negative quantity"""
    order = OrderRequest(
        symbol="AITBC/BTC",
        side="buy",
        type="limit",
        quantity=-100.0,
        price=0.00001
    )
    assert order.quantity == -100.0


@pytest.mark.integration
def test_order_request_invalid_side():
    """Test OrderRequest with invalid side"""
    client = TestClient(app)
    
    # Create trading pair first
    pair = TradingPair(
        symbol="AITBC/BTC",
        base_asset="AITBC",
        quote_asset="BTC",
        min_order_size=0.001,
        price_precision=8,
        quantity_precision=6
    )
    client.post("/api/v1/pairs/create", json=pair.model_dump())
    
    # Create order with invalid side (API doesn't validate, but test the behavior)
    order = OrderRequest(
        symbol="AITBC/BTC",
        side="invalid",
        type="limit",
        quantity=100.0,
        price=0.00001
    )
    # This will be accepted by the API as it doesn't validate the side
    response = client.post("/api/v1/orders", json=order.model_dump())
    assert response.status_code == 200


@pytest.mark.integration
def test_order_request_invalid_type():
    """Test OrderRequest with invalid type"""
    client = TestClient(app)
    
    # Create trading pair first
    pair = TradingPair(
        symbol="AITBC/BTC",
        base_asset="AITBC",
        quote_asset="BTC",
        min_order_size=0.001,
        price_precision=8,
        quantity_precision=6
    )
    client.post("/api/v1/pairs/create", json=pair.model_dump())
    
    # Create order with invalid type (API doesn't validate, but test the behavior)
    order = OrderRequest(
        symbol="AITBC/BTC",
        side="buy",
        type="invalid",
        quantity=100.0,
        price=0.00001
    )
    # This will be accepted by the API as it doesn't validate the type
    response = client.post("/api/v1/orders", json=order.model_dump())
    assert response.status_code == 200


@pytest.mark.integration
def test_connect_already_connected_exchange():
    """Test connecting to already connected exchange"""
    client = TestClient(app)
    registration = ExchangeRegistration(
        name="TestExchange",
        api_key="test_key_123"
    )
    
    # Register exchange
    client.post("/api/v1/exchanges/register", json=registration.model_dump())
    
    # Connect first time
    client.post("/api/v1/exchanges/testexchange/connect")
    
    # Connect second time should return already_connected
    response = client.post("/api/v1/exchanges/testexchange/connect")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "already_connected"


@pytest.mark.integration
def test_update_market_price_missing_fields():
    """Test updating market price with missing fields"""
    client = TestClient(app)
    
    # Create trading pair first
    pair = TradingPair(
        symbol="AITBC-BTC",
        base_asset="AITBC",
        quote_asset="BTC",
        min_order_size=0.001,
        price_precision=8,
        quantity_precision=6
    )
    create_response = client.post("/api/v1/pairs/create", json=pair.model_dump())
    assert create_response.status_code == 200
    
    # Update with missing price
    price_data = {"volume": 50000.0}
    response = client.post("/api/v1/market-data/aitbc-btc/price", json=price_data)
    assert response.status_code == 200
    data = response.json()
    # Should use None for missing price
    assert data["current_price"] is None


@pytest.mark.integration
def test_update_market_price_zero_price():
    """Test updating market price with zero price"""
    client = TestClient(app)
    
    # Create trading pair first
    pair = TradingPair(
        symbol="AITBC-BTC",
        base_asset="AITBC",
        quote_asset="BTC",
        min_order_size=0.001,
        price_precision=8,
        quantity_precision=6
    )
    create_response = client.post("/api/v1/pairs/create", json=pair.model_dump())
    assert create_response.status_code == 200
    
    # Update with zero price
    price_data = {"price": 0.0}
    response = client.post("/api/v1/market-data/aitbc-btc/price", json=price_data)
    assert response.status_code == 200
    data = response.json()
    assert data["current_price"] == 0.0


@pytest.mark.integration
def test_update_market_price_negative_price():
    """Test updating market price with negative price"""
    client = TestClient(app)
    
    # Create trading pair first
    pair = TradingPair(
        symbol="AITBC-BTC",
        base_asset="AITBC",
        quote_asset="BTC",
        min_order_size=0.001,
        price_precision=8,
        quantity_precision=6
    )
    create_response = client.post("/api/v1/pairs/create", json=pair.model_dump())
    assert create_response.status_code == 200
    
    # Update with negative price
    price_data = {"price": -0.00001}
    response = client.post("/api/v1/market-data/aitbc-btc/price", json=price_data)
    assert response.status_code == 200
    data = response.json()
    assert data["current_price"] == -0.00001
