"""#3064 (AUDIT-GOV-TALLY-RACE-1): proposal tally counters are atomic.

``_persist_vote`` used to bump ``proposals.yes_votes`` / ``no_votes`` /
``votes_abstain`` with a Python-side read-modify-write across per-request
sessions — and the read ran an ``await`` (the reconcile probe) between
fetch and write, so concurrent votes interleaved and silently dropped each
other's increments. ``close_proposal`` tallies off those counters, so the
quorum/approval arithmetic drifted from the vote-row ledger.

The fix issues one atomic ``UPDATE proposals SET col = col + :w`` per vote.
This pin drives ``create_vote`` for N distinct voters on N independent
sessions. A session proxy parks every caller after the *second*
``SELECT ... FROM proposals`` — under the old code that second read was the
counter fetch inside ``_persist_vote``, so all N racers read the same
pre-increment tally before any commit (the deterministic lost-update
shape); under the atomic UPDATE there is no second proposals read and the
proxy never parks.

Pins:

- N concurrent votes → stored counters equal the vote-row sums exactly,
  including the ``votes_for`` / ``votes_against`` legacy mirrors.
- ``close_proposal`` resolves the same tally the rows record.
- Same-voter dedup still rejects a repeat.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aitbc.utils.units import ait_to_units
from governance_service.domain.governance import Proposal, ProposalStatus, Vote, VoteType
from governance_service.services.governance_service import GovernanceService
from governance_service.storage import get_session

_PROPOSER = "gov-tally-race"


@pytest.fixture(scope="module", autouse=True)
def _cleanup_rows():
    """The suite shares one sqlite DB — remove every row these pins create
    so later files' list/pagination assertions see a clean table."""
    yield
    import sqlite3

    from aitbc.constants import DATA_DIR

    db = DATA_DIR / "data" / "governance_service.db"
    con = sqlite3.connect(db)
    try:
        con.execute(
            "DELETE FROM votes WHERE proposal_id IN (SELECT proposal_id FROM proposals WHERE proposer_id = ?)",
            (_PROPOSER,),
        )
        con.execute("DELETE FROM proposals WHERE proposer_id = ?", (_PROPOSER,))
        con.execute("DELETE FROM token_stakes WHERE staker_address LIKE '0xTALLY%'")
        con.execute("DELETE FROM governance_tokens WHERE holder_address LIKE '0xTALLY%'")
        con.execute("DELETE FROM governance_profiles WHERE user_id LIKE '0xTALLY%'")
        con.commit()
    finally:
        con.close()


class _Chain:
    """Fake chain: per-address AIT balances (reported in units, like the
    real ``/rpc/account``), a supply aggregate, and a block height."""

    def __init__(self, balances=None, supply=None):
        self.balances = {k.lower(): Decimal(str(v)) for k, v in (balances or {}).items()}
        self.supply = supply if supply is not None else {"circulating_ait": "10", "height": 42}
        self.height = 42

    async def get_voting_power(self, address, chain_id=None):
        return ait_to_units(self.balances.get(str(address).lower(), Decimal("0")))

    async def get_circulating_supply(self, chain_id=None):
        return self.supply

    async def get_block_height(self, chain_id=None):
        return self.height


class _TallyBarrierSession:
    """AsyncSession proxy parking after the second ``SELECT ... FROM proposals``.

    ``create_vote`` reads the proposal once for validation; the removed
    read-modify-write read it a second time inside ``_persist_vote``. Gating
    there forces every racer to tally from the same pre-increment counters —
    the exact interleave that lost updates. With the atomic UPDATE there is
    no second proposals read, so the barrier simply never trips.
    """

    def __init__(self, inner: AsyncSession, barrier: asyncio.Barrier) -> None:
        self._inner = inner
        self._barrier = barrier
        self._proposal_selects = 0

    async def execute(self, stmt: Any, *args: Any, **kwargs: Any) -> Any:
        result = await self._inner.execute(stmt, *args, **kwargs)
        if isinstance(stmt, Select) and "proposals" in str(stmt):
            self._proposal_selects += 1
            if self._proposal_selects == 2:
                await self._barrier.wait()
        return result

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


@asynccontextmanager
async def _svc(chain: _Chain):
    async with get_session() as s:
        yield GovernanceService(s, blockchain_client=chain)  # type: ignore[arg-type]


async def _seed(chain: _Chain, tag: str) -> tuple[str, dict[str, Decimal]]:
    """Create a proposal and stake-backed voters; return (proposal_id, addr→power).

    ``tag`` keeps each test's voter addresses disjoint — stakes accumulate on
    the shared suite database, so reusing an address would stack power.
    """
    async with _svc(chain) as svc:
        proposal = await svc.create_proposal(
            {
                "proposer_id": _PROPOSER,
                "title": "tally race pin",
                "description": "d",
            }
        )
        pid = proposal.proposal_id

    # power = token_balance(0) + 2 * min(staked, on-chain balance); each
    # voter stakes a distinct amount so a lost increment is unmistakable.
    powers: dict[str, Decimal] = {}
    for i in range(6):
        addr = f"0xTALLY{tag}{i}"
        stake = Decimal(i + 1)
        powers[addr] = stake * 2
        async with _svc(chain) as svc:
            await svc.stake_tokens(addr, stake, 30)
    return pid, powers


