"""
Tests for governance service persistence.
"""

from decimal import Decimal

import pytest

from coordinator_api.contexts.governance.services.governance_service import GovernanceService


@pytest.mark.unit
@pytest.mark.asyncio
async def test_regional_council_persisted_across_service_instances(db_session):
    """A council created through GovernanceService is returned by list."""
    service = GovernanceService(db_session)
    created = service.create_regional_council(
        region="NA",
        council_name="NA Council",
        jurisdiction="US",
        council_members=["alice"],
        budget_allocation=Decimal("100"),
    )
    council_id = created["council_id"]

    another_service = GovernanceService(db_session)
    councils = another_service.get_regional_councils(region="NA")
    assert any(c["council_id"] == council_id for c in councils)


@pytest.mark.unit
def test_process_proposal_lifecycle_handles_naive_voting_ends(db_session):
    """COORD-GOVERNANCE-PROCESS-PROPOSAL-ALWAYS-500-NAIVE-VS-AWARE-DATETIME-1.

    The proposals table stores plain (naive) datetimes; comparing them with
    datetime.now(UTC) raised TypeError and the route answered 500.
    """
    from datetime import UTC, datetime, timedelta

    from coordinator_api.contexts.governance.domain.governance import (
        GovernanceProfile,
        ProposalStatus,
    )

    profile = GovernanceProfile(user_id="proposer-1")
    db_session.add(profile)
    db_session.commit()
    service = GovernanceService(db_session)
    proposal = service.create_governance_proposal(
        proposer_id=profile.profile_id,
        proposal_data={"title": "t", "description": "d"},
    )
    proposal.voting_ends = (datetime.now(UTC) - timedelta(hours=1)).replace(tzinfo=None)
    db_session.commit()

    processed = service.process_proposal_lifecycle(proposal.proposal_id)
    assert processed.status == ProposalStatus.DEFEATED
