"""Unit tests for AI engine service"""

import pytest

from ai_service import AnalysisRequest, SimpleAITradingEngine, TradingRequest


@pytest.mark.unit
def test_ai_engine_initialization():
    """Test that AI engine initializes correctly"""
    engine = SimpleAITradingEngine()
    assert engine.models_loaded is True


@pytest.mark.unit
def test_trading_request_model():
    """Test TradingRequest model"""
    request = TradingRequest(symbol="AITBC/BTC", strategy="ai_enhanced")
    assert request.symbol == "AITBC/BTC"
    assert request.strategy == "ai_enhanced"


@pytest.mark.unit
def test_trading_request_defaults():
    """Test TradingRequest default values"""
    request = TradingRequest(symbol="AITBC/BTC")
    assert request.symbol == "AITBC/BTC"
    assert request.strategy == "ai_enhanced"


@pytest.mark.unit
def test_analysis_request_model():
    """Test AnalysisRequest model"""
    request = AnalysisRequest(symbol="AITBC/BTC", analysis_type="full")
    assert request.symbol == "AITBC/BTC"
    assert request.analysis_type == "full"


@pytest.mark.unit
def test_analysis_request_defaults():
    """Test AnalysisRequest default values"""
    request = AnalysisRequest(symbol="AITBC/BTC")
    assert request.symbol == "AITBC/BTC"
    assert request.analysis_type == "full"
