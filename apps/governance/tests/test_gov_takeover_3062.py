"""#3062: movable-balance voting power + inverted emergency quorum.

Pins for the takeover fix:

- quorum is a fraction of circulating supply for BOTH proposal classes
  (emergency uses the higher percent — never the percent-as-tokens 80);
  an unreadable supply leaves an unreachable quorum, not a passable one.
- voting power is stake-backed only: unexpired ``token_stakes`` capped by
  the wallet's *current* on-chain balance (chain units → AIT), re-verified
  at vote time AND again at close — tokens moved after staking stop
  counting, so one balance cannot be recycled across sybil addresses.
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


@pytest.fixture(scope="module", autouse=True)
def _cleanup_rows():
    """The suite shares one sqlite DB — remove every row these pins create
    so later files' list/pagination assertions see a clean table."""
    yield
    import sqlite3

    from aitbc.constants import DATA_DIR

    db = DATA_DIR / "data" / "governance_service.db"
    ids = (
        "gov-takeover-pin",
        "0xVOTER1",
        "0xVOTER2",
        "0xRICH",
        "0xSTAKER",
        "0xWHALE",
        "0xR1",
        "0xR2",
        "0xR3",
        "0xHOLDER",
        "0xHELPER",
        "helper-voter",
        "0xDUAL",
        "voter-a",
        "voter-b",
        "0xSTAYED",
    )
    marks = ",".join("?" for _ in ids)
    con = sqlite3.connect(db)
    try:
        con.execute(
            "DELETE FROM votes WHERE proposal_id IN (SELECT proposal_id FROM proposals WHERE proposer_id = ?)",
            ("gov-takeover-pin",),
        )
        con.execute("DELETE FROM proposals WHERE proposer_id = ?", ("gov-takeover-pin",))
        con.execute(f"DELETE FROM token_stakes WHERE staker_address IN ({marks})", ids)
        con.execute(f"DELETE FROM governance_tokens WHERE holder_address IN ({marks})", ids)
        con.execute(f"DELETE FROM governance_profiles WHERE user_id IN ({marks})", ids)
        con.commit()
    finally:
        con.close()


class _Chain:
    """Fake chain: per-address AIT balances (reported in units, like the
    real ``/rpc/account``), a supply aggregate, and a block height."""

    def __init__(self, balances=None, supply=None):
        self.balances = {k.lower(): Decimal(str(v)) for k, v in (balances or {}).items()}
        self.supply = supply if supply is not None else {"circulating_ait": "1000000", "height": 42}
        self.fail_power = False
        self.height = 42

    def set_balance(self, address: str, ait) -> None:
        self.balances[address.lower()] = Decimal(str(ait))

    async def get_voting_power(self, address, chain_id=None):
        if self.fail_power:
            raise ConnectionError("rpc down")
        return ait_to_units(self.balances.get(str(address).lower(), Decimal("0")))

    async def get_circulating_supply(self, chain_id=None):
        if isinstance(self.supply, Exception):
            raise self.supply
        return self.supply

    async def get_block_height(self, chain_id=None):
        return self.height


@asynccontextmanager
async def _svc(chain):
    async with get_session() as session:
        yield GovernanceService(session, blockchain_client=chain)  # type: ignore[arg-type]


async def _create_proposal(svc: GovernanceService, proposal_type: str = "general") -> Proposal:
    return await svc.create_proposal(
        {
            "proposer_id": "gov-takeover-pin",
            "title": "t",
            "description": "d",
            "proposal_type": proposal_type,
        }
    )


async def _vote(svc: GovernanceService, proposal_id: str, address: str, voter_id: str | None = None) -> None:
    await svc.create_vote(
        {
            "proposal_id": proposal_id,
            "voter_id": voter_id or address,
            "voter_address": address,
            "vote_type": "for",
            "reason": "",
        }
    )


async def _end_window(proposal_id: str) -> None:
    async with get_session() as session:
        proposal = (await session.execute(select(Proposal).where(Proposal.proposal_id == proposal_id))).scalars().one()
        proposal.voting_ends = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()


