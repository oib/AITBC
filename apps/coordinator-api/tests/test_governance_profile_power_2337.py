"""#2337 pins: admin voting-power bootstrap + profile init/delegate CLI surface.

Economic-proposal votes tally ``effective_voting_power(profile)``; a fresh
JWT user gets ``voting_power=0.0`` and every vote adds nothing. The admin
``POST /v1/governance/profiles/{id}/voting-power`` endpoint is the escape
hatch for profiles auto-created at 0 — ``POST /profiles`` only applies
``initial_voting_power`` at creation.
"""

from __future__ import annotations

import pytest
from aitbc.auth import create_access_token

from coordinator_api.contexts.governance.domain.governance import GovernanceProfile

_ADMIN = {"Authorization": f"Bearer {create_access_token('gov-admin-2337', 'admin')}"}
_CLIENT = {"Authorization": f"Bearer {create_access_token('gov-client-2337', 'client')}"}


@pytest.fixture
def profile(db_session):
    p = GovernanceProfile(profile_id="prof-2337", user_id="user-2337", voting_power=0.0)
    db_session.add(p)
    db_session.commit()
    return p


def test_admin_sets_voting_power(client, db_session, profile):
    resp = client.post(
        "/v1/governance/profiles/prof-2337/voting-power",
        json={"voting_power": 42.5},
        headers=_ADMIN,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["voting_power"] == 42.5
    db_session.expire_all()
    assert db_session.get(GovernanceProfile, "prof-2337").voting_power == 42.5


def test_client_cannot_set_voting_power(client, profile):
    resp = client.post(
        "/v1/governance/profiles/prof-2337/voting-power",
        json={"voting_power": 42.5},
        headers=_CLIENT,
    )
    assert resp.status_code == 403


def test_unauthenticated_gets_401(client, profile):
    resp = client.post("/v1/governance/profiles/prof-2337/voting-power", json={"voting_power": 1.0})
    assert resp.status_code == 401


def test_unknown_profile_404(client, db_session):
    resp = client.post(
        "/v1/governance/profiles/nope/voting-power",
        json={"voting_power": 1.0},
        headers=_ADMIN,
    )
    assert resp.status_code == 404


def test_negative_power_rejected(client, profile):
    resp = client.post(
        "/v1/governance/profiles/prof-2337/voting-power",
        json={"voting_power": -1.0},
        headers=_ADMIN,
    )
    assert resp.status_code == 422


def test_admin_profile_init_applies_power_only_on_create(client, db_session):
    """POST /profiles honors initial_voting_power for a NEW profile but
    ignores it for an existing one — the trap the power endpoint fixes."""
    resp = client.post(
        "/v1/governance/profiles",
        json={"user_id": "fresh-2337", "initial_voting_power": 7.0},
        headers=_ADMIN,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["voting_power"] == 7.0
    profile_id = resp.json()["profile_id"]

    again = client.post(
        "/v1/governance/profiles",
        json={"user_id": "fresh-2337", "initial_voting_power": 99.0},
        headers=_ADMIN,
    )
    assert again.status_code == 200
    assert again.json()["voting_power"] == 7.0
    assert again.json()["profile_id"] == profile_id


def test_client_cannot_init_profile(client):
    resp = client.post(
        "/v1/governance/profiles",
        json={"user_id": "x", "initial_voting_power": 5.0},
        headers=_CLIENT,
    )
    assert resp.status_code == 403
