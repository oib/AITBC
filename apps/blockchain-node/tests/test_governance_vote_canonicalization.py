"""Canonical address casing at write + case-insensitive vote uniqueness.

``cast_governance_vote`` lowercased ``voter_address`` before storing while
peer aux upserts arrived checksummed, so one voter could hold two rows for
the same ``(chain_id, proposal_id)`` — the five lowercase twins node2
carried until the 2026-09-29 dedupe, which made
``GET /governance/proposal/{id}`` answer ``total_votes=10`` there against 5
everywhere else.

Two layers now stop it:

  * ``rpc.staking._request_address`` canonicalizes every request-supplied
    address the staking/governance routes store — EIP-55 for 40-hex input
    (with or without the ``0x`` prefix), lowercased passthrough otherwise.
  * ``ux_governance_vote_voter_nocase`` — a UNIQUE INDEX over
    ``(chain_id, proposal_id, voter_address COLLATE NOCASE)`` applied
    per-host (SQLModel does not backfill indexes onto existing DBs) — makes
    a casing twin physically impossible even if a future write path forgets
    to canonicalize.

The stake/unstake signed-message contract the wallet CLI used (signing the
*lowercase* spelling while submitting the checksummed form) still holds on
the v17-revived routes — the handlers reconstruct the message with the
lowercase spelling exactly as before, gated on the
``protocol_transfers_active`` activation pin; see ``rpc/retired.py``.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from unittest.mock import Mock

import pytest
from eth_keys import keys
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, select

from aitbc_chain.metadata import chain_metadata
from aitbc_chain.models import GovernanceProposal, GovernanceVote, Stake
from aitbc_chain.rpc import staking as rpc_staking

CHAIN = "test"
VOTER_KEY = keys.PrivateKey(b"\x33" * 32)
VOTER = VOTER_KEY.public_key.to_checksum_address()

# The per-host index from the v0.25.8 schema-migration note — verbatim.
NOCASE_INDEX_SQL = (
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_governance_vote_voter_nocase "
    "ON governance_vote(chain_id, proposal_id, voter_address COLLATE NOCASE)"
)


@pytest.fixture(autouse=True)
def _no_rate_limit(monkeypatch) -> None:
    monkeypatch.setenv("AITBC_ENABLE_RATE_LIMITING", "false")


@pytest.fixture
def engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    chain_metadata.create_all(engine)
    yield engine
    engine.dispose()


def _scope_for(engine):
    @contextmanager
    def _session_scope(*args, **kwargs):
        with Session(engine) as session:
            yield session

    return _session_scope


@pytest.fixture
def rpc_db(engine, monkeypatch):
    """Point the staking module's session_scope at the in-memory engine."""
    monkeypatch.setattr(rpc_staking, "session_scope", _scope_for(engine))
    return engine


def _proposal(session: Session, proposal_id: str = "p1") -> GovernanceProposal:
    proposal = GovernanceProposal(
        chain_id=CHAIN,
        proposal_id=proposal_id,
        proposer_address=VOTER,
        title="t",
        description="d",
        status="active",
        voting_starts=datetime.now(UTC),
        voting_ends=datetime.now(UTC),
    )
    session.add(proposal)
    session.commit()
    return proposal


# --- _request_address ------------------------------------------------------


def test_request_address_canonicalizes_every_spelling() -> None:
    body = VOTER[2:]
    for spelling in (VOTER, VOTER.lower(), body, body.upper()):
        assert rpc_staking._request_address(spelling) == VOTER


def test_request_address_passes_non_addresses_through_lowercased() -> None:
    """Same contract the old inline blocks had: non-0x input is prefixed
    first, then lowercased — so aliases keep their historical spelling."""
    assert rpc_staking._request_address("Genesis") == "0xgenesis"


# --- cast_governance_vote: canonicalize at write ---------------------------


