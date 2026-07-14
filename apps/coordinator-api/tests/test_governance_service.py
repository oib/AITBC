"""
Tests for governance service persistence.
"""

import pytest

from coordinator_api.contexts.governance.services.governance_service import GovernanceService


@pytest.mark.unit
async def test_regional_council_persisted_across_service_instances(db_session):
    """A council created through GovernanceService is returned by list."""
    service = GovernanceService(db_session)
    created = await service.create_regional_council(
        region="NA",
        council_name="NA Council",
        jurisdiction="US",
        council_members=["alice"],
        budget_allocation=100.0,
    )
    council_id = created["council_id"]

    another_service = GovernanceService(db_session)
    councils = await another_service.get_regional_councils(region="NA")
    assert any(c["council_id"] == council_id for c in councils)
