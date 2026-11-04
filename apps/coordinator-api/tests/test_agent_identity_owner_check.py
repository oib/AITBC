"""Pin for #1070: agent-identity write routes check the caller owns the identity.

Pre-fix every handler ignored the caller: a miner token could verify,
deactivate, update, migrate, export and create wallets for any agent_id.
Post-fix writes require the identity's owner_address to be one of the
caller's wallets (users.id -> wallets), or an admin token.
"""

from __future__ import annotations

import pytest
from aitbc.auth import create_access_token

from coordinator_api.contexts.agent_identity.domain.agent_identity import AgentIdentity
from coordinator_api.contexts.infrastructure.domain.user import User, Wallet

OWNER_ADDR = "0x08aB801150eF3496344cFA78fe025c3B48Caf435"
AGENT_ID = "agent-owner-check-1"


@pytest.fixture
def seeded_identity(db_session):
    db_session.add(User(id="owner1", email="owner1@aitbc.local", username="owner1"))
    db_session.add(Wallet(user_id="owner1", address=OWNER_ADDR.lower()))
    db_session.add(User(id="intruder", email="intruder@aitbc.local", username="intruder"))
    db_session.add(Wallet(user_id="intruder", address="0x4A5b3bf95aa06072c568cfcb7392b4e86608b5d2"))
    db_session.add(AgentIdentity(agent_id=AGENT_ID, owner_address=OWNER_ADDR.lower()))
    db_session.commit()
    return AGENT_ID


def _token(user_id: str, role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user_id, role)}"}


@pytest.mark.unit
def test_non_owner_cannot_update(client, seeded_identity):
    resp = client.put(
        f"/v1/agent-identity/identities/{AGENT_ID}",
        headers=_token("intruder", "client"),
        json={"display_name": "hijacked"},
    )
    assert resp.status_code == 403


@pytest.mark.unit
def test_non_owner_cannot_deactivate(client, seeded_identity):
    resp = client.post(
        f"/v1/agent-identity/identities/{AGENT_ID}/deactivate",
        headers=_token("intruder", "miner"),
        json={"reason": "attack"},
    )
    assert resp.status_code == 403


@pytest.mark.unit
def test_verify_requires_caller_verifier_address(client, seeded_identity):
    resp = client.post(
        f"/v1/agent-identity/identities/{AGENT_ID}/cross-chain/1/verify",
        headers=_token("intruder", "miner"),
        json={"verifier_address": "0x0000000000000000000000000000000000000001", "proof_hash": "0x00"},
    )
    assert resp.status_code == 403


@pytest.mark.unit
def test_owner_can_update(client, seeded_identity):
    resp = client.put(
        f"/v1/agent-identity/identities/{AGENT_ID}",
        headers=_token("owner1", "client"),
        json={"display_name": "mine"},
    )
    assert resp.status_code != 403


@pytest.mark.unit
def test_admin_bypasses_owner_check(client, seeded_identity):
    resp = client.put(
        f"/v1/agent-identity/identities/{AGENT_ID}",
        headers=_token("admin1", "admin"),
        json={"display_name": "admin set"},
    )
    assert resp.status_code != 403
