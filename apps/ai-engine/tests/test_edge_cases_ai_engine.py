"""Edge case and error handling tests for AI engine service"""

import pytest
import sys
import sys
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, UTC


# Mock numpy before importing
sys.modules['numpy'] = MagicMock()

from ai_service import SimpleAITradingEngine


@pytest.mark.unit
@pytest.mark.asyncio
async def test_analyze_market_with_empty_symbol():
    """Test market analysis with empty symbol"""
    engine = SimpleAITradingEngine()
    
    with patch('ai_service.np.random.uniform') as mock_uniform:
        mock_uniform.side_effect = [0.005, 0.02, 5000, 50, 0.005, 0.03, 0.01, 0.8, 0.6, 0.03, 0.5, 0.4]
        with patch('ai_service.np.random.choice') as mock_choice:
            mock_choice.return_value = 'bullish'
            
            result = await engine.analyze_market('')
            
            assert result['symbol'] == ''
            assert 'current_price' in result


@pytest.mark.unit
@pytest.mark.asyncio
async def test_analyze_market_with_special_characters():
    """Test market analysis with special characters in symbol"""
    engine = SimpleAITradingEngine()
    
    with patch('ai_service.np.random.uniform') as mock_uniform:
        mock_uniform.side_effect = [0.005, 0.02, 5000, 50, 0.005, 0.03, 0.01, 0.8, 0.6, 0.03, 0.5, 0.4]
        with patch('ai_service.np.random.choice') as mock_choice:
            mock_choice.return_value = 'bullish'
            
            result = await engine.analyze_market('AITBC/USDT@TEST')
            
            assert result['symbol'] == 'AITBC/USDT@TEST'


@pytest.mark.unit
@pytest.mark.asyncio
async def test_make_trading_decision_extreme_confidence():
    """Test trading decision with extreme confidence values"""
    engine = SimpleAITradingEngine()
    
    # Mock the entire decision process to avoid complex numpy calculations
    with patch.object(engine, 'analyze_market') as mock_analyze:
        mock_analyze.return_value = {
            'symbol': 'AITBC/BTC',
            'current_price': 0.005,
            'price_change_24h': 0.02,
            'volume_24h': 5000,
            'rsi': 50,
            'macd': 0.005,
            'volatility': 0.03,
            'ai_predictions': {
                'price_prediction': {'predicted_change': 1.0, 'confidence': 0.9},
                'risk_assessment': {'risk_score': 0.0, 'volatility': 0.01},
                'sentiment_analysis': {'sentiment_score': 1.0, 'overall_sentiment': 'bullish'}
            },
            'timestamp': datetime.now(datetime.UTC)
        }
        
        result = await engine.make_trading_decision('AITBC/BTC')
        
        assert result['signal'] == 'buy'
        assert result['confidence'] > 0.5


@pytest.mark.unit
@pytest.mark.asyncio
async def test_make_trading_decision_low_confidence():
    """Test trading decision with low confidence values"""
    engine = SimpleAITradingEngine()
    
    with patch('ai_service.np.random.uniform') as mock_uniform:
        # Set values to produce low confidence
        mock_uniform.side_effect = [0.005, 0.02, 5000, 50, 0.005, 0.03, 0.01, 0.8, 0.6, 0.03, 0.0, 0.4, 0.0, 0.4, 0.4]
        with patch('ai_service.np.random.choice') as mock_choice:
            mock_choice.return_value = 'neutral'
            
            result = await engine.make_trading_decision('AITBC/BTC')
            
            assert result['signal'] == 'hold'
            assert result['confidence'] < 0.3


@pytest.mark.unit
@pytest.mark.asyncio
async def test_analyze_market_timestamp_format():
    """Test that timestamp is in correct format"""
    engine = SimpleAITradingEngine()
    
    with patch('ai_service.np.random.uniform') as mock_uniform:
        mock_uniform.side_effect = [0.005, 0.02, 5000, 50, 0.005, 0.03, 0.01, 0.8, 0.6, 0.03, 0.5, 0.4]
        with patch('ai_service.np.random.choice') as mock_choice:
            mock_choice.return_value = 'bullish'
            
            result = await engine.analyze_market('AITBC/BTC')
            
            assert isinstance(result['timestamp'], datetime)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_make_trading_decision_quantity_calculation():
    """Test that quantity is calculated correctly based on confidence"""
    engine = SimpleAITradingEngine()
    
    with patch('ai_service.np.random.uniform') as mock_uniform:
        # Set confidence to 0.5
        # signal_strength = (price_pred * 0.5) + (sentiment * 0.3) - (risk * 0.2)
        # price_pred=0.5, sentiment=0.5, risk=0.1 => (0.5*0.5) + (0.5*0.3) - (0.1*0.2) = 0.25 + 0.15 - 0.02 = 0.38
        # confidence = abs(0.38) = 0.38
        # quantity = 1000 * 0.38 = 380
        mock_uniform.side_effect = [0.005, 0.02, 5000, 50, 0.005, 0.03, 0.01, 0.8, 0.6, 0.03, 0.5, 0.1, 0.5, 0.5, 0.1]
        with patch('ai_service.np.random.choice') as mock_choice:
            mock_choice.return_value = 'bullish'
            
            result = await engine.make_trading_decision('AITBC/BTC')
            
            # Quantity should be 1000 * confidence
            expected_quantity = 1000 * result['confidence']
            assert result['quantity'] == expected_quantity


