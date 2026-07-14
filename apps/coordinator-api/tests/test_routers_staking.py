"""
Tests for staking router
"""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def wallet():
    """Create a test user and wallet for staking auth tests."""
    from coordinator_api.contexts.infrastructure.domain.user import User, Wallet
    from coordinator_api.storage.db import get_engine
    from sqlmodel import Session, SQLModel

    engine = get_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        user = session.get(User, "test-admin")
        if not user:
            user = User(id="test-admin", email="test-admin@example.com", username="test-admin")
            session.add(user)
            wallet = Wallet(user_id="test-admin", address="0x" + "1" * 40, balance=0.0)
            session.add(wallet)
            session.commit()
    yield "0x" + "1" * 40


@pytest.mark.unit
class TestStakingRouter:
    """Test staking router endpoints"""

    def test_get_stake_requires_auth(self, client: TestClient):
        """Missing token should return 401."""
        response = client.get("/v1/stake/not-found")
        assert response.status_code == 401

    def test_get_stakes_uses_real_address(self, client: TestClient, wallet: str, admin_token: str):
        """Valid token with a linked wallet should pass auth and use the wallet address."""
        response = client.get(
            "/v1/stakes",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        assert response.json() == []
