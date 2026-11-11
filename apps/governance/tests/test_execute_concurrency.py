"""GOV-VOTE-UNIQUE-1 (#1803): pin conditional SUCCEEDED→EXECUTED in execute_proposal.

Vote dedup is already covered by ``test_vote_dedup_concurrency`` + migration 006;
this file pins the execute path mirroring ``_stamp_executed_from_chain``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.sql import Update

from governance_service.config import settings
from governance_service.domain.governance import Proposal, ProposalExecutionLog, ProposalStatus
from governance_service.services.governance_service import GovernanceService
from governance_service.storage import get_session


class _ExecuteListSession:
    """Stub session: SELECTs return the proposal; UPDATEs report ``rowcount``."""

    def __init__(self, proposal: Proposal, *, rowcount: int = 1) -> None:
        self._proposal = proposal
        self.added: list = []
        self.statements: list[str] = []
        self.rowcount = rowcount
        self.commits = 0

    def add(self, obj: object) -> None:
        self.added.append(obj)

    async def commit(self) -> None:
        self.commits += 1

    async def refresh(self, obj: object) -> None:
        pass

    async def execute(self, stmt: object, *args: object, **kwargs: object) -> SimpleNamespace:
        self.statements.append(str(stmt))
        if isinstance(stmt, Update):
            return SimpleNamespace(rowcount=self.rowcount)
        return SimpleNamespace(scalars=lambda: SimpleNamespace(first=lambda: self._proposal))


@pytest.mark.asyncio
async def test_execute_proposal_stamp_is_conditional_update(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "enable_onchain_submission", False)
    monkeypatch.setattr(settings, "require_execution_timelock", False)

    proposal = Proposal(
        proposal_id="prop_exec_race",
        proposer_id="p",
        title="t",
        description="d",
        status=ProposalStatus.SUCCEEDED,
        voting_starts=datetime.now(UTC) - timedelta(days=2),
        voting_ends=datetime.now(UTC) - timedelta(days=1),
    )
    session = _ExecuteListSession(proposal)
    bc = SimpleNamespace(
        get_block_height=AsyncMock(return_value=10**9),
        get_sealed_governance_proposal=AsyncMock(return_value=None),
    )
    svc = GovernanceService(session=session, blockchain_client=bc)  # type: ignore[arg-type]

    await svc.execute_proposal("prop_exec_race")

    updates = [s for s in session.statements if "UPDATE" in s.upper()]
    assert updates and any("proposals.status" in s for s in updates), session.statements


@pytest.mark.asyncio
async def test_execute_lost_race_marks_log_failed_not_completed(monkeypatch: pytest.MonkeyPatch) -> None:
    """rowcount 0 → refresh, no completed stamp on the execution log."""
    monkeypatch.setattr(settings, "enable_onchain_submission", False)
    monkeypatch.setattr(settings, "require_execution_timelock", False)

    proposal = Proposal(
        proposal_id="prop_exec_lost",
        proposer_id="p",
        title="t",
        description="d",
        status=ProposalStatus.SUCCEEDED,
        voting_starts=datetime.now(UTC) - timedelta(days=2),
        voting_ends=datetime.now(UTC) - timedelta(days=1),
    )
    session = _ExecuteListSession(proposal, rowcount=0)
    bc = SimpleNamespace(
        get_block_height=AsyncMock(return_value=10**9),
        get_sealed_governance_proposal=AsyncMock(return_value=None),
    )
    svc = GovernanceService(session=session, blockchain_client=bc)  # type: ignore[arg-type]

    await svc.execute_proposal("prop_exec_lost")

    logs = [o for o in session.added if isinstance(o, ProposalExecutionLog)]
    assert len(logs) == 1
    assert logs[0].status == "failed"
    assert "concurrent execute" in (logs[0].error_message or "")


async def _seed_succeeded_proposal() -> str:
    now = datetime.now(UTC)
    async with get_session() as session:
        proposal = Proposal(
            proposer_id="proposer-1",
            title="Execute concurrency probe",
            description="test",
            status=ProposalStatus.SUCCEEDED,
            voting_starts=now - timedelta(days=2),
            voting_ends=now - timedelta(days=1),
            block_height=1_000,
            voting_ends_block=8_000,
            quorum_required=Decimal("1"),
            yes_votes=Decimal("10"),
        )
        session.add(proposal)
        await session.commit()
        return proposal.proposal_id


@pytest.mark.asyncio
async def test_second_execute_after_first_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "enable_onchain_submission", False)
    monkeypatch.setattr(settings, "require_execution_timelock", False)

    proposal_id = await _seed_succeeded_proposal()
    bc = SimpleNamespace(
        get_block_height=AsyncMock(return_value=10**9),
        get_sealed_governance_proposal=AsyncMock(return_value=None),
    )
    async with get_session() as session:
        svc = GovernanceService(session, blockchain_client=bc)  # type: ignore[arg-type]
        await svc.execute_proposal(proposal_id)
        with pytest.raises(ValueError, match="not in succeeded"):
            await svc.execute_proposal(proposal_id)
