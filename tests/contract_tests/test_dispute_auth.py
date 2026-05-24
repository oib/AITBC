"""
Negative authentication tests for dispute endpoints.
Tests for missing authentication, unauthorized access, and invalid tokens.
"""

import pytest
import os
import sys
from pathlib import Path
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from fastapi import status

repo_root = Path(__file__).resolve().parents[2]
blockchain_src = repo_root / "apps" / "blockchain-node" / "src"
if str(blockchain_src) not in sys.path:
    sys.path.insert(0, str(blockchain_src))


@pytest.mark.asyncio
class TestDisputeAuthentication:
    """Test authentication requirements for dispute endpoints"""
    
    @pytest_asyncio.fixture
    async def client(self):
        """Create test client for blockchain node RPC"""
        from aitbc_chain.rpc.router import router
        from fastapi import FastAPI
        
        app = FastAPI()
        app.include_router(router, prefix="/rpc")
        
        # Set DEV_MODE to false for production-like testing
        original_dev_mode = os.getenv("DEV_MODE")
        original_trust_header = os.getenv("TRUST_X_WALLET_ADDRESS")
        os.environ["DEV_MODE"] = "false"
        os.environ["TRUST_X_WALLET_ADDRESS"] = "false"
        
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
                "agreement_id": 1,
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
                "agreement_id": 1,
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
        os.environ["TRUST_X_WALLET_ADDRESS"] = "true"
        response = await client.post(
            "/rpc/disputes/file",
            json={
                "agreement_id": 1,
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

    async def test_valid_wallet_address_header_is_not_trusted_by_default(self, client):
        """Test that filing a dispute with an untrusted wallet address header returns 401"""
        response = await client.post(
            "/rpc/disputes/file",
            json={
                "agreement_id": 1,
                "respondent": "0x1234567890123456789012345678901234567890",
                "dispute_type": "payment_dispute",
                "reason": "Test dispute",
                "evidence_hash": "0xabcdef"
            },
            headers={"X-Wallet-Address": "0x1234567890123456789012345678901234567890"}
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "not trusted" in response.json()["detail"]

    async def test_jwt_token_not_configured(self, client):
        """Test that JWT token authentication fails closed with clear error"""
        response = await client.post(
            "/rpc/disputes/file",
            json={
                "agreement_id": 1,
                "respondent": "0x1234567890123456789012345678901234567890",
                "dispute_type": "payment_dispute",
                "reason": "Test dispute",
                "evidence_hash": "0xabcdef"
            },
            headers={"Authorization": "Bearer test_token"}
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "JWT authentication is not supported" in response.json()["detail"]


@pytest.mark.asyncio
class TestDisputeAuthDevMode:
    """Test authentication behavior in development mode"""
    
    @pytest_asyncio.fixture
    async def dev_client(self):
        """Create test client with DEV_MODE enabled"""
        from aitbc_chain.rpc.router import router
        from fastapi import FastAPI
        
        app = FastAPI()
        app.include_router(router, prefix="/rpc")
        
        # Set DEV_MODE to true
        original_dev_mode = os.getenv("DEV_MODE")
        original_trust_header = os.getenv("TRUST_X_WALLET_ADDRESS")
        os.environ["DEV_MODE"] = "true"
        os.environ["TRUST_X_WALLET_ADDRESS"] = "false"
        
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
        
        # Restore original DEV_MODE
        if original_dev_mode is None:
            os.environ.pop("DEV_MODE", None)
        else:
            os.environ["DEV_MODE"] = original_dev_mode
    
    async def test_file_dispute_dev_mode_fails_closed(self, dev_client):
        """Test that dev mode no longer uses a zero address fallback"""
        response = await dev_client.post(
            "/rpc/disputes/file",
            json={
                "agreement_id": 1,
                "respondent": "0x1234567890123456789012345678901234567890",
                "dispute_type": "payment_dispute",
                "reason": "Test dispute",
                "evidence_hash": "0xabcdef"
            }
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Authentication required" in response.json()["detail"]

    async def test_arbitration_vote_zero_address_rejected(self, dev_client):
        """Test that zero address is rejected in arbitration vote submission"""
        os.environ["TRUST_X_WALLET_ADDRESS"] = "true"
        response = await dev_client.post(
            "/rpc/disputes/vote",
            json={
                "dispute_id": 1,
                "vote_in_favor_of_initiator": True,
                "confidence": 90,
                "reasoning": "Test reasoning"
            },
            headers={"X-Wallet-Address": "0x0000000000000000000000000000000000000000"}
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Zero address is not allowed" in response.json()["detail"]