@pytest.mark.asyncio
async def test_vote_route_stores_canonical_voter_address(rpc_db) -> None:
    with Session(rpc_db) as session:
        _proposal(session)
    result = await rpc_staking.cast_governance_vote(
        Mock(), {"chain_id": CHAIN, "proposal_id": "p1", "voter_address": VOTER.lower(), "vote_type": "for"}
    )
    assert result["success"] is True
    assert result["voter_address"] == VOTER
    with Session(rpc_db) as session:
        vote = session.exec(select(GovernanceVote).where(GovernanceVote.proposal_id == "p1")).one()
        assert vote.voter_address == VOTER


@pytest.mark.asyncio
async def test_vote_route_counts_stakes_of_either_spelling(rpc_db) -> None:
    """Voting power reads every stake spelling — canonical and legacy lowercase."""
    with Session(rpc_db) as session:
        _proposal(session)
        session.add(Stake(chain_id=CHAIN, address=VOTER, amount=500, locked_until=datetime.now(UTC), status="active"))
        session.add(Stake(chain_id=CHAIN, address=VOTER.lower(), amount=300, locked_until=datetime.now(UTC), status="active"))
        session.commit()
    result = await rpc_staking.cast_governance_vote(
        Mock(), {"chain_id": CHAIN, "proposal_id": "p1", "voter_address": VOTER.lower(), "vote_type": "for"}
    )
    assert result["voting_power"] == 800


@pytest.mark.asyncio
async def test_lowercase_legacy_row_blocks_canonical_revote(rpc_db) -> None:
    """A legacy lowercase row still blocks a re-vote with 400, not a 500 from the index."""
    from fastapi import HTTPException

    with Session(rpc_db) as session:
        _proposal(session)
        session.add(GovernanceVote(chain_id=CHAIN, proposal_id="p1", voter_address=VOTER.lower(), vote_type="against"))
        session.commit()
    with pytest.raises(HTTPException) as exc:
        await rpc_staking.cast_governance_vote(
            Mock(), {"chain_id": CHAIN, "proposal_id": "p1", "voter_address": VOTER, "vote_type": "for"}
        )
    assert exc.value.status_code == 400
    assert "Already voted" in exc.value.detail


# --- The per-host NOCASE unique index --------------------------------------


def test_nocase_unique_index_rejects_casing_twin(engine) -> None:
    """The belt under canonicalize-at-write: a twin insert must fail, not diverge."""
    with Session(engine) as session:
        session.execute(text(NOCASE_INDEX_SQL))
        session.add(GovernanceVote(chain_id=CHAIN, proposal_id="p1", voter_address=VOTER, vote_type="for"))
        session.commit()
        session.add(GovernanceVote(chain_id=CHAIN, proposal_id="p1", voter_address=VOTER.lower(), vote_type="against"))
        with pytest.raises(IntegrityError):
            session.commit()


def test_nocase_index_scan_finds_no_dupes_when_clean(engine) -> None:
    """The pre-index gate applied on each host must answer zero on clean data."""
    with Session(engine) as session:
        session.add(GovernanceVote(chain_id=CHAIN, proposal_id="p1", voter_address=VOTER, vote_type="for"))
        session.commit()
        dupes = session.execute(
            text(
                "SELECT chain_id, proposal_id, voter_address COLLATE NOCASE, COUNT(*) "
                "FROM governance_vote GROUP BY 1,2,3 HAVING COUNT(*)>1"
            )
        ).all()
        assert dupes == []


@pytest.mark.asyncio
async def test_vote_route_rejects_missing_or_unknown_vote_type(rpc_db) -> None:
    """#651 remnant: vote_data.get("vote_type", "for") silently cast FOR.
    Missing or unknown values must 400, never default."""
    from fastapi import HTTPException

    with Session(rpc_db) as session:
        _proposal(session)
    for bad in (None, "yes", ""):
        body = {"chain_id": CHAIN, "proposal_id": "p1", "voter_address": VOTER, "reason": "x"}
        if bad is not None:
            body["vote_type"] = bad
        with pytest.raises(HTTPException) as exc:
            await rpc_staking.cast_governance_vote(Mock(), body)
        assert exc.value.status_code == 400
