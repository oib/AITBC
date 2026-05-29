"""Unit tests for exchange integration service"""

import pytest
import sys
import sys
from pathlib import Path
from unittest.mock import Mock, patch


# Mock aiohttp before importing
sys.modules['aiohttp'] = Mock()

from main import app, ExchangeRegistration, TradingPair, OrderRequest


@pytest.mark.unit
def test_app_initialization():
    """Test that the FastAPI app initializes correctly"""
    assert app is not None
    assert app.title == "AITBC Exchange Integration Service"
    assert app.version == "1.0.0"


@pytest.mark.unit
def test_exchange_registration_model():
    """Test ExchangeRegistration model"""
    registration = ExchangeRegistration(
        name="TestExchange",
        api_key="test_key_123",
        sandbox=True,
        description="Test exchange"
    )
    assert registration.name == "TestExchange"
    assert registration.api_key == "test_key_123"
    assert registration.sandbox is True
    assert registration.description == "Test exchange"


@pytest.mark.unit
def test_exchange_registration_defaults():
    """Test ExchangeRegistration default values"""
    registration = ExchangeRegistration(
        name="TestExchange",
        api_key="test_key_123"
    )
    assert registration.name == "TestExchange"
    assert registration.api_key == "test_key_123"
    assert registration.sandbox is True
    assert registration.description is None


@pytest.mark.unit
def test_trading_pair_model():
    """Test TradingPair model"""
    pair = TradingPair(
        symbol="AITBC/BTC",
        base_asset="AITBC",
        quote_asset="BTC",
        min_order_size=0.001,
        price_precision=8,
        quantity_precision=6
    )
    assert pair.symbol == "AITBC/BTC"
    assert pair.base_asset == "AITBC"
    assert pair.quote_asset == "BTC"
    assert pair.min_order_size == 0.001
    assert pair.price_precision == 8
    assert pair.quantity_precision == 6


@pytest.mark.unit
def test_order_request_model():
    """Test OrderRequest model"""
    order = OrderRequest(
        symbol="AITBC/BTC",
        side="buy",
        type="limit",
        quantity=100.0,
        price=0.00001
    )
    assert order.symbol == "AITBC/BTC"
    assert order.side == "buy"
    assert order.type == "limit"
    assert order.quantity == 100.0
    assert order.price == 0.00001


@pytest.mark.unit
def test_order_request_market_order():
    """Test OrderRequest for market order"""
    order = OrderRequest(
        symbol="AITBC/BTC",
        side="sell",
        type="market",
        quantity=50.0
    )
    assert order.symbol == "AITBC/BTC"
    assert order.side == "sell"
    assert order.type == "market"
    assert order.quantity == 50.0
    assert order.price is None
