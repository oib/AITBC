"""#2877: reconcile probe failures are cached briefly, not re-fired per read.

GET /v1/governance/proposals is unauthenticated and fires one chain probe
per eligible row; failures used to skip the cache entirely, so an
unreachable node got one RPC call per row per request. The failure cache
(15s, class-level like the negative cache) bounds that amplification while
still recovering quickly.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from governance_service.domain.governance import Proposal, ProposalStatus
from governance_service.services.governance_service import GovernanceService


class _Session:
    async def execute(self, stmt, *a, **k):
        return SimpleNamespace(scalars=lambda: SimpleNamespace(first=lambda: None, all=lambda: []))


class _FailChain:
    def __init__(self):
        self.calls = 0

    async def get_sealed_governance_proposal(self, proposal_id, chain_id=None):
        self.calls += 1
        raise ConnectionError("rpc down")


def _proposal() -> Proposal:
    return Proposal(
        proposal_id="prop_probe_fail",
        proposer_id="p",
        title="t",
        description="d",
        status=ProposalStatus.SUCCEEDED,
        voting_starts=datetime.now(UTC) - timedelta(days=2),
        voting_ends=datetime.now(UTC) - timedelta(days=1),
    )


@pytest.fixture(autouse=True)
def _clear_caches():
    GovernanceService._reconcile_neg_cache.clear()
    GovernanceService._reconcile_fail_cache.clear()
    yield
    GovernanceService._reconcile_neg_cache.clear()
    GovernanceService._reconcile_fail_cache.clear()


@pytest.mark.asyncio
async def test_probe_failure_is_cached_briefly():
    chain = _FailChain()
    svc = GovernanceService(session=_Session(), blockchain_client=chain)  # type: ignore[arg-type]
    proposal = _proposal()

    assert await svc._reconcile_probe_onchain(proposal) is None
    assert await svc._reconcile_probe_onchain(proposal) is None
    assert await svc._reconcile_probe_onchain(proposal) is None
    # One probe total — the failure answer is remembered, not re-fired.
    assert chain.calls == 1


@pytest.mark.asyncio
async def test_probe_failure_cache_expires():
    chain = _FailChain()
    svc = GovernanceService(session=_Session(), blockchain_client=chain)  # type: ignore[arg-type]
    proposal = _proposal()
    key = (proposal.chain_id, proposal.proposal_id)

    await svc._reconcile_probe_onchain(proposal)
    # Simulate expiry: the entry's monotonic deadline is in the past.
    GovernanceService._reconcile_fail_cache[key] = 0.0
    await svc._reconcile_probe_onchain(proposal)
    assert chain.calls == 2
