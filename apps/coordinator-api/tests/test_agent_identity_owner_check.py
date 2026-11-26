"""Pin for #1070: agent-identity write routes check the caller owns the identity.

Pre-fix every handler ignored the caller: a miner token could verify,
deactivate, update, migrate, export and create wallets for any agent_id.
Post-fix writes require the identity's owner_address to be one of the
caller's wallets (users.id -> wallets), or an admin token.
"""

from __future__ import annotations

import pytest
from aitbc.auth import create_access_token

from coordinator_api.contexts.agent_identity.domain.agent_identity import AgentIdentity, CrossChainMapping
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
def test_owner_cannot_self_verify_identity(client, db_session, seeded_identity):
    """#2710: verification is an operator action — even the identity owner
    (with their own verifier wallet) gets 403."""
    db_session.add(CrossChainMapping(agent_id=AGENT_ID, chain_id=1, chain_address="0x" + "11" * 20))
    db_session.commit()
    resp = client.post(
        f"/v1/agent-identity/identities/{AGENT_ID}/cross-chain/1/verify",
        headers=_token("owner1", "client"),
        json={"verifier_address": OWNER_ADDR, "proof_hash": "0x00"},
    )
    assert resp.status_code == 403


@pytest.mark.unit
def test_admin_can_verify_identity(client, db_session, seeded_identity):
    db_session.add(CrossChainMapping(agent_id=AGENT_ID, chain_id=1, chain_address="0x" + "11" * 20))
    db_session.commit()
    resp = client.post(
        f"/v1/agent-identity/identities/{AGENT_ID}/cross-chain/1/verify",
        headers=_token("admin1", "admin"),
        json={
            "verifier_address": OWNER_ADDR,
            "proof_hash": "0x00",
            "verification_type": "multi-signature",
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["verified"] is True


@pytest.mark.unit
def test_verify_rejects_unknown_verification_type(client, db_session, seeded_identity):
    db_session.add(CrossChainMapping(agent_id=AGENT_ID, chain_id=1, chain_address="0x" + "11" * 20))
    db_session.commit()
    resp = client.post(
        f"/v1/agent-identity/identities/{AGENT_ID}/cross-chain/1/verify",
        headers=_token("admin1", "admin"),
        json={"verifier_address": OWNER_ADDR, "proof_hash": "0x00", "verification_type": "bogus"},
    )
    assert resp.status_code == 400


@pytest.mark.unit
def test_batch_verify_requires_admin(client, seeded_identity):
    resp = client.post(
        "/v1/agent-identity/identities/batch-verify",
        headers=_token("owner1", "client"),
        json=[{"identity_id": "id1", "chain_id": 1, "verifier_address": OWNER_ADDR, "proof_hash": "0x00"}],
    )
    assert resp.status_code == 403


@pytest.mark.unit
def test_admin_bypasses_owner_check(client, seeded_identity):
    resp = client.put(
        f"/v1/agent-identity/identities/{AGENT_ID}",
        headers=_token("admin1", "admin"),
        json={"display_name": "admin set"},
    )
    assert resp.status_code != 403


# #3020 (AUTHZ-AGENT-IDENTITY-READ-EXPOSURE-1): the read side of the same
# surface. Every endpoint below exposes wallet addresses, balances,
# transaction history, owner_address or spend metadata and must apply the
# same owner-or-admin gate the writes already had. The matrix stays ANY —
# the middleware admits any valid JWT and the handler enforces ownership.

GATED_READ_PATHS = [
    # identity summary: owner_address + per-chain chain_address/wallet_address + wallet stats
    f"/v1/agent-identity/identities/{AGENT_ID}",
    # cross-chain mappings carry chain_address + wallet_address
    f"/v1/agent-identity/identities/{AGENT_ID}/cross-chain/mapping",
    f"/v1/agent-identity/identities/{AGENT_ID}/wallets",
    f"/v1/agent-identity/identities/{AGENT_ID}/wallets/1/balance",
    f"/v1/agent-identity/identities/{AGENT_ID}/wallets/1/transactions",
    # agent_id -> chain wallet address
    f"/v1/agent-identity/identities/{AGENT_ID}/resolve/1",
]


@pytest.mark.unit
@pytest.mark.parametrize("path", GATED_READ_PATHS)
def test_non_owner_cannot_read(client, seeded_identity, path):
    resp = client.get(path, headers=_token("intruder", "miner"))
    assert resp.status_code == 403, path


@pytest.mark.unit
@pytest.mark.parametrize("path", GATED_READ_PATHS)
def test_anonymous_cannot_read(client, seeded_identity, path):
    assert client.get(path).status_code == 401, path


@pytest.mark.unit
@pytest.mark.parametrize("path", GATED_READ_PATHS)
def test_owner_can_read(client, seeded_identity, path):
    resp = client.get(path, headers=_token("owner1", "client"))
    assert resp.status_code != 403, f"{path}: {resp.status_code} {resp.text[:200]}"


@pytest.mark.unit
@pytest.mark.parametrize("path", GATED_READ_PATHS)
def test_admin_can_read(client, seeded_identity, path):
    resp = client.get(path, headers=_token("admin1", "admin"))
    assert resp.status_code != 403, f"{path}: {resp.status_code} {resp.text[:200]}"


@pytest.mark.unit
def test_owner_gets_identity_summary(client, seeded_identity):
    """Owner pin on the summary payload itself — the 200 path, not just !=403."""
    resp = client.get(f"/v1/agent-identity/identities/{AGENT_ID}", headers=_token("owner1", "client"))
    assert resp.status_code == 200, resp.text
    assert resp.json()["identity"]["agent_id"] == AGENT_ID


@pytest.mark.unit
def test_address_resolve_stays_discovery(client, seeded_identity, db_session):
    """#3020: /address/{addr}/resolve/{chain} is the pure discovery direction —
    it echoes the caller-supplied address plus the public agent_id and stays
    at the ANY floor (any authenticated role)."""
    from coordinator_api.contexts.agent_identity.domain.agent_identity import CrossChainMapping

    db_session.add(
        CrossChainMapping(
            agent_id=AGENT_ID,
            chain_id=1,
            chain_address="0x" + "11" * 20,
            wallet_address=OWNER_ADDR.lower(),
        )
    )
    db_session.commit()
    resp = client.get(
        f"/v1/agent-identity/address/{'0x' + '11' * 20}/resolve/1",
        headers=_token("intruder", "miner"),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["agent_id"] == AGENT_ID
