"""Integration tests for simple explorer service"""

import pytest
import sys
import sys
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock
from fastapi.testclient import TestClient


# Mock httpx before importing
sys.modules['httpx'] = Mock()

from main import app


@pytest.mark.integration
def test_root_endpoint():
    """Test root endpoint serves HTML"""
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "AITBC Blockchain Explorer" in response.text


@pytest.mark.integration
def test_get_chain_head_success():
    """Test /api/chain/head endpoint with successful response"""
    client = TestClient(app)
    
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"height": 100, "hash": "0xabc123", "timestamp": 1234567890}
    
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.get.return_value = mock_response
    
    with patch('main.httpx.AsyncClient', return_value=mock_client):
        response = client.get("/api/chain/head")
        assert response.status_code == 200
        data = response.json()
        assert data["height"] == 100
        assert data["hash"] == "0xabc123"


@pytest.mark.integration
def test_get_chain_head_error():
    """Test /api/chain/head endpoint with error"""
    client = TestClient(app)
    
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.get.side_effect = Exception("RPC error")
    
    with patch('main.httpx.AsyncClient', return_value=mock_client):
        response = client.get("/api/chain/head")
        assert response.status_code == 200
        data = response.json()
        assert data["height"] == 0
        assert data["hash"] == ""


@pytest.mark.integration
def test_get_block_success():
    """Test /api/blocks/{height} endpoint with successful response"""
    client = TestClient(app)
    
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "height": 50,
        "hash": "0xblock50",
        "timestamp": 1234567890,
        "transactions": []
    }
    
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.get.return_value = mock_response
    
    with patch('main.httpx.AsyncClient', return_value=mock_client):
        response = client.get("/api/blocks/50")
        assert response.status_code == 200
        data = response.json()
        assert data["height"] == 50
        assert data["hash"] == "0xblock50"


@pytest.mark.integration
def test_get_block_error():
    """Test /api/blocks/{height} endpoint with error"""
    client = TestClient(app)
    
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.get.side_effect = Exception("RPC error")
    
    with patch('main.httpx.AsyncClient', return_value=mock_client):
        response = client.get("/api/blocks/50")
        assert response.status_code == 200
        data = response.json()
        assert data["height"] == 50
        assert data["hash"] == ""


@pytest.mark.integration
def test_get_transaction_success():
    """Test /api/transactions/{tx_hash} endpoint with successful response"""
    client = TestClient(app)
    
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "tx_hash": "0x" + "a" * 64,
        "sender": "0xsender",
        "recipient": "0xrecipient",
        "payload": {
            "value": "1000",
            "fee": "10"
        },
        "created_at": "2026-01-01T00:00:00",
        "block_height": 100
    }
    
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.get.return_value = mock_response
    
    with patch('main.httpx.AsyncClient', return_value=mock_client):
        response = client.get("/api/transactions/" + "a" * 64)
        assert response.status_code == 200
        data = response.json()
        assert data["hash"] == "0x" + "a" * 64
        assert data["from"] == "0xsender"
        assert data["to"] == "0xrecipient"
        assert data["amount"] == "1000"
        assert data["fee"] == "10"


@pytest.mark.integration
def test_get_transaction_not_found():
    """Test /api/transactions/{tx_hash} endpoint with 404 response"""
    client = TestClient(app)
    
    mock_response = Mock()
    mock_response.status_code = 404
    
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.get.return_value = mock_response
    
    with patch('main.httpx.AsyncClient', return_value=mock_client):
        response = client.get("/api/transactions/" + "a" * 64)
        assert response.status_code == 404


@pytest.mark.integration
def test_get_transaction_error():
    """Test /api/transactions/{tx_hash} endpoint with error"""
    client = TestClient(app)
    
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.get.side_effect = Exception("RPC error")
    
    with patch('main.httpx.AsyncClient', return_value=mock_client):
        response = client.get("/api/transactions/" + "a" * 64)
        assert response.status_code == 500
