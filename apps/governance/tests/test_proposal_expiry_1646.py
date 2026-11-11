"""#1646: EXPIRED status + expiry sweep for window-ended proposals.

Operator ruling B: keep voting_ends advisory for existing tallies; add an
EXPIRED status and a sweep that stops NEW votes after voting_ends; no
retroactive tally change. Votes outside the window were already refused
(257a0bca24) — this pins the status transition and that close_proposal can
still resolve an EXPIRED proposal.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from governance_service.domain.governance import Proposal
from governance_service.services.governance_service import GovernanceService
from governance_service.storage import get_session


class _NoChain:
    async def get_sealed_governance_proposal(self, *a, **k):
        return None


async def _seed(voting_ends: datetime, status: str = "active", quorum: str = "1") -> str:
    now = datetime.now(UTC)
    async with get_session() as session:
        proposal = Proposal(
            proposer_id="proposer-1",
            title="Expiry probe",
            description="test",
            voting_starts=now - timedelta(days=2),
            voting_ends=voting_ends,
            quorum_required=Decimal(quorum),
            status=status,
        )
        session.add(proposal)
        await session.commit()
        return proposal.proposal_id


@pytest.mark.asyncio
async def test_expire_stale_marks_past_end_active_expired() -> None:
    now = datetime.now(UTC)
    stale = await _seed(now - timedelta(hours=1))
    fresh = await _seed(now + timedelta(days=7))

    async with get_session() as session:
        svc = GovernanceService(session, blockchain_client=_NoChain())  # type: ignore[arg-type]
        assert await svc.expire_stale_proposals() >= 1

    async with get_session() as session:
        from sqlalchemy import select

        rows = (await session.execute(select(Proposal).where(Proposal.proposal_id.in_([stale, fresh])))).scalars().all()
        by_id = {p.proposal_id: p.status for p in rows}
    assert str(by_id[stale]) == "expired"
    assert str(by_id[fresh]) == "active"


@pytest.mark.asyncio
async def test_expired_proposal_rejects_new_votes() -> None:
    now = datetime.now(UTC)
    proposal_id = await _seed(now - timedelta(hours=1))
    async with get_session() as session:
        svc = GovernanceService(session, blockchain_client=_NoChain())  # type: ignore[arg-type]
        await svc.expire_stale_proposals()
        with pytest.raises(ValueError, match="not active"):
            await svc.create_vote({"proposal_id": proposal_id, "voter_id": "late", "vote_type": "for", "reason": ""})


@pytest.mark.asyncio
async def test_close_proposal_resolves_expired_to_defeated() -> None:
    """An expired proposal with no votes and unmet quorum closes DEFEATED —
    EXPIRED must not strand it."""
    now = datetime.now(UTC)
    proposal_id = await _seed(now - timedelta(hours=1), quorum="1000000")
    async with get_session() as session:
        svc = GovernanceService(session, blockchain_client=_NoChain())  # type: ignore[arg-type]
        await svc.expire_stale_proposals()
        closed = await svc.close_proposal(proposal_id)
    assert str(closed.status) == "defeated"