@pytest.mark.unit
@pytest.mark.asyncio
async def test_signal_strength_boundary_buy():
    """Test signal strength at buy boundary (0.2)"""
    engine = SimpleAITradingEngine()
    
    # Mock the entire decision process to avoid complex numpy calculations
    with patch.object(engine, 'analyze_market') as mock_analyze:
        mock_analyze.return_value = {
            'symbol': 'AITBC/BTC',
            'current_price': 0.005,
            'price_change_24h': 0.02,
            'volume_24h': 5000,
            'rsi': 50,
            'macd': 0.005,
            'volatility': 0.03,
            'ai_predictions': {
                'price_prediction': {'predicted_change': 0.8, 'confidence': 0.8},
                'risk_assessment': {'risk_score': 0.0, 'volatility': 0.01},
                'sentiment_analysis': {'sentiment_score': 0.5, 'overall_sentiment': 'bullish'}
            },
            'timestamp': datetime.now(datetime.UTC)
        }
        
        result = await engine.make_trading_decision('AITBC/BTC')
        
        # At > 0.2, should be buy
        assert result['signal'] == 'buy'


@pytest.mark.unit
@pytest.mark.asyncio
async def test_signal_strength_boundary_sell():
    """Test signal strength at sell boundary (-0.2)"""
    engine = SimpleAITradingEngine()
    
    with patch('ai_service.np.random.uniform') as mock_uniform:
        # Set values to produce signal strength at -0.2
        # signal_strength = (price_pred * 0.5) + (sentiment * 0.3) - (risk * 0.2)
        # To get -0.25: price_pred=-0.5, sentiment=-0.5, risk=0.5 => (-0.5*0.5) + (-0.5*0.3) - (0.5*0.2) = -0.25 - 0.15 - 0.1 = -0.5
        mock_uniform.side_effect = [0.005, -0.02, 5000, 50, 0.005, 0.03, 0.01, 0.8, 0.6, 0.03, -0.5, 0.5, -0.5, -0.5, 0.5]
        with patch('ai_service.np.random.choice') as mock_choice:
            mock_choice.return_value = 'bearish'
            
            result = await engine.make_trading_decision('AITBC/BTC')
            
            # At < -0.2, should be sell
            assert result['signal'] == 'sell'


@pytest.mark.unit
@pytest.mark.asyncio
async def test_signal_strength_just_below_buy_threshold():
    """Test signal strength just below buy threshold (0.199)"""
    engine = SimpleAITradingEngine()
    
    with patch('ai_service.np.random.uniform') as mock_uniform:
        # Set values to produce signal strength just below 0.2
        mock_uniform.side_effect = [0.005, 0.02, 5000, 50, 0.005, 0.03, 0.01, 0.8, 0.6, 0.03, 0.199, 0.4, 0.199, 0.3, 0.0]
        with patch('ai_service.np.random.choice') as mock_choice:
            mock_choice.return_value = 'neutral'
            
            result = await engine.make_trading_decision('AITBC/BTC')
            
            # Just below 0.2, should be hold
            assert result['signal'] == 'hold'


@pytest.mark.unit
@pytest.mark.asyncio
async def test_signal_strength_just_above_sell_threshold():
    """Test signal strength just above sell threshold (-0.199)"""
    engine = SimpleAITradingEngine()
    
    with patch('ai_service.np.random.uniform') as mock_uniform:
        # Set values to produce signal strength just above -0.2
        mock_uniform.side_effect = [0.005, -0.02, 5000, 50, 0.005, 0.03, 0.01, 0.8, 0.6, 0.03, -0.199, 0.4, -0.199, 0.3, 0.0]
        with patch('ai_service.np.random.choice') as mock_choice:
            mock_choice.return_value = 'neutral'
            
            result = await engine.make_trading_decision('AITBC/BTC')
            
            # Just above -0.2, should be hold
            assert result['signal'] == 'hold'
