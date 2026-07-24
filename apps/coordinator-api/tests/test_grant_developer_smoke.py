"""Smoke test for the developer registry and grant lifecycle."""

from __future__ import annotations

import asyncio
from datetime import datetime

import pytest
from sqlmodel import Session, SQLModel, create_engine

from coordinator_api.contexts.developer.schemas.developer import DeveloperCreate
from coordinator_api.contexts.developer.services.developer_service import DeveloperService
from coordinator_api.contexts.governance.services.grant_service import GrantService


@pytest.mark.unit
def test_grant_developer_lifecycle() -> None:
    """End-to-end check for developer registration, grant voting, and disbursement."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        dev_service = DeveloperService(session)
        developer = asyncio.run(dev_service.register(DeveloperCreate(wallet_address="0xabc123", name="Smoke Dev")))
        assert developer.wallet_address == "0xabc123"

        grant_service = GrantService(session)
        grant = asyncio.run(grant_service.create_grant(developer.id, "Smoke Grant", "description", "100.5", voting_days=1))
        assert grant.status.value == "submitted"
        assert float(grant.requested_amount) == 100.5

        voted = asyncio.run(grant_service.vote(grant.id, "for", 10.0))
        assert voted.votes_for == 10.0

        # Move voting end into the past so the proposal can be resolved.
        voted.voting_ends = datetime(2000, 1, 1)
        session.add(voted)
        session.commit()

        resolved = asyncio.run(grant_service.process_grant(voted.id))
        assert resolved.status.value == "approved"
        assert float(resolved.approved_amount) == 100.5

        final = asyncio.run(grant_service.disburse(resolved.id, amount="100.5"))
        assert final.status.value == "completed"
        assert float(final.disbursed_amount) == 100.5
