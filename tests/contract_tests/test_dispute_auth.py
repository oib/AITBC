"""Negative authentication tests for dispute endpoints.
Tests for missing authentication, unauthorized access, and invalid tokens.

#3052 (AUDIT-DISPUTE-AUTH-HEADER-1): the dispute mutations no longer accept a
bare ``X-Wallet-Address`` header — not even with ``TRUST_X_WALLET_ADDRESS=true``.
They require a wallet signature over the request; these tests pin the reject
side (missing/malformed/unsigned/bad-proof) at the HTTP layer. The accept side
and replay guard live in ``apps/blockchain-node/tests/test_dispute_signed_auth_3052.py``.
"""

import os

import pytest
import pytest_asyncio
from fastapi import status
from httpx import ASGITransport, AsyncClient

FILE_BODY = {
    "agreement_id": 1,
    "respondent": "0x1234567890123456789012345678901234567890",
    "dispute_type": "Payment",
    "reason": "Test dispute",
    "evidence_hash": "0xabcdef",
}


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
        os.getenv("TRUST_X_WALLET_ADDRESS")
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
        response = await client.post("/rpc/disputes/file", json=FILE_BODY)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Authentication required" in response.json()["detail"]

    async def test_file_dispute_with_invalid_wallet_address(self, client):
        """Test that filing a dispute with invalid wallet address format returns 401"""
        response = await client.post(
            "/rpc/disputes/file",
            json=FILE_BODY,
            headers={"X-Wallet-Address": "invalid_address_format"},
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Invalid wallet address format" in response.json()["detail"]

    async def test_submit_evidence_missing_auth(self, client):
        """Test that submitting evidence without authentication returns 401"""
        response = await client.post(
            "/rpc/disputes/evidence",
            json={
                "dispute_id": 1,
                "evidence_hash": "0xabcdef",
                "evidence_type": "transaction_proof",
                "description": "Test evidence",
            },
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Authentication required" in response.json()["detail"]

    async def test_verify_evidence_missing_auth(self, client):
        """Test that verifying evidence without authentication returns 401"""
        response = await client.post(
            "/rpc/disputes/verify-evidence", json={"dispute_id": 1, "evidence_id": 1, "verified": True}
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Authentication required" in response.json()["detail"]

    async def test_authorize_arbitrator_missing_auth(self, client):
        """Test that authorizing an arbitrator without authentication returns 401"""
        response = await client.post(
            "/rpc/disputes/arbitrators/authorize",
            json={"arbitrator_address": "0x1234567890123456789012345678901234567890", "authorized": True},
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Authentication required" in response.json()["detail"]

    async def test_submit_vote_missing_auth(self, client):
        """Test that submitting a vote without authentication returns 401"""
        response = await client.post(
            "/rpc/disputes/vote", json={"dispute_id": 1, "vote": "plaintiff", "reasoning": "Test reasoning"}
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Authentication required" in response.json()["detail"]

    async def test_bare_wallet_header_is_not_a_credential(self, client):
        """#3052: TRUST_X_WALLET_ADDRESS=true no longer authorizes dispute writes.

        The header is only the claimed-identity hint; without a signature the
        request dies at 401 even though the trust flag and a loopback-looking
        test client would previously have passed.
        """
        os.environ["TRUST_X_WALLET_ADDRESS"] = "true"
        response = await client.post(
            "/rpc/disputes/file",
            json=FILE_BODY,
            headers={"X-Wallet-Address": "0x1234567890123456789012345678901234567890"},
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "signature" in response.json()["detail"].lower()

    async def test_valid_wallet_address_header_still_requires_signature(self, client):
        """A well-formed header alone never authenticates, flag on or off."""
        for flag in ("false", "true"):
            os.environ["TRUST_X_WALLET_ADDRESS"] = flag
            response = await client.post(
                "/rpc/disputes/file",
                json=FILE_BODY,
                headers={"X-Wallet-Address": "0x1234567890123456789012345678901234567890"},
            )
            assert response.status_code == status.HTTP_401_UNAUTHORIZED, flag

    async def test_jwt_token_not_configured(self, client):
        """Test that JWT token authentication fails closed with clear error"""
        response = await client.post(
            "/rpc/disputes/file",
            json=FILE_BODY,
            headers={"Authorization": "Bearer test_token"},
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Authentication required" in response.json()["detail"]


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
        os.getenv("TRUST_X_WALLET_ADDRESS")
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
        response = await dev_client.post("/rpc/disputes/file", json=FILE_BODY)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Authentication required" in response.json()["detail"]

    async def test_zero_address_claim_rejected_without_signature(self, dev_client):
        """#3052: the zero address cannot authenticate — no key exists to sign.

        Previously the bare-header path let the claim through to the route's
        explicit zero-address guard; now it dies earlier at the signature
        requirement, which is strictly stronger.
        """
        os.environ["TRUST_X_WALLET_ADDRESS"] = "true"
        response = await dev_client.post(
            "/rpc/disputes/vote",
            json={"dispute_id": 1, "vote": "plaintiff", "reasoning": "Test reasoning"},
            headers={"X-Wallet-Address": "0x0000000000000000000000000000000000000000"},
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "signature" in response.json()["detail"].lower()
