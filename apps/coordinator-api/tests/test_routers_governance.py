"""
Tests for governance router
"""

import pytest
from sqlmodel import Session

from coordinator_api.contexts.market.domain.provider_bond import ProviderBond, ProviderBondStatus


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
        )

        assert response.status_code == 404

    def test_submit_slash_appeal_mismatched_bond_id_is_404(self, client, db_session):
        """A real provider's bond row does not legitimate a different bond_id."""
        _seed_bond(db_session, "provider-1", "bond-123")
        response = client.post(
            "/v1/governance/slash-appeals",
            json={"bond_id": "bond-other", "provider_id": "provider-1", "reason": "x"},
        )

        assert response.status_code == 404

    def test_submit_slash_appeal_requires_bond_id(self, client):
        """bond_id is required."""
        response = client.post("/v1/governance/slash-appeals", json={"reason": "x"})

        assert response.status_code == 422
