"""#2718: POST /v1/agents/{wallet}/performance was unreachable.

``get_current_user_required`` hard-coded ``is_oracle: False`` for every
caller, so the oracle gate answered 403 even for admins. Oracle status
now resolves from the caller's role (admin).
"""

from __future__ import annotations

import pytest
from aitbc.auth import create_access_token

from coordinator_api.contexts.infrastructure.domain.user import User, Wallet
from coordinator_api.contexts.staking.routers import staking as staking_router
from coordinator_api.main import app

pytestmark = pytest.mark.unit

AGENT_WALLET = "0x" + "ab" * 20


class _FakeBlockchainService:
    async def update_agent_performance(self, *_args, **_kwargs):
        return None


class _FakeStakingService:
    def update_agent_performance(self, **_kwargs):
        return None


@pytest.fixture
def _service_overrides():
    app.dependency_overrides[staking_router.get_blockchain_service] = lambda: _FakeBlockchainService()
    app.dependency_overrides[staking_router.get_staking_service] = lambda: _FakeStakingService()
    yield
    for dep in (staking_router.get_blockchain_service, staking_router.get_staking_service):
        app.dependency_overrides.pop(dep, None)


@pytest.fixture
def _users(db_session):
    db_session.add(User(id="oracle-admin", email="oa@aitbc.local", username="oracle-admin"))
    db_session.add(Wallet(user_id="oracle-admin", address="0x" + "11" * 20))
    db_session.add(User(id="plain-user", email="pu@aitbc.local", username="plain-user"))
    db_session.add(Wallet(user_id="plain-user", address="0x" + "22" * 20))
    db_session.commit()


def _headers(user_id: str, role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user_id, role)}"}


def _body() -> dict:
    return {"agent_wallet": AGENT_WALLET, "accuracy": "95.5", "successful": True}


def test_admin_role_passes_oracle_gate(client, _service_overrides, _users) -> None:
    response = client.post(
        f"/v1/agents/{AGENT_WALLET}/performance",
        json=_body(),
        headers=_headers("oracle-admin", "admin"),
    )
    assert response.status_code == 200
    assert response.json()["message"] == "Agent performance updated successfully"


def test_non_admin_role_still_403(client, _service_overrides, _users) -> None:
    response = client.post(
        f"/v1/agents/{AGENT_WALLET}/performance",
        json=_body(),
        headers=_headers("plain-user", "client"),
    )
    assert response.status_code == 403
