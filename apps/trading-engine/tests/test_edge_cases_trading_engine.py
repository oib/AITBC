"""Edge case and error handling tests for trading engine service"""

import pytest
import sys
import sys
from pathlib import Path
from fastapi.testclient import TestClient
from datetime import datetime


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


@pytest.mark.unit
def test_order_zero_quantity():
    """Test Order with zero quantity"""
    order = Order(
        order_id="order_123",
        symbol="AITBC/BTC",
        side="buy",
        type="limit",
        quantity=0.0,
        price=0.00001,
        user_id="user_123",
        timestamp=datetime.utcnow()
    )
    assert order.quantity == 0.0


@pytest.mark.unit
def test_order_negative_quantity():
    """Test Order with negative quantity"""
    order = Order(
        order_id="order_123",
        symbol="AITBC/BTC",
        side="buy",
        type="limit",
        quantity=-100.0,
        price=0.00001,
        user_id="user_123",
        timestamp=datetime.utcnow()
    )
    assert order.quantity == -100.0


@pytest.mark.unit
def test_order_negative_price():
    """Test Order with negative price"""
    order = Order(
        order_id="order_123",
        symbol="AITBC/BTC",
        side="buy",
        type="limit",
        quantity=100.0,
        price=-0.00001,
        user_id="user_123",
        timestamp=datetime.utcnow()
    )
    assert order.price == -0.00001


@pytest.mark.unit
def test_order_empty_symbol():
    """Test Order with empty symbol"""
    order = Order(
        order_id="order_123",
        symbol="",
        side="buy",
        type="limit",
        quantity=100.0,
        price=0.00001,
        user_id="user_123",
        timestamp=datetime.utcnow()
    )
    assert order.symbol == ""


@pytest.mark.integration
def test_cancel_filled_order():
    """Test cancelling a filled order"""
    client = TestClient(app)
    order = Order(
        order_id="order_129",
        symbol="AITBC/BTC",
        side="buy",
        type="limit",
        quantity=100.0,
        price=0.00001,
        user_id="user_123",
        timestamp=datetime.utcnow()
    )
    client.post("/api/v1/orders/submit", json=order.model_dump(mode='json'))
    
    # Manually mark as filled
    orders["order_129"]["status"] = "filled"
    
    response = client.delete("/api/v1/orders/order_129")
    assert response.status_code == 400


@pytest.mark.integration
def test_submit_order_with_slash_in_symbol():
    """Test submitting order with slash in symbol"""
    client = TestClient(app)
    order = Order(
        order_id="order_130",
        symbol="AITBC/BTC",
        side="buy",
        type="limit",
        quantity=100.0,
        price=0.00001,
        user_id="user_123",
        timestamp=datetime.utcnow()
    )
    response = client.post("/api/v1/orders/submit", json=order.model_dump(mode='json'))
    assert response.status_code == 200


@pytest.mark.integration
def test_submit_order_with_hyphen_in_symbol():
    """Test submitting order with hyphen in symbol"""
    client = TestClient(app)
    order = Order(
        order_id="order_131",
        symbol="AITBC-BTC",
        side="buy",
        type="limit",
        quantity=100.0,
        price=0.00001,
        user_id="user_123",
        timestamp=datetime.utcnow()
    )
    response = client.post("/api/v1/orders/submit", json=order.model_dump(mode='json'))
    assert response.status_code == 200


@pytest.mark.integration
def test_list_orders_with_no_orders():
    """Test listing orders when no orders exist"""
    client = TestClient(app)
    response = client.get("/api/v1/orders")
    assert response.status_code == 200
    data = response.json()
    assert data["total_orders"] == 0


@pytest.mark.integration
def test_list_trades_with_no_trades():
    """Test listing trades when no trades exist"""
    client = TestClient(app)
    response = client.get("/api/v1/trades")
    assert response.status_code == 200
    data = response.json()
    assert data["total_trades"] == 0


@pytest.mark.integration
def test_get_market_data_with_no_symbols():
    """Test getting market data when no symbols exist"""
    client = TestClient(app)
    response = client.get("/api/v1/market-data")
    assert response.status_code == 200
    data = response.json()
    assert data["total_symbols"] == 0


@pytest.mark.integration
def test_order_book_depth_parameter():
    """Test order book with depth parameter"""
    client = TestClient(app)
    order = Order(
        order_id="order_132",
        symbol="AITBC-BTC",
        side="buy",
        type="limit",
        quantity=100.0,
        price=0.00001,
        user_id="user_123",
        timestamp=datetime.utcnow()
    )
    client.post("/api/v1/orders/submit", json=order.model_dump(mode='json'))
    
    response = client.get("/api/v1/orderbook/AITBC-BTC?depth=5")
    assert response.status_code == 200
    data = response.json()
    assert data["symbol"] == "AITBC-BTC"


@pytest.mark.integration
def test_list_trades_limit_parameter():
    """Test listing trades with limit parameter"""
    client = TestClient(app)
    response = client.get("/api/v1/trades?limit=10")
    assert response.status_code == 200
    data = response.json()
    assert "trades" in data
