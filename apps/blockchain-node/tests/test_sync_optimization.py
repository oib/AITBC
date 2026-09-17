"""Integration tests for v0.6.2 sync optimization features (parallel sync, delta sync, peer tracking)."""

from __future__ import annotations

from contextlib import contextmanager

import pytest
from aitbc_chain.sync import ChainSync
from sqlmodel import Session, create_engine

from aitbc_chain.metadata import chain_metadata


@pytest.fixture
def db_engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/test_sync_opt.db", echo=False)
    chain_metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def session_factory(db_engine):
    @contextmanager
    def _factory():
        with Session(db_engine) as session:
            yield session

    return _factory


@pytest.fixture
def sync(session_factory):
    """Create a ChainSync instance with signature validation disabled."""
    return ChainSync(session_factory, chain_id="test", validate_signatures=False)


class TestPeerCapabilityTracker:
    """Test peer capability tracking in ChainSync."""

    def test_register_peer_updates_tracker(self, sync):
        sync.register_sync_peer("peer1", "http://peer1:8202", (0, 1000))
        peer = sync._peer_tracker.get_peer("peer1")
        assert peer is not None
        assert peer.rpc_url == "http://peer1:8202"
        assert peer.block_range == (0, 1000)

    def test_update_peer_capability(self, sync):
        sync.register_sync_peer("peer1", "http://peer1:8202", (0, 500))
        sync.update_peer_capability("peer1", (0, 1000))
        peer = sync._peer_tracker.get_peer("peer1")
        assert peer.block_range == (0, 1000)

    def test_record_success_increases_reputation(self, sync):
        sync.register_sync_peer("peer1", "http://peer1:8202", (0, 1000))
        # Lower reputation first (it starts at 1.0 which is the max)
        sync._peer_tracker.record_failure("peer1", "warmup failure")
        lowered = sync._peer_tracker.get_peer("peer1").reputation
        sync._peer_tracker.record_success("peer1", 50)
        assert sync._peer_tracker.get_peer("peer1").reputation > lowered

    def test_record_failure_decreases_reputation(self, sync):
        sync.register_sync_peer("peer1", "http://peer1:8202", (0, 1000))
        initial = sync._peer_tracker.get_peer("peer1").reputation
        sync._peer_tracker.record_failure("peer1", "timeout")
        assert sync._peer_tracker.get_peer("peer1").reputation < initial


class TestParallelSync:
    """Test parallel block fetching from multiple peers."""


