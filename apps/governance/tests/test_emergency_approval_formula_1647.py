"""#1647: emergency approval re-check must use yes/(yes+no), not yes/(yes+no+abstain).

``close_proposal`` tallies approval as yes / decisive votes (abstentions count
toward quorum only). ``update_proposal_status("succeeded")`` re-checked emergency
proposals with abstentions in the denominator — a proposal could pass the close
tally then be rejected on every retry, leaving it unclosable. Operator ruling:
unify on yes/(yes+no).
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from governance_service.services.governance_service import GovernanceService


class _Session:
    def __init__(self, proposal):
        self._proposal = proposal

    async def commit(self):
        pass

    async def refresh(self, obj):
        pass

    async def execute(self, stmt):
        proposal = self._proposal
        return SimpleNamespace(scalars=lambda: SimpleNamespace(first=lambda: proposal))


def _emergency_proposal(yes, no, abstain, quorum="1"):
    return SimpleNamespace(
        proposal_id="p1",
        proposal_type="emergency",
        status="active",
        yes_votes=Decimal(yes),
        no_votes=Decimal(no),
        votes_abstain=Decimal(abstain),
        quorum_required=Decimal(quorum),
    )


@pytest.mark.asyncio
async def test_abstentions_do_not_sink_emergency_supermajority():
    """yes=7,no=2,abstain=10: decisive rate 77.8% >= 66.67% — must succeed.

    Under the old denominator (7/19 = 36.8%) this raised on every retry.
    """
    svc = GovernanceService(session=_Session(_emergency_proposal(7, 2, 10)))  # type: ignore[arg-type]
    result = await svc.update_proposal_status("p1", "succeeded")
    assert result is not None


@pytest.mark.asyncio
async def test_decisive_rate_below_threshold_still_rejected():
    svc = GovernanceService(session=_Session(_emergency_proposal(1, 2, 0)))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="supermajority"):
        await svc.update_proposal_status("p1", "succeeded")


@pytest.mark.asyncio
async def test_all_abstain_emergency_rejected():
    """decisive=0 → approval 0 — cannot pass the supermajority check."""
    svc = GovernanceService(session=_Session(_emergency_proposal(0, 0, 5)))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="supermajority"):
        await svc.update_proposal_status("p1", "succeeded")
