"""#3063: permissionless early close defeats the voting window.

``close_proposal`` used to succeed the moment quorum+approval were met,
even minutes into the window — any whale (or sybil multiplier) could
propose, self-vote, and close before the community could react. The fix:
before ``voting_ends`` a proposal closes succeeded only when the outcome
is mathematically irreversible — even if every remaining unit of
stake-backed power (bounded by ``2 × circulating supply`` under the #3062
backing caps) voted AGAINST, approval would still pass.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from aitbc.utils.units import ait_to_units
from governance_service.domain.governance import Proposal
from governance_service.services.governance_service import GovernanceService
from governance_service.storage import get_session


class _Chain:
    """Fake chain: per-address AIT balances (reported in units), a supply
    aggregate, and failure toggles."""

    def __init__(self, balances=None, supply=None):
        self.balances = {k.lower(): Decimal(str(v)) for k, v in (balances or {}).items()}
        self.supply = supply if supply is not None else {"circulating_ait": "1000", "height": 42}
        self.fail_power = False
        self.fail_supply = False
        self.height = 42

    def set_balance(self, address: str, ait) -> None:
        self.balances[address.lower()] = Decimal(str(ait))

    async def get_voting_power(self, address, chain_id=None):
        if self.fail_power:
            raise ConnectionError("rpc down")
        return ait_to_units(self.balances.get(str(address).lower(), Decimal("0")))

    async def get_circulating_supply(self, chain_id=None):
        if self.fail_supply:
            raise ConnectionError("rpc down")
        if isinstance(self.supply, Exception):
            raise self.supply
        return self.supply

    async def get_block_height(self, chain_id=None):
        return self.height


@asynccontextmanager
async def _svc(chain):
    async with get_session() as session:
        yield GovernanceService(session, blockchain_client=chain)  # type: ignore[arg-type]


@pytest.fixture(scope="module", autouse=True)
def _cleanup_rows():
    """The suite shares one sqlite DB — remove every row these pins create."""
    yield
    import sqlite3

    from aitbc.constants import DATA_DIR

    db = DATA_DIR / "data" / "governance_service.db"
    ids = (
        "gov-early-close-pin",
        "0xWHALE",
        "0xBIG",
        "0xMID",
        "0xNOISE",
        "0xLATE",
        "0xEMERG1",
        "0xEMERG2",
        "0xSUPP",
    )
    marks = ",".join("?" for _ in ids)
    con = sqlite3.connect(db)
    try:
        con.execute(
            "DELETE FROM votes WHERE proposal_id IN (SELECT proposal_id FROM proposals WHERE proposer_id = ?)",
            ("gov-early-close-pin",),
        )
        con.execute("DELETE FROM proposals WHERE proposer_id = ?", ("gov-early-close-pin",))
        con.execute(f"DELETE FROM token_stakes WHERE staker_address IN ({marks})", ids)
        con.execute(f"DELETE FROM governance_tokens WHERE holder_address IN ({marks})", ids)
        con.execute(f"DELETE FROM governance_profiles WHERE user_id IN ({marks})", ids)
        con.commit()
    finally:
        con.close()


async def _proposal(svc: GovernanceService, proposal_type: str = "general") -> Proposal:
    return await svc.create_proposal(
        {
            "proposer_id": "gov-early-close-pin",
            "title": "t",
            "description": "d",
            "proposal_type": proposal_type,
        }
    )


async def _vote(svc: GovernanceService, pid: str, address: str, vote_type: str = "for") -> None:
    await svc.create_vote(
        {
            "proposal_id": pid,
            "voter_id": address,
            "voter_address": address,
            "vote_type": vote_type,
            "reason": "",
        }
    )


async def _end_window(pid: str) -> None:
    async with get_session() as session:
        proposal = (await session.execute(select(Proposal).where(Proposal.proposal_id == pid))).scalars().one()
        proposal.voting_ends = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()


async def _stored(pid: str) -> Proposal:
    async with get_session() as session:
        return (await session.execute(select(Proposal).where(Proposal.proposal_id == pid))).scalars().one()


# supply circulating=1000 → quorum 300 (30%), max castable power 2000


@pytest.mark.asyncio
async def test_early_close_refused_when_reversible() -> None:
    """The defect verbatim: quorum+approval met minutes in, but the outcome
    can still flip — every remaining unit of power voting no wins. The old
    code returned SUCCEEDED here."""
    chain = _Chain(balances={"0xWHALE": 200})
    async with _svc(chain) as svc:
        proposal = await _proposal(svc)
        pid = proposal.proposal_id
        await svc.stake_tokens("0xWHALE", Decimal("200"), 30)
        await _vote(svc, pid, "0xWHALE")  # power 400 ≥ quorum 300, approval 100%

        with pytest.raises(ValueError, match="not mathematically irreversible"):
            await svc.close_proposal(pid)

    stored = await _stored(pid)
    assert str(stored.status) == "active"


@pytest.mark.asyncio
async def test_early_close_refused_with_no_votes_in_mix() -> None:
    """yes=800/no=100 meets quorum and approval — but 1200 weight of
    uncommitted power can still outvote it."""
    chain = _Chain(balances={"0xMID": 400, "0xNOISE": 50})
    async with _svc(chain) as svc:
        proposal = await _proposal(svc)
        pid = proposal.proposal_id
        await svc.stake_tokens("0xMID", Decimal("400"), 30)  # power 800
        await svc.stake_tokens("0xNOISE", Decimal("50"), 30)  # power 100
        await _vote(svc, pid, "0xMID")
        await _vote(svc, pid, "0xNOISE", vote_type="against")

        with pytest.raises(ValueError, match="not mathematically irreversible"):
            await svc.close_proposal(pid)


@pytest.mark.asyncio
async def test_early_close_succeeds_when_irreversible() -> None:
    """yes=1800 of max possible 2000 — even if ALL remaining power votes
    no, approval stays 90% ≥ 50%. Early close is the designed escape."""
    chain = _Chain(balances={"0xBIG": 900})
    async with _svc(chain) as svc:
        proposal = await _proposal(svc)
        pid = proposal.proposal_id
        await svc.stake_tokens("0xBIG", Decimal("900"), 30)  # power 1800
        await _vote(svc, pid, "0xBIG")

        closed = await svc.close_proposal(pid)
        assert str(closed.status) == "succeeded"


@pytest.mark.asyncio
async def test_post_window_close_unaffected() -> None:
    """The gate only applies pre-window: a reversible-but-met tally closes
    normally once voting_ends has passed (existing semantics preserved)."""
    chain = _Chain(balances={"0xLATE": 200})
    async with _svc(chain) as svc:
        proposal = await _proposal(svc)
        pid = proposal.proposal_id
        await svc.stake_tokens("0xLATE", Decimal("200"), 30)
        await _vote(svc, pid, "0xLATE")

    await _end_window(pid)
    async with _svc(chain) as svc:
        closed = await svc.close_proposal(pid)
    assert str(closed.status) == "succeeded"


@pytest.mark.asyncio
async def test_supply_failure_blocks_early_close() -> None:
    """Fail-closed: without a fresh supply figure the bound cannot be
    computed — the close is refused, not guessed."""
    chain = _Chain(balances={"0xSUPP": 900})
    async with _svc(chain) as svc:
        proposal = await _proposal(svc)
        pid = proposal.proposal_id
        await svc.stake_tokens("0xSUPP", Decimal("900"), 30)
        await _vote(svc, pid, "0xSUPP")

    chain.fail_supply = True
    async with _svc(chain) as svc:
        with pytest.raises(ValueError, match="not mathematically irreversible"):
            await svc.close_proposal(pid)


@pytest.mark.asyncio
async def test_emergency_early_close_needs_supermajority_of_supply() -> None:
    """Emergency threshold is 2/3 and quorum 80% of supply — early close
    needs yes ≥ 2/3 × 2000 = 1333, well above the 800 quorum."""
    chain = _Chain(balances={"0xEMERG1": 700, "0xEMERG2": 500})
    async with _svc(chain) as svc:
        # yes=1400 ≥ 1333 → irreversible → early close allowed.
        p1 = await _proposal(svc, proposal_type="emergency")
        await svc.stake_tokens("0xEMERG1", Decimal("700"), 30)  # power 1400
        await _vote(svc, p1.proposal_id, "0xEMERG1")
        closed = await svc.close_proposal(p1.proposal_id)
        assert str(closed.status) == "succeeded"

        # yes=1000: quorum 800 met, approval 100% met, but 1000/2000 = 50% <
        # 66.67% — still reversible, close refused.
        p2 = await _proposal(svc, proposal_type="emergency")
        await svc.stake_tokens("0xEMERG2", Decimal("500"), 30)  # power 1000
        await _vote(svc, p2.proposal_id, "0xEMERG2")
        with pytest.raises(ValueError, match="not mathematically irreversible"):
            await svc.close_proposal(p2.proposal_id)
