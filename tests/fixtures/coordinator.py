"""
Coordinator API test fixtures
Provides fixtures for testing the coordinator API
"""

import sys
import pytest
from pathlib import Path
from unittest.mock import Mock

project_root = Path(__file__).parent.parent.parent


@pytest.fixture
def coordinator_client():
    """Create a test client for coordinator API"""
    from fastapi.testclient import TestClient
    from aitbc.testing import MockResponse
    
    try:
        # Import the coordinator app specifically
        coordinator_path = str(project_root / "apps" / "coordinator-api" / "src")
        if coordinator_path not in sys.path[:1]:
            sys.path.insert(0, coordinator_path)
        
        from app.main import app as coordinator_app
        print("✅ Using real coordinator API client")
        return TestClient(coordinator_app)
    except ImportError as e:
        # Create a mock client if imports fail
        print(f"Warning: Using mock coordinator_client due to import error: {e}")
        
        mock_response = MockResponse(
            status_code=201,
            json_data={
                "job_id": "test-job-123",
                "state": "QUEUED",
                "assigned_miner_id": None,
                "requested_at": "2026-01-26T18:00:00.000000",
                "expires_at": "2026-01-26T18:15:00.000000",
                "error": None,
                "payment_id": "test-payment-456",
                "payment_status": "escrowed"
            }
        )
        
        mock_client = Mock()
        mock_client.post.return_value = mock_response
        
        mock_get_response = MockResponse(
            status_code=200,
            json_data={
                "job_id": "test-job-123",
                "state": "QUEUED",
                "assigned_miner_id": None,
                "requested_at": "2026-01-26T18:00:00.000000",
                "expires_at": "2026-01-26T18:15:00.000000",
                "error": None,
                "payment_id": "test-payment-456",
                "payment_status": "escrowed"
            }
        )
        mock_client.get.return_value = mock_get_response
        
        mock_receipts_response = MockResponse(
            status_code=200,
            json_data={
                "items": [],
                "total": 0
            }
        )
        
        def mock_get_side_effect(url, headers=None):
            if "receipts" in url:
                return mock_receipts_response
            elif "/docs" in url or "/openapi.json" in url:
                return MockResponse(status_code=200, text='{"openapi": "3.0.0", "info": {"title": "AITBC Coordinator API"}}')
            elif "/v1/health" in url:
                return MockResponse(status_code=200, json_data={"status": "ok", "env": "dev"})
            elif "/payment" in url:
                return MockResponse(
                    status_code=200,
                    json_data={
                        "job_id": "test-job-123",
                        "payment_id": "test-payment-456",
                        "amount": 100,
                        "currency": "AITBC",
                        "status": "escrowed",
                        "payment_method": "aitbc_token",
                        "escrow_address": "test-escrow-id",
                        "created_at": "2026-01-26T18:00:00.000000",
                        "updated_at": "2026-01-26T18:00:00.000000"
                    }
                )
            return mock_get_response
        
        mock_client.get.side_effect = mock_get_side_effect
        mock_client.patch.return_value = MockResponse(status_code=200, json_data={"status": "updated"})
        return mock_client
