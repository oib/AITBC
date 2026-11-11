"""#1847 pins (audit F2/F3): governance routes bind caller identity and never
trust request-supplied addresses or voting power.

Pre-fix: governance-enhanced mutating routes had no auth dep at all and
governance.py's delegate route had none either — any client JWT could
create proposals/councils, cast votes under arbitrary addresses with
arbitrary voting_power, mint profile power via initial_voting_power, and
delegate any profile's votes to themselves.
"""

from __future__ import annotations

import pytest
from aitbc.auth import create_access_token
from sqlmodel import select

from coordinator_api.contexts.governance.domain.governance import (
    GovernanceProfile,
    Proposal,
)
from coordinator_api.contexts.governance.services.governance_service import GovernanceService
from coordinator_api.contexts.infrastructure.domain.user import User, Wallet

BASE = "/v1/governance-enhanced"

OWNER_WALLET = "0x08ab801150ef3496344cfa78fe025c3b48caf435"


def _headers(user_id: str, role: str = "client") -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user_id, role)}"}


_ADMIN = _headers("gov-admin-1847", "admin")
_ALICE = _headers("alice-1847", "client")
_BOB = _headers("bob-1847", "client")


@pytest.fixture
def seeded(db_session):
    """alice owns OWNER_WALLET; bob owns a different wallet; victim profile belongs to alice."""
    db_session.add(User(id="alice-1847", email="a@x", username="alice-1847"))
    db_session.add(Wallet(user_id="alice-1847", address=OWNER_WALLET))
    db_session.add(User(id="bob-1847", email="b@x", username="bob-1847"))
    db_session.add(Wallet(user_id="bob-1847", address="0x4a5b3bf95aa06072c568cfcb7392b4e86608b5d2"))
    victim = GovernanceProfile(profile_id="prof-victim", user_id="alice-1847", voting_power=5.0)
    db_session.add(victim)
    db_session.commit()
    return db_session


def _council_and_proposal(db_session):
    svc = GovernanceService(db_session)
    council = svc.create_regional_council("eu", "EU", "EU", ["0x" + "11" * 20], 100.0)
    proposal = svc.create_regional_proposal(council["council_id"], "t", "d", "general", 10.0, "alice-1847")
    return council["council_id"], proposal["proposal_id"]


# --- authN floor: unauthenticated callers get 401, clients can't admin-gate ---


def test_enhanced_mutations_require_auth(client):
    assert client.post(f"{BASE}/regional-councils").status_code == 401
    assert client.post(f"{BASE}/regional-proposals").status_code == 401
    assert client.post(f"{BASE}/profiles/create").status_code == 401
    assert client.post(f"{BASE}/profiles/delegate").status_code == 401
    assert client.post("/v1/governance/profiles/prof-x/delegate", json={"delegatee_id": "y"}).status_code == 401


def test_client_cannot_create_council(client):
    resp = client.post(
        f"{BASE}/regional-councils",
        params={
            "region": "eu",
            "council_name": "x",
            "jurisdiction": "EU",
            "council_members": ["0x" + "11" * 20],
            "budget_allocation": "1",
        },
        headers=_ALICE,
    )
    assert resp.status_code == 403


# --- F2: caller-supplied identity must match the token ---


def test_proposal_rejects_foreign_proposer(client, seeded):
    _council_and_proposal(seeded)
    council_id = GovernanceService(seeded).get_regional_councils()[0]["council_id"]
    resp = client.post(
        f"{BASE}/regional-proposals",
        params={
            "council_id": council_id,
            "title": "t",
            "description": "d",
            "proposal_type": "general",
            "amount_requested": "1",
            "proposer_address": "mallory-1847",
        },
        headers=_BOB,
    )
    assert resp.status_code == 403


def test_proposal_accepts_bound_identity_and_wallet(client, seeded):
    council_id, _ = _council_and_proposal(seeded)
    # sub identity
    resp = client.post(
        f"{BASE}/regional-proposals",
        params={
            "council_id": council_id,
            "title": "t",
            "description": "d",
            "proposal_type": "general",
            "amount_requested": "1",
            "proposer_address": "alice-1847",
        },
        headers=_ALICE,
    )
    assert resp.status_code == 200, resp.text
    # owned wallet address (any case) is also bound
    resp = client.post(
        f"{BASE}/regional-proposals",
        params={
            "council_id": council_id,
            "title": "t2",
            "description": "d",
            "proposal_type": "general",
            "amount_requested": "1",
            "proposer_address": OWNER_WALLET.upper().replace("0X", "0x"),
        },
        headers=_ALICE,
    )
    assert resp.status_code == 200, resp.text


