"""POST spend-sessions body validation (#2723).

The route used to build ``AgentSpendSessionCreate`` by hand from a raw
dict: a missing ``cap_ait`` (KeyError), a non-numeric value
(InvalidOperation), or a bad ``chain_id`` (ValueError) escaped as a raw
500. The body is now the pydantic model itself, so FastAPI answers 422.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from aitbc.auth import create_access_token
from coordinator_api.contexts.agent_identity.domain.agent_identity import AgentIdentity

BASE = "/v1/agent-identity/identities/agent-2723/spend-sessions"


def _admin() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token('admin-1', 'admin')}"}


@pytest.fixture
def identity(db_session):
    row = AgentIdentity(agent_id="agent-2723", owner_address="0x" + "44" * 20)
    db_session.add(row)
    db_session.commit()
    return row


@pytest.mark.parametrize(
    "body",
    [
        {},  # missing cap_ait
        {"cap_ait": "not-a-number"},
        {"cap_ait": "1.5", "chain_id": "not-an-int"},
        {"cap_ait": 0},
        {"cap_ait": -1},
    ],
)
def test_malformed_body_answers_422(client: TestClient, identity, body: dict) -> None:
    resp = client.post(BASE, json=body, headers=_admin())
    assert resp.status_code == 422, resp.text


def test_valid_body_creates_session(client: TestClient, identity) -> None:
    resp = client.post(BASE, json={"cap_ait": "2.5", "chain_id": 1000}, headers=_admin())
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert Decimal(data["cap_ait"]) == Decimal("2.5")
    assert data["chain_id"] == 1000


def test_defaults_apply(client: TestClient, identity) -> None:
    resp = client.post(BASE, json={"cap_ait": 1}, headers=_admin())
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["chain_id"] == 1000
    assert data["allowed_ops"] == ["wallet.execute"]
