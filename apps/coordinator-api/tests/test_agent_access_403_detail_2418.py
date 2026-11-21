"""#2418 pins: agent-ownership 403s must say WHICH check failed.

"not the agent owner" could not distinguish an unregistered agent_id from
a wrong-wallet caller; both helpers now name the failing case.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from coordinator_api.contexts.agent_coordination.routers.agent_performance import _require_agent_access as perf_access
from coordinator_api.contexts.agent_identity.domain.agent_identity import AgentIdentity
from coordinator_api.contexts.infrastructure.domain.user import User, Wallet
from coordinator_api.utils.ownership import require_agent_access

OWNER_WALLET = "0x5555555555555555555555555555555555555555"
OTHER_WALLET = "0x7777777777777777777777777777777777777777"
AGENT = "agent-owned-2418"


@pytest.fixture
def seeded(db_session):
    db_session.add(User(id="owner1", email="o@x", username="owner1"))
    db_session.add(Wallet(user_id="owner1", address=OWNER_WALLET))
    db_session.add(User(id="intruder", email="i@x", username="intruder"))
    db_session.add(Wallet(user_id="intruder", address=OTHER_WALLET))
    db_session.add(AgentIdentity(agent_id=AGENT, owner_address=OWNER_WALLET))
    db_session.commit()
    return db_session


def _user(sub: str, role: str = "client") -> dict:
    return {"sub": sub, "role": role}


class TestOwnership403Detail:
    def test_missing_identity_names_agent_id(self, seeded):
        with pytest.raises(HTTPException) as exc:
            require_agent_access(seeded, _user("intruder"), "agent-does-not-exist")
        assert exc.value.status_code == 403
        assert "no agent identity registered" in exc.value.detail
        assert "agent-does-not-exist" in exc.value.detail

    def test_wrong_wallet_names_owner(self, seeded):
        with pytest.raises(HTTPException) as exc:
            require_agent_access(seeded, _user("intruder"), AGENT)
        assert exc.value.status_code == 403
        assert "owned by a different wallet" in exc.value.detail
        assert OWNER_WALLET in exc.value.detail

    def test_owner_passes(self, seeded):
        require_agent_access(seeded, _user("owner1"), AGENT)

    def test_admin_passes(self, seeded):
        require_agent_access(seeded, _user("intruder", role="admin"), AGENT)


class TestAgentPerformance403Detail:
    """Same contract on the agent-performance router's own helper."""

    def test_missing_identity_names_agent_id(self, seeded):
        with pytest.raises(HTTPException) as exc:
            perf_access(seeded, _user("intruder"), "agent-does-not-exist")
        assert exc.value.status_code == 403
        assert "no agent identity registered" in exc.value.detail

    def test_wrong_wallet_names_owner(self, seeded):
        with pytest.raises(HTTPException) as exc:
            perf_access(seeded, _user("intruder"), AGENT)
        assert exc.value.status_code == 403
        assert "owned by a different wallet" in exc.value.detail
        assert OWNER_WALLET in exc.value.detail

    def test_owner_passes(self, seeded):
        perf_access(seeded, _user("owner1"), AGENT)
