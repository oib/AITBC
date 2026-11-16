"""Restart-recovery tests for distributed-consensus persistence (#2164).

``DistributedConsensus`` used to hold nodes, proposals, votes, and history in
process-local dicts, so every agent-coordinator restart wiped consensus state
and replicas diverged. The module now writes through to the shared agent
SQLite DB (``aitbc.db``) via ``ConsensusStore`` and hydrates on init.

These tests point ``AGENT_DB_PATH`` at a tmp file, reset the cached engine,
and construct fresh ``DistributedConsensus(store=ConsensusStore())``
instances to simulate restarts.
"""

from __future__ import annotations

import pytest

from aitbc.db import agent_db

from agent_app.consensus.distributed_consensus import DistributedConsensus
from agent_app.storage.consensus_store import ConsensusStore


@pytest.fixture
def consensus_db(monkeypatch, tmp_path):
    """A fresh agent SQLite DB; the engine is a module global, so reset it."""
    monkeypatch.setenv("AGENT_DB_PATH", str(tmp_path / "consensus.db"))
    monkeypatch.setattr(agent_db, "_engine", None)
    monkeypatch.setattr(agent_db, "_SessionLocal", None)
    agent_db.init_db()
    yield
    agent_db._engine = None
    agent_db._SessionLocal = None


def _node(node_id: str) -> dict:
    return {"node_id": node_id, "endpoint": f"http://{node_id}:9000"}


def test_pending_proposal_and_votes_survive_restart(consensus_db):
    """propose + partial vote → new instance → state intact, vote can finish."""
    first = DistributedConsensus(store=ConsensusStore())
    for nid in ("n1", "n2", "n3"):
        assert first.register_node(_node(nid))["status"] == "success"

    created = first.create_proposal({"proposer_id": "n1", "content": {"task": "t1"}})
    assert created["status"] == "success"
    proposal_id = created["proposal_id"]
    # 3 nodes → majority requires 2 votes; one vote keeps it pending.
    assert first.cast_vote(proposal_id, "n1", True)["status"] == "success"

    # "Restart": a brand-new instance over the same DB.
    second = DistributedConsensus(store=ConsensusStore())
    assert set(second.nodes) == {"n1", "n2", "n3"}
    assert second.nodes["n2"].endpoint == "http://n2:9000"

    status = second.get_proposal_status(proposal_id)
    assert status["status"] == "pending"
    assert status["current_votes"] == {"yes": 1, "no": 0, "total": 1, "details": {"n1": True}}
    assert status["required_votes"] == 2

    # The rehydrated instance can finish the vote and reach the same outcome.
    result = second.cast_vote(proposal_id, "n2", True)
    assert result["status"] == "success"
    # Finalized proposals are cleaned up, exactly like the pre-restart path.
    assert second.get_proposal_status(proposal_id)["status"] == "error"
    assert len(second.consensus_history) == 1
    assert second.consensus_history[0]["approved"] is True
    assert second.consensus_history[0]["votes"] == {"n1": True, "n2": True}


def test_finalized_history_and_statistics_survive_restart(consensus_db):
    """A completed proposal's history row feeds statistics after restart."""
    first = DistributedConsensus(store=ConsensusStore())
    for nid in ("n1", "n2"):
        first.register_node(_node(nid))
    # 2 nodes → majority requires 2 votes; two yes votes approve and finalize.
    proposal_id = first.create_proposal({"proposer_id": "n1", "content": {}})["proposal_id"]
    first.cast_vote(proposal_id, "n1", True)
    first.cast_vote(proposal_id, "n2", True)
    assert first.consensus_history[0]["approved"] is True

    second = DistributedConsensus(store=ConsensusStore())
    # The finalized proposal row is gone (same cleanup as before restart)…
    assert second.get_proposal_status(proposal_id)["status"] == "error"
    # …but its history record and the derived statistics survived.
    stats = second.get_consensus_statistics()
    assert stats["status"] == "success"
    assert stats["total_proposals"] == 1
    assert stats["approved_proposals"] == 1
    assert stats["active_proposals"] == 0
    assert stats["node_participation"]["n1"]["votes_cast"] == 1


def test_node_status_and_algorithm_survive_restart(consensus_db):
    first = DistributedConsensus(store=ConsensusStore())
    first.register_node(_node("n1"))
    first.register_node(_node("n2"))
    assert first.update_node_status("n2", False)["status"] == "success"
    assert first.set_consensus_algorithm("supermajority")["status"] == "success"

    second = DistributedConsensus(store=ConsensusStore())
    assert second.nodes["n2"].is_active is False
    assert second.current_algorithm == "supermajority"
    assert sum(1 for n in second.nodes.values() if n.is_active) == 1


def test_no_store_keeps_pure_in_memory_behavior():
    """``DistributedConsensus()`` without a store must not touch the DB."""
    instance = DistributedConsensus()
    instance.register_node(_node("solo"))
    proposal_id = instance.create_proposal({"proposer_id": "solo", "content": {}})["proposal_id"]
    instance.cast_vote(proposal_id, "solo", True)
    assert instance.get_proposal_status(proposal_id)["status"] == "error"  # finalized+cleaned
    assert instance.consensus_history[0]["approved"] is True
