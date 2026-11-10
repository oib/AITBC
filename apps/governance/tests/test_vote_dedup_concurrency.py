"""Concurrency pin for GovernanceService.create_vote (#1091 follow-on).

The one-vote-per-voter-per-proposal rule is enforced by a check-then-act
scan plus the ``uq_votes_proposal_voter_ci`` unique index on
``(proposal_id, lower(voter_id))`` (#1610) that catches a racer whose scan
predates the winner's commit. Two simultaneous votes from the same voter
must not both land and stack weight — the loser's ``IntegrityError`` is
translated back into the same "already voted" ``ValueError``.

The test drives ``create_vote`` on two independent sessions against the
suite's real SQLite database, with an ``asyncio.Barrier`` inside each
session's first ``execute`` so both duplicate scans complete before either
insert commits — the deterministic shape of the HTTP race.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from governance_service.domain.governance import Proposal, Vote
from governance_service.services.governance_service import GovernanceService
from governance_service.storage import get_session


class _BarrierSession:
    """AsyncSession proxy parking the first ``execute`` until peers arrive.

    ``create_vote`` issues its duplicate-vote ``list_votes`` SELECT before
    the INSERT+commit; gating there forces both scans to see the same
    pre-insert state.
    """

    def __init__(self, inner: AsyncSession, barrier: asyncio.Barrier) -> None:
        self._inner = inner
        self._barrier = barrier
        self._parked = False

    async def execute(self, stmt: Any, *args: Any, **kwargs: Any) -> Any:
        result = await self._inner.execute(stmt, *args, **kwargs)
        if not self._parked:
            self._parked = True
            await self._barrier.wait()
        return result

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


async def _seed_active_proposal() -> str:
    """Insert an ACTIVE proposal (voting window open → no chain probe)."""
    now = datetime.now(UTC)
    async with get_session() as session:
        proposal = Proposal(
            proposer_id="proposer-1",
            title="Concurrency probe",
            description="test",
            voting_starts=now - timedelta(hours=1),
            voting_ends=now + timedelta(days=7),
            status="active",
        )
        session.add(proposal)
        await session.commit()
        return proposal.proposal_id


@pytest.mark.asyncio
async def test_concurrent_duplicate_votes_at_most_one_lands() -> None:
    proposal_id = await _seed_active_proposal()
    vote_data = {
        "proposal_id": proposal_id,
        "voter_id": "voter-1",
        "vote_type": "for",
        "reason": "",
    }

    barrier = asyncio.Barrier(2)
    async with get_session() as s1, get_session() as s2:
        svc1 = GovernanceService(_BarrierSession(s1, barrier))  # type: ignore[arg-type]
        svc2 = GovernanceService(_BarrierSession(s2, barrier))  # type: ignore[arg-type]
        results = await asyncio.gather(
            svc1.create_vote(dict(vote_data)),
            svc2.create_vote(dict(vote_data)),
            return_exceptions=True,
        )

    async with get_session() as session:
        count = (
            await session.execute(
                select(func.count()).select_from(Vote).where(Vote.proposal_id == proposal_id, Vote.voter_id == "voter-1")
            )
        ).scalar_one()

    successes = [r for r in results if not isinstance(r, BaseException)]
    duplicates = [r for r in results if isinstance(r, ValueError) and "already voted" in str(r)]
    assert len(successes) + len(duplicates) == 2, f"unexpected outcomes: {results!r}"
    assert count == 1, f"{count} vote rows for one voter on one proposal — duplicate scan raced: {results!r}"
