"""
Tests for IPFS router (decentralized storage)
"""

import pytest
from fastapi.testclient import TestClient


@pytest.mark.unit
class TestIPFSRouter:
    """Test IPFS router endpoints"""

    def test_ipfs_health(self, client: TestClient):
        """Test IPFS health endpoint"""
        response = client.get("/v1/ipfs/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["service"] == "ipfs-storage"

    def test_get_content_invalid_cid(self, client: TestClient):
        """Test retrieving with invalid CID"""
        response = client.get("/v1/ipfs/content/invalid-cid-format")
        # Should either return error or try to fetch and fail gracefully
        assert response.status_code in [400, 404, 500]
