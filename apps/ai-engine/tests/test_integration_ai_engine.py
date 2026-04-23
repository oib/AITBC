"""Integration tests for AI engine service"""

import pytest
import sys
import sys
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock
from fastapi.testclient import TestClient


# Mock numpy before importing
sys.modules['numpy'] = MagicMock()

from ai_service import app, ai_engine


@pytest.mark.integration
def test_analyze_market_endpoint():
    """Test /api/ai/analyze endpoint"""
    client = TestClient(app)
    
    with patch('ai_service.np.random.uniform') as mock_uniform:
        mock_uniform.side_effect = [0.005, 0.02, 5000, 50, 0.005, 0.03, 0.01, 0.8, 0.6, 0.03, 0.5, 0.4]
        with patch('ai_service.np.random.choice') as mock_choice:
            mock_choice.return_value = 'bullish'
            
            response = client.post("/api/ai/analyze", json={"symbol": "AITBC/BTC", "analysis_type": "full"})
            
            assert response.status_code == 200
            data = response.json()
            assert data['status'] == 'success'
            assert 'analysis' in data
            assert data['analysis']['symbol'] == 'AITBC/BTC'


@pytest.mark.integration
def test_execute_ai_trade_endpoint():
    """Test /api/ai/trade endpoint"""
    client = TestClient(app)
    
    with patch('ai_service.np.random.uniform') as mock_uniform:
        mock_uniform.side_effect = [0.005, 0.02, 5000, 50, 0.005, 0.03, 0.01, 0.8, 0.6, 0.03, 0.5, 0.4, 0.5, 0.3, 0.1]
        with patch('ai_service.np.random.choice') as mock_choice:
            mock_choice.return_value = 'bullish'
            
            response = client.post("/api/ai/trade", json={"symbol": "AITBC/BTC", "strategy": "ai_enhanced"})
            
            assert response.status_code == 200
            data = response.json()
            assert data['status'] == 'success'
            assert 'decision' in data
            assert data['decision']['symbol'] == 'AITBC/BTC'
            assert 'signal' in data['decision']


@pytest.mark.integration
def test_predict_market_endpoint():
    """Test /api/ai/predict/{symbol} endpoint"""
    client = TestClient(app)
    
    with patch('ai_service.np.random.uniform') as mock_uniform:
        mock_uniform.side_effect = [0.005, 0.02, 5000, 50, 0.005, 0.03, 0.01, 0.8, 0.6, 0.03, 0.5, 0.4]
        with patch('ai_service.np.random.choice') as mock_choice:
            mock_choice.return_value = 'bullish'
            
            response = client.get("/api/ai/predict/AITBC-BTC")
            
            assert response.status_code == 200
            data = response.json()
            assert data['status'] == 'success'
            assert 'predictions' in data
            assert 'price' in data['predictions']
            assert 'risk' in data['predictions']
            assert 'sentiment' in data['predictions']


@pytest.mark.integration
def test_get_ai_dashboard_endpoint():
    """Test /api/ai/dashboard endpoint"""
    client = TestClient(app)
    
    # The dashboard endpoint calls analyze_market and make_trading_decision multiple times
    # Mock the entire ai_engine methods to avoid complex numpy mocking
    with patch.object(ai_engine, 'analyze_market') as mock_analyze, \
         patch.object(ai_engine, 'make_trading_decision') as mock_decision:
        
        mock_analyze.return_value = {
            'symbol': 'AITBC/BTC',
            'current_price': 0.005,
            'price_change_24h': 0.02,
            'volume_24h': 5000,
            'rsi': 50,
            'macd': 0.005,
            'volatility': 0.03,
            'ai_predictions': {
                'price_prediction': {'predicted_change': 0.01, 'confidence': 0.8},
                'risk_assessment': {'risk_score': 0.5, 'volatility': 0.03},
                'sentiment_analysis': {'sentiment_score': 0.5, 'overall_sentiment': 'bullish'}
            },
            'timestamp': datetime.utcnow()
        }
        
        mock_decision.return_value = {
            'symbol': 'AITBC/BTC',
            'signal': 'buy',
            'confidence': 0.5,
            'quantity': 500,
            'price': 0.005,
            'reasoning': 'Test reasoning',
            'timestamp': datetime.utcnow()
        }
        
        response = client.get("/api/ai/dashboard")
        
        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'success'
        assert 'dashboard' in data
        assert 'market_overview' in data['dashboard']
        assert 'symbol_analysis' in data['dashboard']
        assert len(data['dashboard']['symbol_analysis']) == 3


@pytest.mark.integration
def test_get_ai_status_endpoint():
    """Test /api/ai/status endpoint"""
    client = TestClient(app)
    
    response = client.get("/api/ai/status")
    
    assert response.status_code == 200
    data = response.json()
    assert data['status'] == 'active'
    assert data['models_loaded'] is True
    assert 'services' in data
    assert 'capabilities' in data
    assert 'trading_engine' in data['services']
    assert 'market_analysis' in data['services']


@pytest.mark.integration
def test_health_check_endpoint():
    """Test /api/health endpoint"""
    client = TestClient(app)
    
    response = client.get("/api/health")
    
    assert response.status_code == 200
    data = response.json()
    assert data['status'] == 'ok'


@pytest.mark.integration
def test_analyze_market_with_default_strategy():
    """Test analyze endpoint with default strategy"""
    client = TestClient(app)
    
    with patch('ai_service.np.random.uniform') as mock_uniform:
        mock_uniform.side_effect = [0.005, 0.02, 5000, 50, 0.005, 0.03, 0.01, 0.8, 0.6, 0.03, 0.5, 0.4]
        with patch('ai_service.np.random.choice') as mock_choice:
            mock_choice.return_value = 'bullish'
            
            response = client.post("/api/ai/analyze", json={"symbol": "AITBC/ETH"})
            
            assert response.status_code == 200
            data = response.json()
            assert data['status'] == 'success'


@pytest.mark.integration
def test_trade_endpoint_with_default_strategy():
    """Test trade endpoint with default strategy"""
    client = TestClient(app)
    
    with patch('ai_service.np.random.uniform') as mock_uniform:
        mock_uniform.side_effect = [0.005, 0.02, 5000, 50, 0.005, 0.03, 0.01, 0.8, 0.6, 0.03, 0.5, 0.4, 0.5, 0.3, 0.1]
        with patch('ai_service.np.random.choice') as mock_choice:
            mock_choice.return_value = 'bullish'
            
            response = client.post("/api/ai/trade", json={"symbol": "AITBC/USDT"})
            
            assert response.status_code == 200
            data = response.json()
            assert data['status'] == 'success'
