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

The stake/unstake signed-message contract is pinned too: the wallet CLI
signs the *lowercase* spelling of its address while submitting the
checksummed form, so the server must reconstruct ``sign_data`` with the
lowercase spelling — canonicalizing inside the signed message would break
every existing client signature.
"""

from __future__ import annotations

import json
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any
from unittest.mock import Mock

import pytest
from eth_keys import keys
from eth_utils import keccak
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, select

from aitbc_chain.metadata import chain_metadata
from aitbc_chain.models import Account, GovernanceProposal, GovernanceVote, Stake
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


def _sign(message: dict[str, Any], key: keys.PrivateKey) -> str:
    digest = keccak(json.dumps(message, sort_keys=True, separators=(",", ":")).encode())
    return key.sign_msg_hash(digest).to_hex()


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


async def test_vote_route_counts_stakes_of_either_spelling(rpc_db) -> None:
    """Voting power reads every stake spelling — canonical and legacy lowercase."""
    with Session(rpc_db) as session:
        _proposal(session)
        session.add(Stake(chain_id=CHAIN, address=VOTER, amount=500, locked_until=datetime.now(UTC), status="active"))
        session.add(Stake(chain_id=CHAIN, address=VOTER.lower(), amount=300, locked_until=datetime.now(UTC), status="active"))
        session.commit()
    result = await rpc_staking.cast_governance_vote(
        Mock(), {"chain_id": CHAIN, "proposal_id": "p1", "voter_address": VOTER.lower()}
    )
    assert result["voting_power"] == 800


async def test_lowercase_legacy_row_blocks_canonical_revote(rpc_db) -> None:
    """A legacy lowercase row still blocks a re-vote with 400, not a 500 from the index."""
    from fastapi import HTTPException

    with Session(rpc_db) as session:
        _proposal(session)
        session.add(GovernanceVote(chain_id=CHAIN, proposal_id="p1", voter_address=VOTER.lower(), vote_type="against"))
        session.commit()
    with pytest.raises(HTTPException) as exc:
        await rpc_staking.cast_governance_vote(Mock(), {"chain_id": CHAIN, "proposal_id": "p1", "voter_address": VOTER})
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


# --- The signed-message casing contract (stake/unstake) --------------------


async def test_stake_signed_message_keeps_lowercase_spelling(rpc_db, monkeypatch) -> None:
    """The wallet signs ``address.lower()``; the server must reproduce that.

    The stored Stake row and the queued transfer still take the canonical
    spelling — only the reconstructed signed message keeps lowercase.
    """
    staker = VOTER
    queued: dict[str, Any] = {}

    def _queue(**kwargs: Any) -> str:
        queued["tx"] = kwargs
        return "0x" + "ab" * 32

    monkeypatch.setattr(rpc_staking, "validate_chain_id", lambda chain_id: True)
    monkeypatch.setattr(rpc_staking, "stake_escrow_address", lambda: "0x" + "00" * 19 + "01")
    monkeypatch.setattr(rpc_staking, "queue_protocol_transfer", _queue)
    with Session(rpc_db) as session:
        session.add(Account(chain_id=CHAIN, address=staker, balance=10**9, nonce=0))
        session.commit()

    sign_data = {
        "address": staker.lower(),
        "amount": 1000,
        "chain_id": CHAIN,
        "action": "stake",
        "nonce": 0,
        "timestamp": int(time.time()),
    }
    result = await rpc_staking.stake_tokens(
        Mock(),
        {
            "chain_id": CHAIN,
            "address": staker,  # the checksummed spelling the CLI submits
            "amount": 1000,
            "lock_days": 30,
            "nonce": 0,
            "timestamp": sign_data["timestamp"],
            "signature": _sign(sign_data, VOTER_KEY),
        },
    )
    assert result["success"] is True
    with Session(rpc_db) as session:
        stake = session.exec(select(Stake).where(Stake.chain_id == CHAIN)).one()
        assert stake.address == staker
    # The authorization evidence carries the signed message verbatim —
    # lowercase address — while the signer is recorded canonically.
    auth = queued["tx"]["auth"]
    assert auth["message"]["address"] == staker.lower()
    assert auth["signer"] == staker


async def test_stake_signature_over_canonical_spelling_is_rejected(rpc_db, monkeypatch) -> None:
    """Pin the contract: signing the checksummed spelling never verified."""
    from fastapi import HTTPException

    staker = VOTER
    monkeypatch.setattr(rpc_staking, "validate_chain_id", lambda chain_id: True)
    sign_data = {
        "address": staker,  # canonical — NOT what the CLI signs
        "amount": 1000,
        "chain_id": CHAIN,
        "action": "stake",
        "nonce": 0,
        "timestamp": int(time.time()),
    }
    with pytest.raises(HTTPException) as exc:
        await rpc_staking.stake_tokens(
            Mock(),
            {
                "chain_id": CHAIN,
                "address": staker,
                "amount": 1000,
                "lock_days": 30,
                "nonce": 0,
                "timestamp": sign_data["timestamp"],
                "signature": _sign(sign_data, VOTER_KEY),
            },
        )
    assert exc.value.status_code == 403


async def test_unstake_authorizes_against_lowercase_legacy_stake_row(rpc_db, monkeypatch) -> None:
    """Stake rows written before canonical-at-write still authorize their owner."""
    staker = VOTER
    monkeypatch.setattr(rpc_staking, "validate_chain_id", lambda chain_id: True)
    monkeypatch.setattr(rpc_staking, "stake_escrow_address", lambda: "0x" + "00" * 19 + "01")
    monkeypatch.setattr(
        rpc_staking,
        "confirmed_lock_txs",
        lambda session, chain_id, tx_type, key, value: [Mock(tx_hash="0xabc", payload={}, block_height=1)],
    )
    monkeypatch.setattr(rpc_staking, "queue_protocol_transfer", lambda **kwargs: "0x" + "cd" * 32)
    with Session(rpc_db) as session:
        session.add(Account(chain_id=CHAIN, address=staker, balance=10**9, nonce=0))
        # The pre-fix write path stored the lowercase spelling.
        session.add(
            Stake(
                chain_id=CHAIN,
                address=staker.lower(),
                amount=1000,
                locked_until=datetime(2000, 1, 1, tzinfo=UTC),
                status="active",
            )
        )
        session.commit()
        stake_id = session.exec(select(Stake.id).where(Stake.chain_id == CHAIN)).one()

    sign_data = {
        "address": staker.lower(),
        "stake_id": str(stake_id),
        "chain_id": CHAIN,
        "action": "unstake",
        "nonce": 0,
        "timestamp": int(time.time()),
    }
    result = await rpc_staking.unstake_tokens(
        Mock(),
        {
            "chain_id": CHAIN,
            "address": staker,
            "stake_id": str(stake_id),
            "nonce": 0,
            "timestamp": sign_data["timestamp"],
            "signature": _sign(sign_data, VOTER_KEY),
        },
    )
    assert result["success"] is True
    with Session(rpc_db) as session:
        assert session.get(Stake, stake_id).status == "withdrawn"
