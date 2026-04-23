"""Unit tests for exchange service"""

import pytest
import sys
import sys
from pathlib import Path


from exchange_api import app, OrderCreate, OrderResponse, TradeResponse, OrderBookResponse


@pytest.mark.unit
def test_app_initialization():
    """Test that the FastAPI app initializes correctly"""
    assert app is not None
    assert app.title == "AITBC Trade Exchange API"
    assert app.version == "1.0.0"


@pytest.mark.unit
def test_order_create_model():
    """Test OrderCreate model"""
    order = OrderCreate(
        order_type="BUY",
        amount=100.0,
        price=0.00001
    )
    assert order.order_type == "BUY"
    assert order.amount == 100.0
    assert order.price == 0.00001


@pytest.mark.unit
def test_order_create_model_sell():
    """Test OrderCreate model with SELL"""
    order = OrderCreate(
        order_type="SELL",
        amount=50.0,
        price=0.00002
    )
    assert order.order_type == "SELL"
    assert order.amount == 50.0


@pytest.mark.unit
def test_order_response_model():
    """Test OrderResponse model"""
    from datetime import datetime
    order = OrderResponse(
        id=1,
        order_type="BUY",
        amount=100.0,
        price=0.00001,
        total=0.001,
        filled=0.0,
        remaining=100.0,
        status="OPEN",
        created_at=datetime.utcnow()
    )
    assert order.id == 1
    assert order.order_type == "BUY"
    assert order.amount == 100.0
    assert order.status == "OPEN"


@pytest.mark.unit
def test_trade_response_model():
    """Test TradeResponse model"""
    from datetime import datetime
    trade = TradeResponse(
        id=1,
        amount=50.0,
        price=0.00001,
        total=0.0005,
        created_at=datetime.utcnow()
    )
    assert trade.id == 1
    assert trade.amount == 50.0
    assert trade.total == 0.0005


@pytest.mark.unit
def test_order_book_response_model():
    """Test OrderBookResponse model"""
    from datetime import datetime
    buy_order = OrderResponse(
        id=1,
        order_type="BUY",
        amount=100.0,
        price=0.00001,
        total=0.001,
        filled=0.0,
        remaining=100.0,
        status="OPEN",
        created_at=datetime.utcnow()
    )
    sell_order = OrderResponse(
        id=2,
        order_type="SELL",
        amount=50.0,
        price=0.00002,
        total=0.001,
        filled=0.0,
        remaining=50.0,
        status="OPEN",
        created_at=datetime.utcnow()
    )
    orderbook = OrderBookResponse(buys=[buy_order], sells=[sell_order])
    assert len(orderbook.buys) == 1
    assert len(orderbook.sells) == 1


@pytest.mark.unit
def test_order_create_negative_amount():
    """Test OrderCreate with negative amount"""
    order = OrderCreate(
        order_type="BUY",
        amount=-10.0,
        price=0.00001
    )
    assert order.amount == -10.0


@pytest.mark.unit
def test_order_create_zero_price():
    """Test OrderCreate with zero price"""
    order = OrderCreate(
        order_type="BUY",
        amount=100.0,
        price=0.0
    )
    assert order.price == 0.0


@pytest.mark.unit
def test_order_create_invalid_type():
    """Test OrderCreate with invalid order type"""
    # Model accepts any string, validation happens at endpoint level
    order = OrderCreate(
        order_type="INVALID",
        amount=100.0,
        price=0.00001
    )
    assert order.order_type == "INVALID"
