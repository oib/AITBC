"""Edge case and error handling tests for exchange service"""

import pytest
import sys
import sys
from pathlib import Path


from exchange_api import OrderCreate, OrderResponse, TradeResponse, OrderBookResponse
from datetime import datetime, UTC


@pytest.mark.unit
def test_order_create_empty_type():
    """Test OrderCreate with empty order type"""
    order = OrderCreate(
        order_type="",
        amount=100.0,
        price=0.00001
    )
    assert order.order_type == ""


@pytest.mark.unit
def test_order_create_zero_amount():
    """Test OrderCreate with zero amount"""
    order = OrderCreate(
        order_type="BUY",
        amount=0.0,
        price=0.00001
    )
    assert order.amount == 0.0


@pytest.mark.unit
def test_order_create_negative_price():
    """Test OrderCreate with negative price"""
    order = OrderCreate(
        order_type="BUY",
        amount=100.0,
        price=-0.00001
    )
    assert order.price == -0.00001


@pytest.mark.unit
def test_order_response_zero_remaining():
    """Test OrderResponse with zero remaining"""
    order = OrderResponse(
        id=1,
        order_type="BUY",
        amount=100.0,
        price=0.00001,
        total=0.001,
        filled=100.0,
        remaining=0.0,
        status="FILLED",
        created_at=datetime.now(datetime.UTC)
    )
    assert order.remaining == 0.0
    assert order.status == "FILLED"


@pytest.mark.unit
def test_order_response_empty_status():
    """Test OrderResponse with empty status"""
    order = OrderResponse(
        id=1,
        order_type="BUY",
        amount=100.0,
        price=0.00001,
        total=0.001,
        filled=0.0,
        remaining=100.0,
        status="",
        created_at=datetime.now(datetime.UTC)
    )
    assert order.status == ""


@pytest.mark.unit
def test_trade_response_zero_amount():
    """Test TradeResponse with zero amount"""
    trade = TradeResponse(
        id=1,
        amount=0.0,
        price=0.00001,
        total=0.0,
        created_at=datetime.now(datetime.UTC)
    )
    assert trade.amount == 0.0
    assert trade.total == 0.0


@pytest.mark.unit
def test_order_book_empty_buys():
    """Test OrderBookResponse with empty buys"""
    orderbook = OrderBookResponse(buys=[], sells=[])
    assert len(orderbook.buys) == 0
    assert len(orderbook.sells) == 0


@pytest.mark.unit
def test_order_book_empty_sells():
    """Test OrderBookResponse with empty sells"""
    from datetime import datetime, UTC
    buy_order = OrderResponse(
        id=1,
        order_type="BUY",
        amount=100.0,
        price=0.00001,
        total=0.001,
        filled=0.0,
        remaining=100.0,
        status="OPEN",
        created_at=datetime.now(datetime.UTC)
    )
    orderbook = OrderBookResponse(buys=[buy_order], sells=[])
    assert len(orderbook.buys) == 1
    assert len(orderbook.sells) == 0


@pytest.mark.unit
def test_order_create_very_large_amount():
    """Test OrderCreate with very large amount"""
    order = OrderCreate(
        order_type="BUY",
        amount=9999999999.0,
        price=0.00001
    )
    assert order.amount == 9999999999.0


@pytest.mark.unit
def test_order_create_very_small_price():
    """Test OrderCreate with very small price"""
    order = OrderCreate(
        order_type="BUY",
        amount=100.0,
        price=0.000000001
    )
    assert order.price == 0.000000001
