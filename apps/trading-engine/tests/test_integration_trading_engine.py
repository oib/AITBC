"""Integration tests for trading engine service"""

import pytest
import sys
import sys
from pathlib import Path
from fastapi.testclient import TestClient
from datetime import datetime, UTC


from main import app, Order, order_books, orders, trades


@pytest.fixture(autouse=True)
def reset_state():
    """Reset global state before each test"""
    order_books.clear()
    orders.clear()
    trades.clear()
    yield
    order_books.clear()
    orders.clear()
    trades.clear()


@pytest.mark.integration
def test_root_endpoint():
    """Test root endpoint"""
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "AITBC Trading Engine"
    assert data["status"] == "running"


@pytest.mark.integration
def test_health_check_endpoint():
    """Test health check endpoint"""
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "active_order_books" in data
    assert "total_orders" in data


@pytest.mark.integration
def test_submit_market_order():
    """Test submitting a market order"""
    client = TestClient(app)
    order = Order(
        order_id="order_123",
        symbol="AITBC/BTC",
        side="buy",
        type="market",
        quantity=100.0,
        user_id="user_123",
        timestamp=datetime.now(datetime.UTC)
    )
    response = client.post("/api/v1/orders/submit", json=order.model_dump(mode='json'))
    assert response.status_code == 200
    data = response.json()
    assert data["order_id"] == "order_123"
    assert "status" in data


@pytest.mark.integration
def test_submit_limit_order():
    """Test submitting a limit order"""
    client = TestClient(app)
    order = Order(
        order_id="order_124",
        symbol="AITBC/BTC",
        side="buy",
        type="limit",
        quantity=100.0,
        price=0.00001,
        user_id="user_123",
        timestamp=datetime.now(datetime.UTC)
    )
    response = client.post("/api/v1/orders/submit", json=order.model_dump(mode='json'))
    assert response.status_code == 200
    data = response.json()
    assert data["order_id"] == "order_124"
    assert "status" in data


@pytest.mark.integration
def test_get_order():
    """Test getting order details"""
    client = TestClient(app)
    order = Order(
        order_id="order_125",
        symbol="AITBC/BTC",
        side="buy",
        type="limit",
        quantity=100.0,
        price=0.00001,
        user_id="user_123",
        timestamp=datetime.now(datetime.UTC)
    )
    client.post("/api/v1/orders/submit", json=order.model_dump(mode='json'))
    
    response = client.get("/api/v1/orders/order_125")
    assert response.status_code == 200
    data = response.json()
    assert data["order_id"] == "order_125"


@pytest.mark.integration
def test_get_order_not_found():
    """Test getting nonexistent order"""
    client = TestClient(app)
    response = client.get("/api/v1/orders/nonexistent")
    assert response.status_code == 404


@pytest.mark.integration
def test_list_orders():
    """Test listing all orders"""
    client = TestClient(app)
    response = client.get("/api/v1/orders")
    assert response.status_code == 200
    data = response.json()
    assert "orders" in data
    assert "total_orders" in data


@pytest.mark.integration
def test_get_order_book():
    """Test getting order book"""
    client = TestClient(app)
    # Create some orders first
    order1 = Order(
        order_id="order_126",
        symbol="AITBC-BTC",
        side="buy",
        type="limit",
        quantity=100.0,
        price=0.00001,
        user_id="user_123",
        timestamp=datetime.now(datetime.UTC)
    )
    client.post("/api/v1/orders/submit", json=order1.model_dump(mode='json'))
    
    response = client.get("/api/v1/orderbook/AITBC-BTC")
    assert response.status_code == 200
    data = response.json()
    assert data["symbol"] == "AITBC-BTC"
    assert "bids" in data
    assert "asks" in data


@pytest.mark.integration
def test_get_order_book_not_found():
    """Test getting order book for nonexistent symbol"""
    client = TestClient(app)
    response = client.get("/api/v1/orderbook/NONEXISTENT")
    assert response.status_code == 404


@pytest.mark.integration
def test_list_trades():
    """Test listing trades"""
    client = TestClient(app)
    response = client.get("/api/v1/trades")
    assert response.status_code == 200
    data = response.json()
    assert "trades" in data
    assert "total_trades" in data


@pytest.mark.integration
def test_list_trades_by_symbol():
    """Test listing trades by symbol"""
    client = TestClient(app)
    response = client.get("/api/v1/trades?symbol=AITBC-BTC")
    assert response.status_code == 200
    data = response.json()
    assert "trades" in data


@pytest.mark.integration
def test_get_ticker():
    """Test getting ticker information"""
    client = TestClient(app)
    # Create order book first
    order = Order(
        order_id="order_127",
        symbol="AITBC-BTC",
        side="buy",
        type="limit",
        quantity=100.0,
        price=0.00001,
        user_id="user_123",
        timestamp=datetime.now(datetime.UTC)
    )
    client.post("/api/v1/orders/submit", json=order.model_dump(mode='json'))
    
    response = client.get("/api/v1/ticker/AITBC-BTC")
    assert response.status_code == 200
    data = response.json()
    assert data["symbol"] == "AITBC-BTC"


@pytest.mark.integration
def test_get_ticker_not_found():
    """Test getting ticker for nonexistent symbol"""
    client = TestClient(app)
    response = client.get("/api/v1/ticker/NONEXISTENT")
    assert response.status_code == 404


@pytest.mark.integration
def test_cancel_order():
    """Test cancelling an order"""
    client = TestClient(app)
    order = Order(
        order_id="order_128",
        symbol="AITBC/BTC",
        side="buy",
        type="limit",
        quantity=100.0,
        price=0.00001,
        user_id="user_123",
        timestamp=datetime.now(datetime.UTC)
    )
    client.post("/api/v1/orders/submit", json=order.model_dump(mode='json'))
    
    response = client.delete("/api/v1/orders/order_128")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "cancelled"


@pytest.mark.integration
def test_cancel_order_not_found():
    """Test cancelling nonexistent order"""
    client = TestClient(app)
    response = client.delete("/api/v1/orders/nonexistent")
    assert response.status_code == 404


@pytest.mark.integration
def test_get_market_data():
    """Test getting market data"""
    client = TestClient(app)
    response = client.get("/api/v1/market-data")
    assert response.status_code == 200
    data = response.json()
    assert "market_data" in data
    assert "total_symbols" in data


@pytest.mark.integration
def test_get_engine_stats():
    """Test getting engine statistics"""
    client = TestClient(app)
    response = client.get("/api/v1/engine/stats")
    assert response.status_code == 200
    data = response.json()
    assert "engine_stats" in data