async def _proposal(proposal_id: str) -> Proposal:
    async with get_session() as session:
        return (await session.execute(select(Proposal).where(Proposal.proposal_id == proposal_id))).scalars().one()


# ---------------------------------------------------------------- quorum


@pytest.mark.asyncio
async def test_normal_quorum_is_supply_fraction() -> None:
    chain = _Chain(supply={"circulating_ait": "1000000", "height": 42})
    async with _svc(chain) as svc:
        proposal = await _create_proposal(svc)
        # 30% of 1,000,000 AIT — not the flat 1,000,000 model default.
        assert proposal.quorum_required == Decimal("300000")
        assert proposal.snapshot_block == 42
        assert proposal.snapshot_timestamp is not None
        assert proposal.proposal_metadata["quorum_circulating_ait"] == "1000000"


@pytest.mark.asyncio
async def test_emergency_quorum_uses_higher_percent_not_absolute_80() -> None:
    chain = _Chain(supply={"circulating_ait": "1000000", "height": 7})
    async with _svc(chain) as svc:
        proposal = await _create_proposal(svc, proposal_type="emergency")
        # 80% of supply — the old code stored the literal 80 as the quorum.
        assert proposal.quorum_required == Decimal("800000")
        assert proposal.quorum_required != Decimal("80")


@pytest.mark.asyncio
async def test_supply_failure_leaves_unreachable_quorum() -> None:
    chain = _Chain(supply=ConnectionError("rpc down"))
    async with _svc(chain) as svc:
        proposal = await _create_proposal(svc)
        assert proposal.quorum_required == GovernanceService._QUORUM_UNREACHABLE
        assert "quorum_supply_error" in (proposal.proposal_metadata or {})


# ------------------------------------------------------- voting power


@pytest.mark.asyncio
async def test_movable_balance_stops_counting() -> None:
    """Stake 100 AIT backed by 100 AIT → power 200; move the tokens away →
    power follows the CURRENT balance, not the stake record."""
    addr = "0xVOTER1"
    chain = _Chain(balances={addr: 100})
    async with _svc(chain) as svc:
        await svc.stake_tokens(addr, Decimal("100"), 30)
        assert await svc.calculate_voting_power(addr) == Decimal("200")

        chain.set_balance(addr, 10)
        assert await svc.calculate_voting_power(addr) == Decimal("20")

        chain.set_balance(addr, 0)
        assert await svc.calculate_voting_power(addr) == Decimal("0")


@pytest.mark.asyncio
async def test_expired_lock_gives_no_power() -> None:
    """lock_period_days=0 expires immediately — no permanent 2× position."""
    addr = "0xVOTER2"
    chain = _Chain(balances={addr: 100})
    async with _svc(chain) as svc:
        await svc.stake_tokens(addr, Decimal("100"), 0)
        assert await svc.calculate_voting_power(addr) == Decimal("0")


@pytest.mark.asyncio
async def test_unbacked_stake_and_raw_balance_have_no_power() -> None:
    """Raw balance alone never counted off-chain; a stake the wallet can no
    longer back contributes nothing."""
    rich = "0xRICH"  # balance but never staked
    chain = _Chain(balances={rich: 500})
    async with _svc(chain) as svc:
        assert await svc.calculate_voting_power(rich) == Decimal("0")


# ------------------------------------------------------------- tallies


@pytest.mark.asyncio
async def test_vote_weight_is_stake_backed_not_balance() -> None:
    chain = _Chain(balances={"0xSTAKER": 100, "0xWHALE": 500})
    async with _svc(chain) as svc:
        proposal = await _create_proposal(svc)
        pid = proposal.proposal_id
        await svc.stake_tokens("0xSTAKER", Decimal("100"), 30)
        await _vote(svc, pid, "0xSTAKER")
        await _vote(svc, pid, "0xWHALE")

    stored = await _proposal(pid)
    # Only the staked-and-backed address counted: 2 × min(100, 100) = 200.
    assert stored.yes_votes == Decimal("200")


