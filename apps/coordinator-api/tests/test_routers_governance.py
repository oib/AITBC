"""
Tests for governance router
"""

import pytest
from sqlmodel import Session

from aitbc.auth import create_access_token
from coordinator_api.contexts.market.domain.provider_bond import ProviderBond, ProviderBondStatus


def _headers(user_id: str = "admin-1", role: str = "admin") -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user_id, role)}"}


def _seed_bond(session: Session, provider_id: str, bond_id: str, status: str = ProviderBondStatus.LIQUIDATED.value) -> None:
    session.add(ProviderBond(provider_id=provider_id, bond_id=bond_id, status=status))
    session.commit()


@pytest.mark.unit
class TestGovernanceRouter:
    """Test governance router endpoints"""

    def test_submit_slash_appeal(self, client, db_session):
        """POST /v1/governance/slash-appeals stores an appeal and returns it."""
        _seed_bond(db_session, "provider-1", "bond-123")
        response = client.post(
            "/v1/governance/slash-appeals",
            json={
                "bond_id": "bond-123",
                "provider_id": "provider-1",
                "reason": "false positive",
                "evidence": ["ipfs://QmEvidence"],
            },
            headers=_headers(),
        )

        assert response.status_code == 201, response.text
        body = response.json()
        assert body["bond_id"] == "bond-123"
        assert body["status"] == "submitted"
        assert body["id"]
        assert body["created_at"]

    def test_submit_slash_appeal_unknown_bond_is_404(self, client, db_session):
        """#2359: appeals against nonexistent provider/bond ids must not create
        ghost records — the paid sweep filed appeals for ids that never existed."""
        response = client.post(
            "/v1/governance/slash-appeals",
            json={"bond_id": "bond-ghost", "provider_id": "provider-ghost", "reason": "x"},
            headers=_headers(),
        )

        assert response.status_code == 404

    def test_submit_slash_appeal_mismatched_bond_id_is_404(self, client, db_session):
        """A real provider's bond row does not legitimate a different bond_id."""
        _seed_bond(db_session, "provider-1", "bond-123")
        response = client.post(
            "/v1/governance/slash-appeals",
            json={"bond_id": "bond-other", "provider_id": "provider-1", "reason": "x"},
            headers=_headers(),
        )

        assert response.status_code == 404

    def test_submit_slash_appeal_requires_bond_id(self, client):
        """bond_id is required."""
        response = client.post("/v1/governance/slash-appeals", json={"reason": "x"}, headers=_headers())

        assert response.status_code == 422


# ---------------------------------------------------------------------------
# #2489 — empty ids, anonymous callers, unbounded evidence
# ---------------------------------------------------------------------------


class TestSlashAppealEmptyBond:
    """The #2359 ghost-bond guard must not be bypassed by empty strings."""

    @pytest.mark.parametrize(
        "payload",
        [
            {"bond_id": "", "provider_id": "provider-1"},
            {"bond_id": "", "provider_id": ""},
        ],
    )
    def test_empty_bond_id_is_422(self, client, db_session, payload):
        _seed_bond(db_session, "provider-1", "bond-123")
        response = client.post(
            "/v1/governance/slash-appeals",
            json={**payload, "reason": "x"},
            headers=_headers(),
        )
        assert response.status_code == 422

    def test_unauthenticated_appeal_is_401(self, client, db_session):
        _seed_bond(db_session, "provider-1", "bond-123")
        response = client.post(
            "/v1/governance/slash-appeals",
            json={"bond_id": "bond-123", "provider_id": "provider-1", "reason": "x"},
        )
        assert response.status_code == 401

    def test_non_owner_cannot_appeal_someone_elses_bond(self, client, db_session):
        _seed_bond(db_session, "provider-1", "bond-123")
        response = client.post(
            "/v1/governance/slash-appeals",
            json={"bond_id": "bond-123", "reason": "x"},
            headers=_headers(user_id="user-x", role="client"),
        )
        assert response.status_code == 403

    def test_provider_owner_can_appeal_own_bond(self, client, db_session):
        _seed_bond(db_session, "provider-1", "bond-123")
        # A caller whose JWT sub is the provider id owns the bond.
        response = client.post(
            "/v1/governance/slash-appeals",
            json={"bond_id": "bond-123", "reason": "x"},
            headers=_headers(user_id="provider-1", role="client"),
        )
        assert response.status_code == 201, response.text
        assert response.json()["provider_id"] == "provider-1"

    def test_provider_id_mismatch_is_404_not_stored(self, client, db_session):
        """A supplied provider_id that disagrees with the bond's owner must
        not legitimate the appeal."""
        _seed_bond(db_session, "provider-1", "bond-123")
        response = client.post(
            "/v1/governance/slash-appeals",
            json={"bond_id": "bond-123", "provider_id": "provider-2", "reason": "x"},
            headers=_headers(),
        )
        assert response.status_code == 404

    def test_evidence_is_bounded(self, client, db_session):
        _seed_bond(db_session, "provider-1", "bond-123")
        response = client.post(
            "/v1/governance/slash-appeals",
            json={"bond_id": "bond-123", "evidence": ["x"] * 21},
            headers=_headers(),
        )
        assert response.status_code == 422
        response = client.post(
            "/v1/governance/slash-appeals",
            json={"bond_id": "bond-123", "evidence": ["x" * 2049]},
            headers=_headers(),
        )
        assert response.status_code == 422
