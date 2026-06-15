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
        response = client.get("/ipfs/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ["healthy", "degraded"]

    def test_upload_text(self, client: TestClient):
        """Test uploading text to IPFS"""
        response = client.post("/ipfs/upload/text", data={"content": "Hello IPFS!", "filename": "test.txt"})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "cid" in data
        assert data["filename"] == "test.txt"
        assert data["size"] > 0

    def test_upload_text_empty(self, client: TestClient):
        """Test uploading empty text fails"""
        response = client.post("/ipfs/upload/text", data={"content": "", "filename": "empty.txt"})
        assert response.status_code == 400

    def test_get_content(self, client: TestClient):
        """Test retrieving content by CID"""
        # First upload content
        upload_response = client.post(
            "/ipfs/upload/text", data={"content": "Test content for retrieval", "filename": "retrieve.txt"}
        )
        cid = upload_response.json()["cid"]

        # Retrieve it
        response = client.get(f"/ipfs/content/{cid}")
        assert response.status_code == 200
        data = response.json()
        assert data["cid"] == cid
        assert "content" in data or "gateway_url" in data

    def test_get_content_invalid_cid(self, client: TestClient):
        """Test retrieving with invalid CID"""
        response = client.get("/ipfs/content/invalid-cid-format")
        # Should either return error or try to fetch and fail gracefully
        assert response.status_code in [400, 404, 500]

    def test_pin_content(self, client: TestClient):
        """Test pinning content"""
        # Upload first
        upload_response = client.post("/ipfs/upload/text", data={"content": "Content to pin", "filename": "pin.txt"})
        cid = upload_response.json()["cid"]

        # Pin it
        response = client.post(f"/ipfs/pin/{cid}")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["cid"] == cid
        assert data["pinned"] is True

    def test_unpin_content(self, client: TestClient):
        """Test unpinning content"""
        # Upload and pin first
        upload_response = client.post("/ipfs/upload/text", data={"content": "Content to unpin", "filename": "unpin.txt"})
        cid = upload_response.json()["cid"]
        client.post(f"/ipfs/pin/{cid}")

        # Unpin it
        response = client.post(f"/ipfs/unpin/{cid}")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["cid"] == cid
        assert data["pinned"] is False

    def test_list_pins(self, client: TestClient):
        """Test listing pinned content"""
        response = client.get("/ipfs/pins")
        assert response.status_code == 200
        data = response.json()
        assert "pins" in data
        assert "count" in data

    def test_get_gateway_url(self, client: TestClient):
        """Test getting gateway URL for CID"""
        response = client.get("/ipfs/gateway/QmTest123")
        assert response.status_code == 200
        data = response.json()
        assert "cid" in data
        assert "gateway_url" in data
        assert "https://" in data["gateway_url"] or "http://" in data["gateway_url"]


@pytest.mark.integration
class TestIPFSIntegration:
    """Integration tests for IPFS workflow"""

    def test_full_ipfs_workflow(self, client: TestClient):
        """Test complete upload-pin-retrieve workflow"""
        # 1. Upload content
        upload_response = client.post(
            "/ipfs/upload/text", data={"content": "Integration test content", "filename": "integration.txt"}
        )
        assert upload_response.status_code == 200
        cid = upload_response.json()["cid"]

        # 2. Pin the content
        pin_response = client.post(f"/ipfs/pin/{cid}")
        assert pin_response.status_code == 200

        # 3. Verify it's in pins list
        pins_response = client.get("/ipfs/pins")
        assert pins_response.status_code == 200
        pinned_cids = [p["cid"] for p in pins_response.json()["pins"]]
        assert cid in pinned_cids

        # 4. Get gateway URL
        gateway_response = client.get(f"/ipfs/gateway/{cid}")
        assert gateway_response.status_code == 200
        assert "gateway_url" in gateway_response.json()

        # 5. Unpin
        unpin_response = client.post(f"/ipfs/unpin/{cid}")
        assert unpin_response.status_code == 200
