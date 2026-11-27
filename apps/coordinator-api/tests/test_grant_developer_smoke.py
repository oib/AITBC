"""Smoke test for the developer registry and grant lifecycle."""

from __future__ import annotations

import tempfile
import time
from datetime import datetime

import pytest
from eth_account import Account
from sqlmodel import Session, SQLModel, create_engine

from aitbc.crypto.developer_registry import developer_register_claim, sign_developer_register
from coordinator_api.contexts.developer.schemas.developer import DeveloperCreate
from coordinator_api.contexts.developer.services.developer_service import DeveloperService
from coordinator_api.contexts.governance.services.grant_service import GrantService

_DEV_KEY = Account.from_key("0x" + "33" * 32)


@pytest.mark.unit
def test_grant_developer_lifecycle() -> None:
    """End-to-end check for developer registration, grant voting, and disbursement."""
    engine = create_engine(f"sqlite:///{tempfile.mkdtemp()}/test.db", echo=False, connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        dev_service = DeveloperService(session)
        # #3023 made signature/timestamp required on DeveloperCreate.
        timestamp = int(time.time())
        claim = developer_register_claim(
            wallet_address=_DEV_KEY.address, name="Smoke Dev", email=None, github_handle=None, timestamp=timestamp
        )
        developer = dev_service.register(
            DeveloperCreate(
                wallet_address=_DEV_KEY.address,
                name="Smoke Dev",
                signature=sign_developer_register(claim, _DEV_KEY.key.hex()),
                timestamp=timestamp,
            )
        )
        assert developer.wallet_address == _DEV_KEY.address.lower()

        grant_service = GrantService(session)
        grant = grant_service.create_grant(developer.id, "Smoke Grant", "description", "100.5", voting_days=1)
        assert grant.status.value == "voting"  # #2356: fresh proposals open in VOTING
        assert float(grant.requested_amount) == 100.5

        voted = grant_service.vote(grant.id, "for", 10.0)
        assert voted.votes_for == 10.0

        # Move voting end into the past so the proposal can be resolved.
        voted.voting_ends = datetime(2000, 1, 1)
        session.add(voted)
        session.commit()

        resolved = grant_service.process_grant(voted.id)
        assert resolved.status.value == "approved"
        assert float(resolved.approved_amount) == 100.5

        final = grant_service.disburse(resolved.id, amount="100.5")
        assert final.status.value == "completed"
        assert float(final.disbursed_amount) == 100.5
    engine.dispose()
