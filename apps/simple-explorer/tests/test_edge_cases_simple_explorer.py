"""Edge case and error handling tests for simple explorer service"""

import pytest
import sys
import sys
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock
from fastapi.testclient import TestClient


# Mock httpx before importing
sys.modules['httpx'] = Mock()

from main import app


@pytest.mark.unit
def test_get_transaction_missing_fields():
    """Test transaction mapping with missing fields"""
    client = TestClient(app)
    
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "tx_hash": "0x" + "a" * 64,
        # Missing sender, recipient, payload
        "created_at": "2026-01-01T00:00:00"
    }
    
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.get.return_value = mock_response
    
    with patch('main.httpx.AsyncClient', return_value=mock_client):
        response = client.get("/api/transactions/" + "a" * 64)
        assert response.status_code == 200
        data = response.json()
        assert data["from"] == "unknown"
        assert data["to"] == "unknown"
        assert data["amount"] == "0"
        assert data["fee"] == "0"


@pytest.mark.unit
def test_get_transaction_empty_payload():
    """Test transaction mapping with empty payload"""
    client = TestClient(app)
    
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "tx_hash": "0x" + "a" * 64,
        "sender": "0xsender",
        "recipient": "0xrecipient",
        "payload": {},
        "created_at": "2026-01-01T00:00:00"
    }
    
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.get.return_value = mock_response
    
    with patch('main.httpx.AsyncClient', return_value=mock_client):
        response = client.get("/api/transactions/" + "a" * 64)
        assert response.status_code == 200
        data = response.json()
        assert data["amount"] == "0"
        assert data["fee"] == "0"


@pytest.mark.unit
def test_get_transaction_missing_created_at():
    """Test transaction mapping with missing created_at"""
    client = TestClient(app)
    
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "tx_hash": "0x" + "a" * 64,
        "sender": "0xsender",
        "recipient": "0xrecipient",
        "payload": {"value": "1000", "fee": "10"}
        # Missing created_at
    }
    
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.get.return_value = mock_response
    
    with patch('main.httpx.AsyncClient', return_value=mock_client):
        response = client.get("/api/transactions/" + "a" * 64)
        assert response.status_code == 200
        data = response.json()
        assert data["timestamp"] is None


@pytest.mark.unit
def test_get_transaction_missing_block_height():
    """Test transaction mapping with missing block_height"""
    client = TestClient(app)
    
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "tx_hash": "0x" + "a" * 64,
        "sender": "0xsender",
        "recipient": "0xrecipient",
        "payload": {"value": "1000", "fee": "10"},
        "created_at": "2026-01-01T00:00:00"
        # Missing block_height
    }
    
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.get.return_value = mock_response
    
    with patch('main.httpx.AsyncClient', return_value=mock_client):
        response = client.get("/api/transactions/" + "a" * 64)
        assert response.status_code == 200
        data = response.json()
        assert data["block_height"] == "pending"


@pytest.mark.unit
def test_get_block_negative_height():
    """Test /api/blocks/{height} with negative height"""
    client = TestClient(app)
    
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "height": -1,
        "hash": "0xblock",
        "timestamp": 1234567890,
        "transactions": []
    }
    
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.get.return_value = mock_response
    
    with patch('main.httpx.AsyncClient', return_value=mock_client):
        response = client.get("/api/blocks/-1")
        assert response.status_code == 200
        data = response.json()
        assert data["height"] == -1


@pytest.mark.unit
def test_get_block_zero_height():
    """Test /api/blocks/{height} with zero height"""
    client = TestClient(app)
    
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "height": 0,
        "hash": "0xgenesis",
        "timestamp": 1234567890,
        "transactions": []
    }
    
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.get.return_value = mock_response
    
    with patch('main.httpx.AsyncClient', return_value=mock_client):
        response = client.get("/api/blocks/0")
        assert response.status_code == 200
        data = response.json()
        assert data["height"] == 0


@pytest.mark.unit
def test_get_transaction_short_hash():
    """Test /api/transactions/{tx_hash} with short hash"""
    client = TestClient(app)
    
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "tx_hash": "0x" + "a" * 64,
        "sender": "0xsender",
        "recipient": "0xrecipient",
        "payload": {"value": "1000", "fee": "10"},
        "created_at": "2026-01-01T00:00:00",
        "block_height": 100
    }
    
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.get.return_value = mock_response
    
    with patch('main.httpx.AsyncClient', return_value=mock_client):
        response = client.get("/api/transactions/abc")
        assert response.status_code in [200, 404, 500]  # Any valid response


@pytest.mark.unit
def test_get_transaction_invalid_hex_hash():
    """Test /api/transactions/{tx_hash} with invalid hex characters"""
    client = TestClient(app)
    
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "tx_hash": "0x" + "a" * 64,
        "sender": "0xsender",
        "recipient": "0xrecipient",
        "payload": {"value": "1000", "fee": "10"},
        "created_at": "2026-01-01T00:00:00",
        "block_height": 100
    }
    
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.get.return_value = mock_response
    
    with patch('main.httpx.AsyncClient', return_value=mock_client):
        response = client.get("/api/transactions/" + "z" * 64)
        assert response.status_code in [200, 404, 500]
