"""GOV-LIST-EXEC-STALE-1 (#757): chain-truth reconcile for executed proposals.

A GOVERNANCE_EXECUTE submitted straight to the blockchain RPC seals without the
service seeing it; the service row then reports ``active`` forever
(prop_76855f71, 28 Oct). ``_reconcile_executed_onchain`` writes the truth back:
status ``executed``, the sealed tx hash, the sealing block's timestamp and a
``reconcile`` execution-log row — skipped for already-executed rows and for
proposals still inside their voting window, and failure-soft when the node
cannot answer.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


from governance_service.domain.governance import Proposal, ProposalExecutionLog, ProposalStatus
from governance_service.services.governance_service import GovernanceService, _RECONCILE_PROBE_CONCURRENCY


class _Session:
    def __init__(self):
        self.added = []

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        pass

    async def refresh(self, obj):
        pass

    async def execute(self, stmt):
        return SimpleNamespace(scalars=lambda: SimpleNamespace(first=lambda: self._row))

    _row = None


def _proposal(*, status=ProposalStatus.ACTIVE, voting_ends=None):
    return Proposal(
        proposal_id="prop_recon",
        proposer_id="tester",
        title="t",
        description="d",
        category="general",
        proposal_type="parameter_change",
        chain_id="bc-2",
        status=status,
        voting_starts=datetime.now(UTC) - timedelta(days=8),
        voting_ends=voting_ends if voting_ends is not None else datetime.now(UTC) - timedelta(days=1),
        yes_votes=Decimal("100"),
        quorum_required=Decimal("1"),
    )


def _client(*, sealed=None, block=None, raises=False):
    c = SimpleNamespace()
    c.get_sealed_governance_proposal = AsyncMock(side_effect=RuntimeError("rpc down") if raises else None)
    if not raises:
        c.get_sealed_governance_proposal.return_value = sealed
    c.get_block = AsyncMock(return_value=block)
    return c


async def test_chain_executed_writes_back_status_hash_timestamp_and_log():
    session = _Session()
    proposal = _proposal()
    client = _client(
        sealed={"executed": True, "execute_tx_hash": "0x8dc52a2a", "execute_block_height": 9278},
        block={"timestamp": "2026-10-28T20:35:33.989611"},
    )
    svc = GovernanceService(session=session, blockchain_client=client)  # type: ignore[arg-type]

    out = await svc._reconcile_executed_onchain(proposal)

    assert out.status == ProposalStatus.EXECUTED
    assert out.execution_tx_hash == "0x8dc52a2a"
    assert out.executed_at == datetime(2026, 10, 28, 20, 35, 33, 989611, tzinfo=UTC)
    assert out.proposal_metadata["execution_block_height"] == 9278
    logs = [o for o in session.added if isinstance(o, ProposalExecutionLog)]
    assert len(logs) == 1 and logs[0].execution_step == "reconcile" and logs[0].status == "completed"


async def test_inside_voting_window_and_not_executed_are_not_probed():
    session = _Session()
    client = _client(sealed={"executed": True, "execute_tx_hash": "0x1", "execute_block_height": 1})
    svc = GovernanceService(session=session, blockchain_client=client)  # type: ignore[arg-type]

    in_window = _proposal(voting_ends=datetime.now(UTC) + timedelta(days=1))
    assert await svc._reconcile_executed_onchain(in_window) is in_window
    assert in_window.status == ProposalStatus.ACTIVE

    unexecuted = _proposal()
    client.get_sealed_governance_proposal.return_value = {"executed": False}
    assert await svc._reconcile_executed_onchain(unexecuted) is unexecuted
    assert unexecuted.status == ProposalStatus.ACTIVE
    assert not [o for o in session.added if isinstance(o, ProposalExecutionLog)]


async def test_rpc_failure_and_missing_record_leave_row_untouched():
    session = _Session()
    proposal = _proposal()
    svc = GovernanceService(session=session, blockchain_client=_client(raises=True))  # type: ignore[arg-type]
    assert await svc._reconcile_executed_onchain(proposal) is proposal
    assert proposal.status == ProposalStatus.ACTIVE

    svc._blockchain = _client(sealed=None)
    assert await svc._reconcile_executed_onchain(proposal) is proposal
    assert proposal.status == ProposalStatus.ACTIVE


async def test_already_executed_is_a_noop():
    proposal = _proposal(status=ProposalStatus.EXECUTED)
    client = _client()
    svc = GovernanceService(session=_Session(), blockchain_client=client)  # type: ignore[arg-type]
    assert await svc._reconcile_executed_onchain(proposal) is proposal
    client.get_sealed_governance_proposal.assert_not_called()


class _ListSession:
    """Stub session for the list path: the proposals SELECT returns a fixed
    set; every other statement (the conditional stamp UPDATE) reports the
    configured rowcount."""

    def __init__(self, proposals, rowcount=1):
        self.added = []
        self.statements = []
        self._proposals = proposals
        self.rowcount = rowcount
        self.commits = 0

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1

    async def refresh(self, obj):
        pass

    async def execute(self, stmt):
        self.statements.append(str(stmt))
        return SimpleNamespace(
            scalars=lambda: SimpleNamespace(all=lambda: self._proposals, first=lambda: None),
            rowcount=self.rowcount,
        )


class TestListReconcile:
    """GOV-LIST-RECONCILE-COST-1: the list path probes bounded-concurrent,
    caches a 'not executed' answer briefly, and stamps conditionally so a
    racing second writer adds no second reconcile log row."""

    @pytest.fixture(autouse=True)
    def _clear_neg_cache(self):
        GovernanceService._reconcile_neg_cache.clear()
        yield
        GovernanceService._reconcile_neg_cache.clear()

    async def test_probes_are_bounded_concurrent(self):
        proposals = [_proposal() for _ in range(10)]
        for i, p in enumerate(proposals):
            p.proposal_id = f"prop_{i}"
        in_flight = max_in_flight = calls = 0

        async def probe(pid, chain):
            nonlocal in_flight, max_in_flight, calls
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
            calls += 1
            await asyncio.sleep(0.02)
            in_flight -= 1
            return None

        client = SimpleNamespace(get_sealed_governance_proposal=probe)
        svc = GovernanceService(session=_ListSession(proposals), blockchain_client=client)  # type: ignore[arg-type]
        await svc.list_proposals()

        assert calls == len(proposals)
        assert 1 < max_in_flight <= _RECONCILE_PROBE_CONCURRENCY

    async def test_negative_cache_skips_the_second_probe(self):
        proposals = [_proposal() for _ in range(5)]
        for i, p in enumerate(proposals):
            p.proposal_id = f"prop_{i}"
        calls = 0

        async def probe(pid, chain):
            nonlocal calls
            calls += 1
            return None

        client = SimpleNamespace(get_sealed_governance_proposal=probe)
        svc = GovernanceService(session=_ListSession(proposals), blockchain_client=client)  # type: ignore[arg-type]
        await svc.list_proposals()
        await svc.list_proposals()

        assert calls == len(proposals)

    async def test_a_lost_stamp_race_adds_no_second_log_row(self):
        """The conditional UPDATE reporting 0 rows changed means the other
        writer already stamped: refresh, no ProposalExecutionLog."""
        session = _ListSession([], rowcount=0)
        proposal = _proposal()
        client = _client(sealed={"executed": True, "execute_tx_hash": "0x1", "execute_block_height": 1})
        svc = GovernanceService(session=session, blockchain_client=client)  # type: ignore[arg-type]

        await svc._stamp_executed_from_chain(proposal, {"executed": True, "execute_tx_hash": "0x1", "execute_block_height": 1})

        assert [o for o in session.added if isinstance(o, ProposalExecutionLog)] == []
        assert session.commits == 0

    async def test_the_stamp_is_a_conditional_update(self):
        """Losing the race must be detectable: the UPDATE carries
        `status != executed` so the second writer changes zero rows."""
        session = _ListSession([])
        proposal = _proposal()
        client = _client(sealed={"executed": True, "execute_tx_hash": "0x1", "execute_block_height": 1})
        svc = GovernanceService(session=session, blockchain_client=client)  # type: ignore[arg-type]

        await svc._stamp_executed_from_chain(proposal, {"executed": True, "execute_tx_hash": "0x1", "execute_block_height": 1})

        assert any("status !=" in stmt for stmt in session.statements), session.statements
