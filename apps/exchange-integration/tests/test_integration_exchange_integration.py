"""Integration tests for exchange integration service"""

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


@pytest.mark.integration
def test_root_endpoint():
    """Test root endpoint"""
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "AITBC Exchange Integration"
    assert data["status"] == "running"


@pytest.mark.integration
def test_health_check_endpoint():
    """Test health check endpoint"""
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "exchanges_connected" in data
    assert "active_pairs" in data
    assert "total_orders" in data


@pytest.mark.integration
def test_register_exchange():
    """Test exchange registration"""
    client = TestClient(app)
    registration = ExchangeRegistration(
        name="TestExchange",
        api_key="test_key_123",
        sandbox=True
    )
    response = client.post("/api/v1/exchanges/register", json=registration.model_dump())
    assert response.status_code == 200
    data = response.json()
    assert data["exchange_id"] == "testexchange"
    assert data["status"] == "registered"
    assert data["name"] == "TestExchange"


@pytest.mark.integration
def test_register_duplicate_exchange():
    """Test registering duplicate exchange"""
    client = TestClient(app)
    registration = ExchangeRegistration(
        name="TestExchange",
        api_key="test_key_123"
    )
    
    # First registration
    client.post("/api/v1/exchanges/register", json=registration.model_dump())
    
    # Second registration should fail
    response = client.post("/api/v1/exchanges/register", json=registration.model_dump())
    assert response.status_code == 400


@pytest.mark.integration
def test_connect_exchange():
    """Test connecting to exchange"""
    client = TestClient(app)
    registration = ExchangeRegistration(
        name="TestExchange",
        api_key="test_key_123"
    )
    
    # Register exchange first
    client.post("/api/v1/exchanges/register", json=registration.model_dump())
    
    # Connect to exchange
    response = client.post("/api/v1/exchanges/testexchange/connect")
    assert response.status_code == 200
    data = response.json()
    assert data["exchange_id"] == "testexchange"
    assert data["status"] == "connected"


@pytest.mark.integration
def test_connect_nonexistent_exchange():
    """Test connecting to nonexistent exchange"""
    client = TestClient(app)
    response = client.post("/api/v1/exchanges/nonexistent/connect")
    assert response.status_code == 404


@pytest.mark.integration
def test_create_trading_pair():
    """Test creating trading pair"""
    client = TestClient(app)
    pair = TradingPair(
        symbol="AITBC/BTC",
        base_asset="AITBC",
        quote_asset="BTC",
        min_order_size=0.001,
        price_precision=8,
        quantity_precision=6
    )
    response = client.post("/api/v1/pairs/create", json=pair.model_dump())
    assert response.status_code == 200
    data = response.json()
    assert data["pair_id"] == "aitbc/btc"
    assert data["symbol"] == "AITBC/BTC"
    assert data["status"] == "created"


@pytest.mark.integration
def test_create_duplicate_trading_pair():
    """Test creating duplicate trading pair"""
    client = TestClient(app)
    pair = TradingPair(
        symbol="AITBC/BTC",
        base_asset="AITBC",
        quote_asset="BTC",
        min_order_size=0.001,
        price_precision=8,
        quantity_precision=6
    )
    
    # First creation
    client.post("/api/v1/pairs/create", json=pair.model_dump())
    
    # Second creation should fail
    response = client.post("/api/v1/pairs/create", json=pair.model_dump())
    assert response.status_code == 400


@pytest.mark.integration
def test_list_trading_pairs():
    """Test listing trading pairs"""
    client = TestClient(app)
    response = client.get("/api/v1/pairs")
    assert response.status_code == 200
    data = response.json()
    assert "pairs" in data
    assert "total_pairs" in data


@pytest.mark.integration
def test_get_trading_pair():
    """Test getting specific trading pair"""
    client = TestClient(app)
    pair = TradingPair(
        symbol="AITBC-BTC",
        base_asset="AITBC",
        quote_asset="BTC",
        min_order_size=0.001,
        price_precision=8,
        quantity_precision=6
    )
    
    # Create pair first
    client.post("/api/v1/pairs/create", json=pair.model_dump())
    
    # Get pair with lowercase symbol as pair_id
    response = client.get("/api/v1/pairs/aitbc-btc")
    assert response.status_code == 200
    data = response.json()
    assert data["symbol"] == "AITBC-BTC"


