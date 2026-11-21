"""Tests for #2389: shared island membership state across processes/workers.

``aitbc-blockchain-rpc`` runs ``uvicorn --workers 2`` and ``aitbc-blockchain-node``
is a separate process; ``IslandManager.islands`` must live in a flock-serialized
file beside chain.db (``islands.json``) so join/leave/list/get see the same
memberships everywhere. ``AITBC_ISLAND_STATE_FILE=memory`` (or an explicit
``state_path="memory"``) keeps the legacy per-process behaviour for tests/dev.
Ephemeral runtime state (``island_peers``, ``bridge_requests``,
``active_bridges``) stays per-process.
"""

from __future__ import annotations

import json

import pytest

from aitbc_chain.network.island_manager import IslandManager, IslandStatus


def _mgr(state_file, **kw) -> IslandManager:
    args = {"local_node_id": "node-1", "default_island_id": "default-island", "default_chain_id": "ait-hub"}
    args.update(kw)
    return IslandManager(**args, state_path=state_file)


@pytest.fixture()
def state_file(tmp_path):
    return tmp_path / "islands.json"


def test_second_instance_sees_join(state_file):
    """Simulates the second uvicorn worker: same state file, fresh object."""
    worker_a = _mgr(state_file)
    assert worker_a.join_island("island-uuid-1", "island1", "ait-island1") is True

    worker_b = _mgr(state_file)
    assert worker_b.is_member_of_island("island-uuid-1")
    island = worker_b.get_island_info("island-uuid-1")
    assert island is not None
    assert island.island_name == "island1"
    assert island.chain_ids == ["ait-island1"]
    assert island.status == IslandStatus.ACTIVE


def test_join_then_list_consistent_across_instances(state_file):
    worker_a = _mgr(state_file)
    worker_b = _mgr(state_file)
    worker_a.join_island("island-uuid-1", "island1", ["ait-island1", "ait-island1b"])

    ids_a = {i.island_id for i in worker_a.get_all_islands()}
    ids_b = {i.island_id for i in worker_b.get_all_islands()}
    assert ids_a == ids_b == {"default-island", "island-uuid-1"}


def test_leave_removes_for_both_workers(state_file):
    worker_a = _mgr(state_file)
    worker_b = _mgr(state_file)
    worker_a.join_island("island-uuid-1", "island1", "ait-island1")
    assert worker_b.is_member_of_island("island-uuid-1")

    assert worker_b.leave_island("island-uuid-1") == "left"
    assert not worker_a.is_member_of_island("island-uuid-1")
    assert worker_a.get_island_info("island-uuid-1") is None


def test_duplicate_join_across_workers_rejected(state_file):
    """Two workers racing to join the same island: flock serializes, second sees member."""
    worker_a = _mgr(state_file)
    worker_b = _mgr(state_file)
    assert worker_a.join_island("island-uuid-1", "island1", "ait-island1") is True
    # worker_b joined 'before' seeing A's write would double-register without reload
    assert worker_b.join_island("island-uuid-1", "island1", "ait-island1") is False


def test_default_island_always_present(state_file):
    worker_a = _mgr(state_file, is_hub=True, role="hub")
    worker_b = _mgr(state_file, is_hub=False, role="follower")
    worker_a.join_island("island-uuid-1", "island1", "ait-island1")
    for mgr in (worker_a, worker_b):
        default = mgr.get_island_info("default-island")
        assert default is not None
        assert default.status == IslandStatus.ACTIVE
    assert mgr.leave_island("default-island") == "forbidden_default"


def test_state_survives_restart(state_file):
    worker_a = _mgr(state_file)
    worker_a.join_island("island-uuid-1", "island1", "ait-island1")
    reloaded = _mgr(state_file)
    assert reloaded.is_member_of_island("island-uuid-1")


def test_memory_mode_isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("AITBC_ISLAND_STATE_FILE", "memory")
    a = IslandManager("node-1", "default-island", "ait-hub")
    b = IslandManager("node-1", "default-island", "ait-hub")
    a.join_island("island-uuid-1", "island1", "ait-island1")
    assert not b.is_member_of_island("island-uuid-1")


def test_explicit_memory_state_path_isolated(state_file):
    a = IslandManager("node-1", "default-island", "ait-hub", state_path="memory")
    b = _mgr(state_file)
    a.join_island("island-uuid-1", "island1", "ait-island1")
    assert not b.is_member_of_island("island-uuid-1")
    assert not state_file.exists()


def test_env_state_file_path_used(tmp_path, monkeypatch):
    target = tmp_path / "env-islands.json"
    monkeypatch.setenv("AITBC_ISLAND_STATE_FILE", str(target))
    a = IslandManager("node-1", "default-island", "ait-hub")
    a.join_island("island-uuid-1", "island1", "ait-island1")
    b = IslandManager("node-1", "default-island", "ait-hub")
    assert b.is_member_of_island("island-uuid-1")


def test_corrupt_state_file_recovers(state_file):
    state_file.write_text("{not json")
    mgr = _mgr(state_file)
    # default island still present; mutations work and rewrite a valid file
    assert mgr.get_island_info("default-island") is not None
    mgr.join_island("island-uuid-1", "island1", "ait-island1")
    data = json.loads(state_file.read_text())
    assert "island-uuid-1" in data["islands"]


def test_missing_state_file_created_on_join(state_file):
    mgr = _mgr(state_file)
    assert not state_file.exists()
    mgr.join_island("island-uuid-1", "island1", "ait-island1")
    assert state_file.exists()


def test_peer_count_not_persisted(state_file):
    """peer_count is derived from per-process island_peers — a sibling worker
    must not inherit a stale count."""
    worker_a = _mgr(state_file)
    worker_a.join_island("island-uuid-1", "island1", "ait-island1")
    worker_a.add_island_peer("island-uuid-1", "peer-x")
    assert worker_a.get_island_info("island-uuid-1").peer_count == 1

    worker_b = _mgr(state_file)
    assert worker_b.get_island_info("island-uuid-1").peer_count == 0
    # and the file carries no peer_count key
    data = json.loads(state_file.read_text())
    assert "peer_count" not in data["islands"]["island-uuid-1"]


def test_health_check_inactive_persisted(state_file):
    """ACTIVE→INACTIVE after 600s without peers is written through the shared
    store so sibling workers observe it."""
    import time

    worker_a = _mgr(state_file)
    worker_a.join_island("island-uuid-1", "island1", "ait-island1")
    # age the membership past the 600s horizon, then run one sweep
    with worker_a._state_transaction():
        worker_a.islands["island-uuid-1"].joined_at = time.time() - 700
    worker_b = _mgr(state_file)
    worker_a._mark_island_inactive("island-uuid-1", worker_a.islands["island-uuid-1"].joined_at, time.time())
    assert worker_b.get_island_info("island-uuid-1").status == IslandStatus.INACTIVE


def test_request_bridge_sees_sibling_join(state_file):
    worker_a = _mgr(state_file)
    worker_b = _mgr(state_file)
    worker_a.join_island("island-uuid-1", "island1", "ait-island1")
    # worker_b must not offer a bridge to an island it is already a member of
    assert worker_b.request_bridge("island-uuid-1") == ""
