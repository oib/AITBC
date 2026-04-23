"""Unit tests for AI engine service"""

import pytest
import sys
import sys
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime


# Mock numpy before importing
sys.modules['numpy'] = MagicMock()

from ai_service import SimpleAITradingEngine, TradingRequest, AnalysisRequest


@pytest.mark.unit
def test_ai_engine_initialization():
    """Test that AI engine initializes correctly"""
    engine = SimpleAITradingEngine()
    assert engine.models_loaded is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_analyze_market():
    """Test market analysis functionality"""
    engine = SimpleAITradingEngine()
    
    # Mock numpy to return consistent values
    with patch('ai_service.np.random.uniform') as mock_uniform:
        mock_uniform.side_effect = [0.005, 0.02, 5000, 50, 0.005, 0.03, 0.01, 0.8, 0.6, 0.03, 0.5, 0.4]
        with patch('ai_service.np.random.choice') as mock_choice:
            mock_choice.return_value = 'bullish'
            
            result = await engine.analyze_market('AITBC/BTC')
            
            assert result['symbol'] == 'AITBC/BTC'
            assert 'current_price' in result
            assert 'price_change_24h' in result
            assert 'volume_24h' in result
            assert 'rsi' in result
            assert 'macd' in result
            assert 'volatility' in result
            assert 'ai_predictions' in result
            assert 'timestamp' in result
            
            # Check AI predictions structure
            predictions = result['ai_predictions']
            assert 'price_prediction' in predictions
            assert 'risk_assessment' in predictions
            assert 'sentiment_analysis' in predictions


@pytest.mark.unit
@pytest.mark.asyncio
async def test_make_trading_decision_buy():
    """Test trading decision for buy signal"""
    engine = SimpleAITradingEngine()
    
    with patch('ai_service.np.random.uniform') as mock_uniform:
        # Set values to produce a buy signal
        mock_uniform.side_effect = [0.005, 0.02, 5000, 50, 0.005, 0.03, 0.01, 0.8, 0.6, 0.03, 0.5, 0.4, 0.5, 0.3, 0.1]
        with patch('ai_service.np.random.choice') as mock_choice:
            mock_choice.return_value = 'bullish'
            
            result = await engine.make_trading_decision('AITBC/BTC')
            
            assert result['symbol'] == 'AITBC/BTC'
            assert 'signal' in result
            assert 'confidence' in result
            assert 'quantity' in result
            assert 'price' in result
            assert 'reasoning' in result
            assert 'timestamp' in result


@pytest.mark.unit
@pytest.mark.asyncio
async def test_make_trading_decision_sell():
    """Test trading decision for sell signal"""
    engine = SimpleAITradingEngine()
    
    with patch('ai_service.np.random.uniform') as mock_uniform:
        # Set values to produce a sell signal
        mock_uniform.side_effect = [0.005, -0.02, 5000, 50, 0.005, 0.03, 0.01, 0.8, 0.6, 0.03, -0.5, 0.4, -0.5, 0.3, 0.1]
        with patch('ai_service.np.random.choice') as mock_choice:
            mock_choice.return_value = 'bearish'
            
            result = await engine.make_trading_decision('AITBC/BTC')
            
            assert result['symbol'] == 'AITBC/BTC'
            assert result['signal'] in ['buy', 'sell', 'hold']


@pytest.mark.unit
@pytest.mark.asyncio
async def test_make_trading_decision_hold():
    """Test trading decision for hold signal"""
    engine = SimpleAITradingEngine()
    
    with patch('ai_service.np.random.uniform') as mock_uniform:
        # Set values to produce a hold signal
        mock_uniform.side_effect = [0.005, 0.01, 5000, 50, 0.005, 0.03, 0.01, 0.8, 0.6, 0.03, 0.0, 0.4, 0.0, 0.3, 0.1]
        with patch('ai_service.np.random.choice') as mock_choice:
            mock_choice.return_value = 'neutral'
            
            result = await engine.make_trading_decision('AITBC/BTC')
            
            assert result['symbol'] == 'AITBC/BTC'
            assert result['signal'] in ['buy', 'sell', 'hold']


@pytest.mark.unit
def test_trading_request_model():
    """Test TradingRequest model"""
    request = TradingRequest(symbol='AITBC/BTC', strategy='ai_enhanced')
    assert request.symbol == 'AITBC/BTC'
    assert request.strategy == 'ai_enhanced'


@pytest.mark.unit
def test_trading_request_defaults():
    """Test TradingRequest default values"""
    request = TradingRequest(symbol='AITBC/BTC')
    assert request.symbol == 'AITBC/BTC'
    assert request.strategy == 'ai_enhanced'


@pytest.mark.unit
def test_analysis_request_model():
    """Test AnalysisRequest model"""
    request = AnalysisRequest(symbol='AITBC/BTC', analysis_type='full')
    assert request.symbol == 'AITBC/BTC'
    assert request.analysis_type == 'full'


@pytest.mark.unit
def test_analysis_request_defaults():
    """Test AnalysisRequest default values"""
    request = AnalysisRequest(symbol='AITBC/BTC')
    assert request.symbol == 'AITBC/BTC'
    assert request.analysis_type == 'full'