@pytest.mark.asyncio
async def test_close_reverification_defeats_sequential_recycling() -> None:
    """The assembled exploit: one 100-AIT balance recycles across three
    addresses — stake, vote, transfer, repeat. Cast-time tallies reach 600;
    at close only the still-backed address counts → 200 < quorum → defeated.
    """
    chain = _Chain(supply={"circulating_ait": "1000", "height": 1})  # quorum = 300
    async with _svc(chain) as svc:
        proposal = await _create_proposal(svc)
        pid = proposal.proposal_id

        for addr in ("0xR1", "0xR2", "0xR3"):
            chain.set_balance(addr, 100)
            await svc.stake_tokens(addr, Decimal("100"), 30)
            await _vote(svc, pid, addr)
            # Move the float on to the next sybil — the last holder keeps it.
            if addr != "0xR3":
                chain.set_balance(addr, 0)

    # Cast-time tally: 3 × 200 = 600 — looks like a landslide.
    assert (await _proposal(pid)).yes_votes == Decimal("600")

    await _end_window(pid)
    async with _svc(chain) as svc:
        closed = await svc.close_proposal(pid)

    assert str(closed.status) == "defeated"
    # Only 0xR3 still holds the backing: effective tally is its 200, not 600.
    assert closed.yes_votes == Decimal("200")
    assert closed.yes_votes < closed.quorum_required


@pytest.mark.asyncio
async def test_close_keeps_simultaneously_backed_votes() -> None:
    """Control: voters still holding their stakes keep full weight — the
    re-verification only removes what is no longer backed."""
    chain = _Chain(
        balances={"0xHOLDER": 100, "0xHELPER": 50},
        supply={"circulating_ait": "100", "height": 1},  # quorum = 30
    )
    async with _svc(chain) as svc:
        proposal = await _create_proposal(svc)
        pid = proposal.proposal_id
        await svc.stake_tokens("0xHOLDER", Decimal("100"), 30)
        await svc.stake_tokens("0xHELPER", Decimal("50"), 30)
        await _vote(svc, pid, "0xHOLDER")
        await _vote(svc, pid, "0xHELPER", voter_id="helper-voter")

    await _end_window(pid)
    async with _svc(chain) as svc:
        closed = await svc.close_proposal(pid)

    assert str(closed.status) == "succeeded"
    assert closed.yes_votes == Decimal("300")  # 200 + 100, all still backed


@pytest.mark.asyncio
async def test_same_address_cannot_double_count_across_voter_ids() -> None:
    """Two voter_ids on one address share a single backing pool at close."""
    chain = _Chain(balances={"0xDUAL": 100}, supply={"circulating_ait": "100", "height": 1})
    async with _svc(chain) as svc:
        proposal = await _create_proposal(svc)
        pid = proposal.proposal_id
        await svc.stake_tokens("0xDUAL", Decimal("100"), 30)
        await _vote(svc, pid, "0xDUAL", voter_id="voter-a")
        await _vote(svc, pid, "0xDUAL", voter_id="voter-b")

    await _end_window(pid)
    async with _svc(chain) as svc:
        closed = await svc.close_proposal(pid)

    # Each vote recorded 200; combined they may count at most the address's
    # current power (200), not 400.
    assert closed.yes_votes == Decimal("200")


@pytest.mark.asyncio
async def test_unreadable_chain_aborts_close() -> None:
    """Fail-closed but retryable: a chain outage at close must not zero real
    votes into a wrongful defeat — the close raises and can be retried."""
    chain = _Chain(balances={"0xSTAYED": 100}, supply={"circulating_ait": "100", "height": 1})
    async with _svc(chain) as svc:
        proposal = await _create_proposal(svc)
        pid = proposal.proposal_id
        await svc.stake_tokens("0xSTAYED", Decimal("100"), 30)
        await _vote(svc, pid, "0xSTAYED")

    await _end_window(pid)
    chain.fail_power = True
    async with _svc(chain) as svc:
        with pytest.raises(ConnectionError):
            await svc.close_proposal(pid)

    stored = await _proposal(pid)
    assert str(stored.status) == "active"
    assert stored.yes_votes == Decimal("200")