def test_profile_create_rejects_foreign_user_and_minted_power(client, seeded):
    resp = client.post(
        f"{BASE}/profiles/create",
        params={"user_id": "victim-1847", "initial_voting_power": "999999"},
        headers=_BOB,
    )
    assert resp.status_code == 403
    # bound user_id works, but request-supplied power is ignored
    resp = client.post(
        f"{BASE}/profiles/create",
        params={"user_id": "bob-1847", "initial_voting_power": "999999"},
        headers=_BOB,
    )
    assert resp.status_code == 200, resp.text
    profile = seeded.exec(select(GovernanceProfile).where(GovernanceProfile.user_id == "bob-1847")).one()
    assert profile.voting_power == 0.0


# --- F2: voting power comes from the profile, never the request ---


def test_vote_uses_profile_power_not_request(client, seeded):
    _, proposal_id = _council_and_proposal(seeded)
    # prof-victim (user_id="alice-1847") already carries voting_power=5.0 —
    # get_or_create_profile returns it for voter_address="alice-1847", so the
    # tally must reflect stored profile power, not anything request-side.
    resp = client.post(
        f"{BASE}/regional-proposals/{proposal_id}/vote",
        params={"voter_address": "alice-1847", "vote_type": "for"},
        headers=_ALICE,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["vote"]["voting_power"] == 5.0
    proposal = seeded.exec(select(Proposal).where(Proposal.proposal_id == proposal_id)).one()
    assert proposal.votes_for == 5.0


def test_vote_rejects_foreign_voter_and_repeat(client, seeded):
    _, proposal_id = _council_and_proposal(seeded)
    resp = client.post(
        f"{BASE}/regional-proposals/{proposal_id}/vote",
        params={"voter_address": "alice-1847", "vote_type": "for"},
        headers=_BOB,
    )
    assert resp.status_code == 403
    # bound voter succeeds once, second vote refused
    assert (
        client.post(
            f"{BASE}/regional-proposals/{proposal_id}/vote",
            params={"voter_address": "alice-1847", "vote_type": "for"},
            headers=_ALICE,
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"{BASE}/regional-proposals/{proposal_id}/vote",
            params={"voter_address": "alice-1847", "vote_type": "against"},
            headers=_ALICE,
        ).status_code
        == 400  # service ValueError -> 400 (one vote per voter per proposal)
    )


# --- F3: delegation binds the delegator profile to the caller ---


def test_delegate_rejects_foreign_delegator(client, seeded):
    seeded.add(GovernanceProfile(profile_id="prof-bob", user_id="bob-1847", voting_power=1.0))
    seeded.commit()
    resp = client.post(
        f"{BASE}/profiles/delegate",
        params={"delegator_id": "prof-victim", "delegatee_id": "prof-bob"},
        headers=_BOB,
    )
    assert resp.status_code == 403
    victim = seeded.exec(select(GovernanceProfile).where(GovernanceProfile.profile_id == "prof-victim")).one()
    assert victim.delegate_to is None


def test_delegate_owner_and_admin(client, seeded):
    seeded.add(GovernanceProfile(profile_id="prof-bob", user_id="bob-1847", voting_power=1.0))
    seeded.commit()
    resp = client.post(
        f"{BASE}/profiles/delegate",
        params={"delegator_id": "prof-victim", "delegatee_id": "prof-bob"},
        headers=_ALICE,
    )
    assert resp.status_code == 200, resp.text
    # admin may delegate on behalf of any profile
    seeded.add(GovernanceProfile(profile_id="prof-carol", user_id="carol-1847", voting_power=1.0))
    seeded.commit()
    resp = client.post(
        f"{BASE}/profiles/delegate",
        params={"delegator_id": "prof-carol", "delegatee_id": "prof-bob"},
        headers=_ADMIN,
    )
    assert resp.status_code == 200, resp.text


def test_governance_router_delegate_binds_owner(client, seeded):
    seeded.add(GovernanceProfile(profile_id="prof-bob", user_id="bob-1847", voting_power=1.0))
    seeded.commit()
    resp = client.post(
        "/v1/governance/profiles/prof-victim/delegate",
        json={"delegatee_id": "prof-bob"},
        headers=_BOB,
    )
    assert resp.status_code == 403
    resp = client.post(
        "/v1/governance/profiles/prof-victim/delegate",
        json={"delegatee_id": "prof-bob"},
        headers=_ALICE,
    )
    assert resp.status_code == 200, resp.text
    victim = seeded.exec(select(GovernanceProfile).where(GovernanceProfile.profile_id == "prof-victim")).one()
    assert victim.delegate_to == "prof-bob"