@pytest.mark.integration
def test_get_nonexistent_trading_pair():
    """Test getting nonexistent trading pair"""
    client = TestClient(app)
    response = client.get("/api/v1/pairs/nonexistent")
    assert response.status_code == 404


@pytest.mark.integration
def test_create_order():
    """Test creating order"""
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
    
    # Create order
    order = OrderRequest(
        symbol="AITBC/BTC",
        side="buy",
        type="limit",
        quantity=100.0,
        price=0.00001
    )
    response = client.post("/api/v1/orders", json=order.model_dump())
    assert response.status_code == 200
    data = response.json()
    assert data["symbol"] == "AITBC/BTC"
    assert data["side"] == "buy"
    assert data["status"] == "filled"
    assert data["filled_quantity"] == 100.0


@pytest.mark.integration
def test_create_order_nonexistent_pair():
    """Test creating order for nonexistent pair"""
    client = TestClient(app)
    order = OrderRequest(
        symbol="NONEXISTENT/BTC",
        side="buy",
        type="limit",
        quantity=100.0,
        price=0.00001
    )
    response = client.post("/api/v1/orders", json=order.model_dump())
    assert response.status_code == 404


@pytest.mark.integration
def test_list_orders():
    """Test listing orders"""
    client = TestClient(app)
    response = client.get("/api/v1/orders")
    assert response.status_code == 200
    data = response.json()
    assert "orders" in data
    assert "total_orders" in data


@pytest.mark.integration
def test_get_order():
    """Test getting specific order"""
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
    
    # Create order
    order = OrderRequest(
        symbol="AITBC/BTC",
        side="buy",
        type="limit",
        quantity=100.0,
        price=0.00001
    )
    create_response = client.post("/api/v1/orders", json=order.model_dump())
    order_id = create_response.json()["order_id"]
    
    # Get order
    response = client.get(f"/api/v1/orders/{order_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["order_id"] == order_id


@pytest.mark.integration
def test_get_nonexistent_order():
    """Test getting nonexistent order"""
    client = TestClient(app)
    response = client.get("/api/v1/orders/nonexistent")
    assert response.status_code == 404


@pytest.mark.integration
def test_list_exchanges():
    """Test listing exchanges"""
    client = TestClient(app)
    response = client.get("/api/v1/exchanges")
    assert response.status_code == 200
    data = response.json()
    assert "exchanges" in data
    assert "total_exchanges" in data


@pytest.mark.integration
def test_get_exchange():
    """Test getting specific exchange"""
    client = TestClient(app)
    registration = ExchangeRegistration(
        name="TestExchange",
        api_key="test_key_123"
    )
    
    # Register exchange first
    client.post("/api/v1/exchanges/register", json=registration.model_dump())
    
    # Get exchange
    response = client.get("/api/v1/exchanges/testexchange")
    assert response.status_code == 200
    data = response.json()
    assert data["exchange_id"] == "testexchange"


@pytest.mark.integration
def test_get_nonexistent_exchange():
    """Test getting nonexistent exchange"""
    client = TestClient(app)
    response = client.get("/api/v1/exchanges/nonexistent")
    assert response.status_code == 404


@pytest.mark.integration
def test_update_market_price():
    """Test updating market price"""
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
    client.post("/api/v1/pairs/create", json=pair.model_dump())
    
    # Update price
    price_data = {"price": 0.000015, "volume": 50000.0}
    response = client.post("/api/v1/market-data/aitbc-btc/price", json=price_data)
    assert response.status_code == 200
    data = response.json()
    assert data["current_price"] == 0.000015


@pytest.mark.integration
def test_update_price_nonexistent_pair():
    """Test updating price for nonexistent pair"""
    client = TestClient(app)
    price_data = {"price": 0.000015}
    response = client.post("/api/v1/market-data/nonexistent/price", json=price_data)
    assert response.status_code == 404


@pytest.mark.integration
def test_get_market_data():
    """Test getting market data"""
    client = TestClient(app)
    response = client.get("/api/v1/market-data")
    assert response.status_code == 200
    data = response.json()
    assert "market_data" in data
    assert "total_pairs" in data