async def _proposal(proposal_id: str) -> Proposal:
    async with get_session() as session:
        return (await session.execute(select(Proposal).where(Proposal.proposal_id == proposal_id))).scalars().one()


async def _row_sums(proposal_id: str) -> dict[VoteType, Decimal]:
    async with get_session() as session:
        rows = (await session.execute(select(Vote).where(Vote.proposal_id == proposal_id))).scalars().all()
    sums = {VoteType.FOR: Decimal("0"), VoteType.AGAINST: Decimal("0"), VoteType.ABSTAIN: Decimal("0")}
    for v in rows:
        sums[VoteType(v.vote_type)] += Decimal(v.voting_power_used or 0)
    return sums


@pytest.mark.asyncio
async def test_concurrent_votes_counters_match_vote_rows() -> None:
    tag = "A"
    addrs = [f"0xTALLY{tag}{i}" for i in range(6)]
    chain = _Chain(balances=dict.fromkeys(addrs, 1000))
    pid, powers = await _seed(chain, tag)
    # 4 FOR / 1 AGAINST / 1 ABSTAIN across six distinct staked voters.
    types = [VoteType.FOR, VoteType.FOR, VoteType.AGAINST, VoteType.ABSTAIN, VoteType.FOR, VoteType.FOR]

    barrier = asyncio.Barrier(len(addrs))

    async def _one_vote(addr: str, vote_type: VoteType) -> None:
        async with get_session() as session:
            svc = GovernanceService(
                _TallyBarrierSession(session, barrier),
                blockchain_client=chain,  # type: ignore[arg-type]
            )
            await svc.create_vote(
                {
                    "proposal_id": pid,
                    "voter_id": addr,
                    "voter_address": addr,
                    "vote_type": str(vote_type),
                    "reason": "",
                }
            )

    async with asyncio.TaskGroup() as tg:
        for addr, vote_type in zip(addrs, types, strict=True):
            tg.create_task(_one_vote(addr, vote_type))

    expected = {VoteType.FOR: Decimal("0"), VoteType.AGAINST: Decimal("0"), VoteType.ABSTAIN: Decimal("0")}
    for addr, vt in zip(addrs, types, strict=True):
        expected[vt] += powers[addr]

    proposal = await _proposal(pid)
    rows = await _row_sums(pid)
    assert rows == expected, f"vote-row sums drifted: {rows} != {expected}"

    # Counters must equal the ledger exactly — no lost increments.
    assert proposal.yes_votes == expected[VoteType.FOR], f"yes_votes {proposal.yes_votes} != {expected[VoteType.FOR]}"
    assert proposal.no_votes == expected[VoteType.AGAINST]
    assert proposal.votes_abstain == expected[VoteType.ABSTAIN]
    # Legacy mirrors track the same counters.
    assert proposal.votes_for == proposal.yes_votes
    assert proposal.votes_against == proposal.no_votes


@pytest.mark.asyncio
async def test_close_proposal_tally_matches_ledger() -> None:
    tag = "B"
    addrs = [f"0xTALLY{tag}{i}" for i in range(6)]
    chain = _Chain(balances=dict.fromkeys(addrs, 1000))
    pid, powers = await _seed(chain, tag)

    # Sequential votes are enough here — the tally path is what is pinned.
    async with _svc(chain) as svc:
        for i, addr in enumerate(addrs):
            await svc.create_vote(
                {
                    "proposal_id": pid,
                    "voter_id": addr,
                    "voter_address": addr,
                    "vote_type": "against" if i == 0 else "for",
                    "reason": "",
                }
            )

    async with get_session() as session:
        proposal = (await session.execute(select(Proposal).where(Proposal.proposal_id == pid))).scalars().one()
        proposal.voting_ends = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()

    async with _svc(chain) as svc:
        closed = await svc.close_proposal(pid)

    rows = await _row_sums(pid)
    yes = rows[VoteType.FOR]
    no = rows[VoteType.AGAINST]
    abstain = rows[VoteType.ABSTAIN]
    assert closed.status == ProposalStatus.SUCCEEDED
    assert closed.yes_votes == yes
    assert closed.no_votes == no
    assert closed.votes_abstain == abstain
    assert closed.yes_votes + closed.no_votes + closed.votes_abstain == sum(powers.values())


@pytest.mark.asyncio
async def test_duplicate_vote_still_rejected_after_atomic_bump() -> None:
    tag = "C"
    addrs = [f"0xTALLY{tag}{i}" for i in range(6)]
    chain = _Chain(balances=dict.fromkeys(addrs, 1000))
    pid, _ = await _seed(chain, tag)
    addr = addrs[0]
    async with _svc(chain) as svc:
        await svc.create_vote({"proposal_id": pid, "voter_id": addr, "voter_address": addr, "vote_type": "for", "reason": ""})
        with pytest.raises(ValueError, match="already voted"):
            await svc.create_vote(
                {"proposal_id": pid, "voter_id": addr, "voter_address": addr, "vote_type": "for", "reason": ""}
            )
    proposal = await _proposal(pid)
    # One vote landed, one bump — the rejected duplicate added nothing.
    assert proposal.yes_votes == Decimal("2")
    async with get_session() as session:
        count = (
            await session.execute(select(func.count()).select_from(Vote).where(Vote.proposal_id == pid, Vote.voter_id == addr))
        ).scalar_one()
    assert count == 1
