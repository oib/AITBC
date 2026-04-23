"""Unit tests for trading engine service"""

import pytest
import sys
import sys
from pathlib import Path
from datetime import datetime


from main import app, Order, Trade, OrderBookEntry


@pytest.mark.unit
def test_app_initialization():
    """Test that the FastAPI app initializes correctly"""
    assert app is not None
    assert app.title == "AITBC Trading Engine"
    assert app.version == "1.0.0"


@pytest.mark.unit
def test_order_model():
    """Test Order model"""
    order = Order(
        order_id="order_123",
        symbol="AITBC/BTC",
        side="buy",
        type="limit",
        quantity=100.0,
        price=0.00001,
        user_id="user_123",
        timestamp=datetime.utcnow()
    )
    assert order.order_id == "order_123"
    assert order.symbol == "AITBC/BTC"
    assert order.side == "buy"
    assert order.type == "limit"
    assert order.quantity == 100.0
    assert order.price == 0.00001
    assert order.user_id == "user_123"


@pytest.mark.unit
def test_order_model_market_order():
    """Test Order model for market order"""
    order = Order(
        order_id="order_123",
        symbol="AITBC/BTC",
        side="sell",
        type="market",
        quantity=50.0,
        user_id="user_123",
        timestamp=datetime.utcnow()
    )
    assert order.type == "market"
    assert order.price is None


@pytest.mark.unit
def test_trade_model():
    """Test Trade model"""
    trade = Trade(
        trade_id="trade_123",
        symbol="AITBC/BTC",
        buy_order_id="buy_order_123",
        sell_order_id="sell_order_123",
        quantity=100.0,
        price=0.00001,
        timestamp=datetime.utcnow()
    )
    assert trade.trade_id == "trade_123"
    assert trade.symbol == "AITBC/BTC"
    assert trade.buy_order_id == "buy_order_123"
    assert trade.sell_order_id == "sell_order_123"
    assert trade.quantity == 100.0
    assert trade.price == 0.00001


@pytest.mark.unit
def test_order_book_entry_model():
    """Test OrderBookEntry model"""
    entry = OrderBookEntry(
        price=0.00001,
        quantity=1000.0,
        orders_count=5
    )
    assert entry.price == 0.00001
    assert entry.quantity == 1000.0
    assert entry.orders_count == 5
