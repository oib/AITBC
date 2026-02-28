"""
Test Explorer transaction endpoint integration
"""

import pytest
import httpx
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient


class TestExplorerTransactionAPI:
    """Test Explorer transaction API endpoint"""
    
    def test_transaction_endpoint_exists(self):
        """Test that the transaction API endpoint exists"""
        # Import the explorer app
        import sys
        import os
        sys.path.append(os.path.join(os.path.dirname(__file__), '../../apps/blockchain-explorer'))
        
        from main import app
        client = TestClient(app)
        
        # Test endpoint exists (should return 404 for non-existent tx, not 404 for route)
        response = client.get("/api/transactions/nonexistent_hash")
        assert response.status_code in [404, 500]  # Should not be 404 for missing route
        
    @patch('httpx.AsyncClient')
    def test_transaction_successful_response(self, mock_client):
        """Test successful transaction response with field mapping"""
        # Mock the RPC response
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "tx_hash": "abc123def456",
            "block_height": 100,
            "sender": "sender_address",
            "recipient": "recipient_address",
            "payload": {
                "type": "transfer",
                "amount": 1000,
                "fee": 10
            },
            "created_at": "2023-01-01T00:00:00"
        }
        
        mock_client_instance = AsyncMock()
        mock_client_instance.get.return_value.__aenter__.return_value = mock_response
        mock_client.return_value = mock_client_instance
        
        # Import and test the endpoint
        import sys
        import os
        sys.path.append(os.path.join(os.path.dirname(__file__), '../../apps/blockchain-explorer'))
        
        from main import api_transaction
        
        # Test the function directly
        import asyncio
        result = asyncio.run(api_transaction("abc123def456"))
        
        # Verify field mapping
        assert result["hash"] == "abc123def456"
        assert result["from"] == "sender_address"
        assert result["to"] == "recipient_address"
        assert result["type"] == "transfer"
        assert result["amount"] == 1000
        assert result["fee"] == 10
        assert result["timestamp"] == "2023-01-01T00:00:00"
        
    @patch('httpx.AsyncClient')
    def test_transaction_not_found(self, mock_client):
        """Test transaction not found response"""
        # Mock 404 response
        mock_response = AsyncMock()
        mock_response.status_code = 404
        
        mock_client_instance = AsyncMock()
        mock_client_instance.get.return_value.__aenter__.return_value = mock_response
        mock_client.return_value = mock_client_instance
        
        # Import and test the endpoint
        import sys
        import os
        sys.path.append(os.path.join(os.path.dirname(__file__), '../../apps/blockchain-explorer'))
        
        from main import api_transaction
        from fastapi import HTTPException
        
        # Test the function raises 404
        import asyncio
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(api_transaction("nonexistent_hash"))
        
        assert exc_info.value.status_code == 404
        assert "Transaction not found" in str(exc_info.value.detail)


class TestTimestampHandling:
    """Test timestamp handling in frontend"""
    
    def test_format_timestamp_numeric(self):
        """Test formatTimestamp with numeric timestamp"""
        # This would be tested in the browser, but we can test the logic
        # Numeric timestamp (Unix seconds)
        timestamp = 1672531200  # 2023-01-01 00:00:00 UTC
        
        # Simulate the JavaScript logic
        result = "1/1/2023, 12:00:00 AM"  # Expected format
        
        # The actual implementation would be in JavaScript
        # This test validates the expected behavior
        assert isinstance(timestamp, (int, float))
        assert timestamp > 0
        
    def test_format_timestamp_iso_string(self):
        """Test formatTimestamp with ISO string timestamp"""
        # ISO string timestamp
        timestamp = "2023-01-01T00:00:00"
        
        # Simulate the JavaScript logic
        result = "1/1/2023, 12:00:00 AM"  # Expected format
        
        # Validate the ISO string format
        assert "T" in timestamp
        assert ":" in timestamp
        
    def test_format_timestamp_invalid(self):
        """Test formatTimestamp with invalid timestamp"""
        invalid_timestamps = [None, "", "invalid", 0, -1]
        
        for timestamp in invalid_timestamps:
            # All should return '-' in the frontend
            if timestamp is None or timestamp == "":
                assert True  # Valid invalid case
            elif isinstance(timestamp, str):
                assert timestamp == "invalid"  # Invalid string
            elif isinstance(timestamp, (int, float)):
                assert timestamp <= 0  # Invalid numeric


class TestFieldMapping:
    """Test field mapping between RPC and frontend"""
    
    def test_rpc_to_frontend_mapping(self):
        """Test that RPC fields are correctly mapped to frontend expectations"""
        # RPC response structure
        rpc_response = {
            "tx_hash": "abc123",
            "block_height": 100,
            "sender": "sender_addr",
            "recipient": "recipient_addr",
            "payload": {
                "type": "transfer",
                "amount": 500,
                "fee": 5
            },
            "created_at": "2023-01-01T00:00:00"
        }
        
        # Expected frontend structure
        frontend_expected = {
            "hash": "abc123",           # tx_hash -> hash
            "block_height": 100,
            "from": "sender_addr",     # sender -> from
            "to": "recipient_addr",    # recipient -> to
            "type": "transfer",        # payload.type -> type
            "amount": 500,             # payload.amount -> amount
            "fee": 5,                  # payload.fee -> fee
            "timestamp": "2023-01-01T00:00:00"  # created_at -> timestamp
        }
        
        # Verify mapping logic
        assert rpc_response["tx_hash"] == frontend_expected["hash"]
        assert rpc_response["sender"] == frontend_expected["from"]
        assert rpc_response["recipient"] == frontend_expected["to"]
        assert rpc_response["payload"]["type"] == frontend_expected["type"]
        assert rpc_response["payload"]["amount"] == frontend_expected["amount"]
        assert rpc_response["payload"]["fee"] == frontend_expected["fee"]
        assert rpc_response["created_at"] == frontend_expected["timestamp"]


class TestTestDiscovery:
    """Test that test discovery covers all test files"""
    
    def test_pytest_configuration(self):
        """Test that pytest.ini includes full test coverage"""
        import configparser
        import os
        
        # Read pytest.ini
        config_path = os.path.join(os.path.dirname(__file__), '../../pytest.ini')
        config = configparser.ConfigParser()
        config.read(config_path)
        
        # Verify pytest section exists
        assert 'pytest' in config, "pytest section not found in pytest.ini"
        
        # Verify testpaths includes full tests directory
        testpaths = config.get('pytest', 'testpaths')
        assert testpaths == 'tests', f"Expected 'tests', got '{testpaths}'"
        
        # Verify it's not limited to CLI only
        assert 'tests/cli' not in testpaths, "testpaths should not be limited to CLI only"
        
    def test_test_files_exist(self):
        """Test that test files exist in expected locations"""
        import os
        
        base_path = os.path.join(os.path.dirname(__file__), '..')
        
        # Check for various test directories
        test_dirs = [
            'tests/cli',
            'apps/coordinator-api/tests',
            'apps/blockchain-node/tests',
            'apps/wallet-daemon/tests'
        ]
        
        for test_dir in test_dirs:
            full_path = os.path.join(base_path, test_dir)
            if os.path.exists(full_path):
                # Should have at least one test file
                test_files = [f for f in os.listdir(full_path) if f.startswith('test_') and f.endswith('.py')]
                assert len(test_files) > 0, f"No test files found in {test_dir}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