class TestDeltaSync:
    """Test delta-based state synchronization."""

    def test_chain_parameters_upserted_from_peer(self, session_factory):
        """chain_parameter rows are consensus state outside the account state
        root — the sync must carry them or gates like governance_executors
        exist only on the node that served the execute call."""
        from aitbc_chain.base_models import ChainParameter
        from aitbc_chain.sync_state import _upsert_chain_parameters
        from sqlmodel import select

        params = [
            {
                "parameter": "governance_executors",
                "value": "0x02B8F2C61DB19B04aB68cfb43d0605E63dE74c5B",
                "proposal_id": "p1",
            }
        ]
        with session_factory() as s:
            assert _upsert_chain_parameters(s, "test", params) == 1
            s.commit()
        with session_factory() as s:
            row = s.exec(select(ChainParameter).where(ChainParameter.chain_id == "test")).one()
            assert row.parameter == "governance_executors"
            assert row.value == "0x02B8F2C61DB19B04aB68cfb43d0605E63dE74c5B"

        # Second sync with a changed value updates in place — no duplicate row
        params[0]["value"] = "0x1111111111111111111111111111111111111111"
        with session_factory() as s:
            assert _upsert_chain_parameters(s, "test", params) == 1
            s.commit()
        with session_factory() as s:
            rows = s.exec(select(ChainParameter).where(ChainParameter.chain_id == "test")).all()
            assert len(rows) == 1
            assert rows[0].value == "0x1111111111111111111111111111111111111111"

    def test_aux_state_upserted_from_peer(self, session_factory):
        """stake/bond/governance side-effect rows live outside the account
        state root — without sync propagation a follower's governance/vote
        reads zero power and bond gates diverge per node."""
        from datetime import UTC, datetime, timedelta

        from aitbc_chain.aux_state import upsert_aux_rows
        from aitbc_chain.base_models import Bond, GovernanceProposal, GovernanceVote, Stake
        from sqlmodel import select

        now = datetime.now(UTC)
        payload = {
            "stakes": [
                {
                    "id": 7,
                    "address": "0x02b8f2c61db19b04ab68cfb43d0605e63de74c5b",
                    "amount": 1000,
                    "locked_until": (now + timedelta(days=30)).isoformat(),
                    "status": "active",
                    "created_at": now.isoformat(),
                    "updated_at": now.isoformat(),
                }
            ],
            "bonds": [
                {
                    "bond_id": "bond_0xabc_1",
                    "provider": "0x02b8f2c61db19b04ab68cfb43d0605e63de74c5b",
                    "amount": 500,
                    "locked_until": (now + timedelta(days=7)).isoformat(),
                    "status": "active",
                    "created_tx_hash": "0xdeadbeef",
                }
            ],
            "governance_proposals": [
                {
                    "proposal_id": "prop-1",
                    "proposer_address": "0x02b8f2c61db19b04ab68cfb43d0605e63de74c5b",
                    "title": "t",
                    "description": "d",
                    "status": "active",
                    "votes_for": 3,
                    "voting_starts": now.isoformat(),
                    "voting_ends": (now + timedelta(days=3)).isoformat(),
                    "execution_payload": {"k": "v"},
                }
            ],
            "governance_votes": [
                {
                    "proposal_id": "prop-1",
                    "voter_address": "0x02b8f2c61db19b04ab68cfb43d0605e63de74c5b",
                    "vote_type": "for",
                    "voting_power": 1000,
                    "created_at": now.isoformat(),
                }
            ],
        }
        with session_factory() as s:
            counts = upsert_aux_rows(s, "test", payload)
            assert counts == {"stakes": 1, "bonds": 1, "governance_proposals": 1, "governance_votes": 1}
            s.commit()

        checksummed = "0x02B8F2C61DB19B04aB68cfb43d0605E63dE74c5B"
        with session_factory() as s:
            stake = s.exec(select(Stake).where(Stake.chain_id == "test")).one()
            assert stake.id == 7 and stake.address == checksummed and stake.amount == 1000
            bond = s.exec(select(Bond).where(Bond.chain_id == "test")).one()
            assert bond.bond_id == "bond_0xabc_1" and bond.provider == checksummed
            prop = s.exec(select(GovernanceProposal).where(GovernanceProposal.chain_id == "test")).one()
            assert prop.votes_for == 3 and prop.execution_payload == {"k": "v"}
            vote = s.exec(select(GovernanceVote).where(GovernanceVote.chain_id == "test")).one()
            assert vote.voting_power == 1000 and vote.voter_address == checksummed

        # Second sync updates in place — keyed upsert, no duplicates.
        payload["stakes"][0]["status"] = "withdrawn"
        payload["governance_votes"][0]["voting_power"] = 2000
        with session_factory() as s:
            upsert_aux_rows(s, "test", payload)
            s.commit()
        with session_factory() as s:
            stakes = s.exec(select(Stake).where(Stake.chain_id == "test")).all()
            assert len(stakes) == 1 and stakes[0].status == "withdrawn"
            votes = s.exec(select(GovernanceVote).where(GovernanceVote.chain_id == "test")).all()
            assert len(votes) == 1 and votes[0].voting_power == 2000

    def test_aux_state_missing_key_skipped(self, session_factory):
        from aitbc_chain.aux_state import upsert_aux_rows
        from aitbc_chain.base_models import Stake
        from sqlmodel import select

        with session_factory() as s:
            counts = upsert_aux_rows(s, "test", {"stakes": [{"address": "0x02B8F2C61DB19B04aB68cfb43d0605E63dE74c5B", "amount": 5}]})
            assert counts["stakes"] == 0
            s.commit()
        with session_factory() as s:
            assert s.exec(select(Stake).where(Stake.chain_id == "test")).all() == []

    def test_aux_state_serialize_window(self, session_factory):
        """Delta path ships only rows touched at-or-after the cutoff; the
        snapshot path ships everything."""
        from datetime import UTC, datetime, timedelta

        from aitbc_chain.aux_state import serialize_aux_rows
        from aitbc_chain.base_models import Stake

        now = datetime.now(UTC)
        with session_factory() as s:
            old = Stake(
                chain_id="test",
                address="0x02B8F2C61DB19B04aB68cfb43d0605E63dE74c5B",
                amount=1,
                locked_until=now + timedelta(days=1),
                status="active",
            )
            old.updated_at = now - timedelta(hours=2)
            s.add(old)
            recent = Stake(
                chain_id="test",
                address="0x02B8F2C61DB19B04aB68cfb43d0605E63dE74c5B",
                amount=2,
                locked_until=now + timedelta(days=1),
                status="active",
            )
            recent.updated_at = now
            s.add(recent)
            s.commit()

        cutoff = now - timedelta(minutes=15)
        with session_factory() as s:
            delta = serialize_aux_rows(s, "test", changed_since=cutoff)
            assert [r["amount"] for r in delta["tables"]["stakes"]] == [2]
            assert delta["truncated"] is False
            full = serialize_aux_rows(s, "test")
            assert sorted(r["amount"] for r in full["tables"]["stakes"]) == [1, 2]
            capped = serialize_aux_rows(s, "test", max_rows=1)
            assert capped["truncated"] is True
