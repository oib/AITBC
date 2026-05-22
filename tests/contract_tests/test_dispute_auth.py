"""
Negative authentication tests for dispute endpoints.
Tests for missing authentication, unauthorized access, and invalid tokens.
"""

import pytest
import os
from httpx import AsyncClient, ASGITransport
from fastapi import status


@pytest.mark.asyncio
class TestDisputeAuthentication:
    """Test authentication requirements for dispute endpoints"""
    
    @pytest.fixture
    async def client(self):
        """Create test client for blockchain node RPC"""
        from apps.blockchain_node.src.aitbc_chain.rpc.router import router
        from fastapi import FastAPI
        
        app = FastAPI()
        app.include_router(router, prefix="/rpc")
        
        # Set DEV_MODE to false for production-like testing
        original_dev_mode = os.getenv("DEV_MODE")
        os.environ["DEV_MODE"] = "false"
        
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
        
        # Restore original DEV_MODE
        if original_dev_mode is None:
            os.environ.pop("DEV_MODE", None)
        else:
            os.environ["DEV_MODE"] = original_dev_mode
    
    async def test_file_dispute_missing_auth(self, client):
        """Test that filing a dispute without authentication returns 401"""
        response = await client.post(
            "/rpc/disputes/file",
            json={
                "agreement_id": "test_agreement_1",
                "respondent": "0x1234567890123456789012345678901234567890",
                "dispute_type": "payment_dispute",
                "reason": "Test dispute",
                "evidence_hash": "0xabcdef"
            }
        )
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Authentication required" in response.json()["detail"]
    
    async def test_file_dispute_with_invalid_wallet_address(self, client):
        """Test that filing a dispute with invalid wallet address format returns 401"""
        response = await client.post(
            "/rpc/disputes/file",
            json={
                "agreement_id": "test_agreement_1",
                "respondent": "0x1234567890123456789012345678901234567890",
                "dispute_type": "payment_dispute",
                "reason": "Test dispute",
                "evidence_hash": "0xabcdef"
            },
            headers={"X-Wallet-Address": "invalid_address_format"}
        )
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Invalid wallet address format" in response.json()["detail"]
    
    async def test_submit_evidence_missing_auth(self, client):
        """Test that submitting evidence without authentication returns 401"""
        response = await client.post(
            "/rpc/disputes/evidence",
            json={
                "dispute_id": 1,
                "evidence_type": "transaction_proof",
                "evidence_data": "test_evidence_data"
            }
        )
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Authentication required" in response.json()["detail"]
    
    async def test_verify_evidence_missing_auth(self, client):
        """Test that verifying evidence without authentication returns 401"""
        response = await client.post(
            "/rpc/disputes/verify-evidence",
            json={
                "dispute_id": 1,
                "evidence_id": 1,
                "is_valid": True,
                "verification_score": 95
            }
        )
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Authentication required" in response.json()["detail"]
    
    async def test_authorize_arbitrator_missing_auth(self, client):
        """Test that authorizing an arbitrator without authentication returns 401"""
        response = await client.post(
            "/rpc/disputes/arbitrators/authorize",
            json={
                "arbitrator": "0x1234567890123456789012345678901234567890",
                "reputation_score": 85
            }
        )
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Authentication required" in response.json()["detail"]
    
    async def test_submit_vote_missing_auth(self, client):
        """Test that submitting a vote without authentication returns 401"""
        response = await client.post(
            "/rpc/disputes/vote",
            json={
                "dispute_id": 1,
                "vote_in_favor_of_initiator": True,
                "confidence": 90,
                "reasoning": "Test reasoning"
            }
        )
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Authentication required" in response.json()["detail"]
    
    async def test_file_dispute_with_valid_wallet_address(self, client):
        """Test that filing a dispute with valid wallet address header succeeds (or returns expected error)"""
        response = await client.post(
            "/rpc/disputes/file",
            json={
                "agreement_id": "test_agreement_1",
                "respondent": "0x1234567890123456789012345678901234567890",
                "dispute_type": "payment_dispute",
                "reason": "Test dispute",
                "evidence_hash": "0xabcdef"
            },
            headers={"X-Wallet-Address": "0x1234567890123456789012345678901234567890"}
        )
        
        # Should not be 401 (authentication passed)
        # May be 500 if dispute service is not available, which is acceptable
        assert response.status_code != status.HTTP_401_UNAUTHORIZED
    
    async def test_jwt_token_not_implemented(self, client):
        """Test that JWT token authentication returns 501 (not yet implemented)"""
        response = await client.post(
            "/rpc/disputes/file",
            json={
                "agreement_id": "test_agreement_1",
                "respondent": "0x1234567890123456789012345678901234567890",
                "dispute_type": "payment_dispute",
                "reason": "Test dispute",
                "evidence_hash": "0xabcdef"
            },
            headers={"Authorization": "Bearer test_token"}
        )
        
        assert response.status_code == status.HTTP_501_NOT_IMPLEMENTED
        assert "JWT authentication not yet implemented" in response.json()["detail"]


@pytest.mark.asyncio
class TestDisputeAuthDevMode:
    """Test authentication behavior in development mode"""
    
    @pytest.fixture
    async def dev_client(self):
        """Create test client with DEV_MODE enabled"""
        from apps.blockchain_node.src.aitbc_chain.rpc.router import router
        from fastapi import FastAPI
        
        app = FastAPI()
        app.include_router(router, prefix="/rpc")
        
        # Set DEV_MODE to true
        original_dev_mode = os.getenv("DEV_MODE")
        os.environ["DEV_MODE"] = "true"
        
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
        
        # Restore original DEV_MODE
        if original_dev_mode is None:
            os.environ.pop("DEV_MODE", None)
        else:
            os.environ["DEV_MODE"] = original_dev_mode
    
    async def test_file_dispute_dev_mode_fallback(self, dev_client):
        """Test that in dev mode, missing auth uses zero address fallback"""
        response = await dev_client.post(
            "/rpc/disputes/file",
            json={
                "agreement_id": "test_agreement_1",
                "respondent": "0x1234567890123456789012345678901234567890",
                "dispute_type": "payment_dispute",
                "reason": "Test dispute",
                "evidence_hash": "0xabcdef"
            }
        )
        
        # In dev mode, should not return 401 (uses zero address fallback)
        # May return 500 if dispute service is not available
        assert response.status_code != status.HTTP_401_UNAUTHORIZED
