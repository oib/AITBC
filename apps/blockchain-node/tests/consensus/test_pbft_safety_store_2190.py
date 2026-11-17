"""#2190: PBFT commit-lock / view-change persistence must not need a second
chain.db writer.  The pre-fix path (``save_state`` from inside the proposer's
write transaction) self-deadlocked on a FILE-backed sqlite — the existing
tests use in-memory shared connections and could not see it."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

import pytest

from aitbc_chain.config import settings
from aitbc_chain.consensus.multi_validator_poa import MultiValidatorPoA, ValidatorRole

HASH_A = "0x" + "a" * 64
HASH_B = "0x" + "b" * 64
SEQ = 40000


def _chain_db(chain_id: str):
    from aitbc_chain.database import get_engine
    from aitbc_chain.metadata import chain_metadata

    Path(settings.get_db_path(chain_id)).parent.mkdir(parents=True, exist_ok=True)
    engine = get_engine(chain_id, create_ok=True)
    chain_metadata.create_all(engine)
    return engine


def _make(chain_id: str) -> MultiValidatorPoA:
    _chain_db(chain_id)
    consensus = MultiValidatorPoA(chain_id)
    for i in range(4):
        addr = f"0x{i:040x}"
        consensus.add_validator(addr, 1000.0)
        consensus.validators[addr].role = ValidatorRole.PROPOSER
    return consensus


def _hold_write_lock(chain_id: str) -> sqlite3.Connection:
    """Open a second connection holding the sqlite write lock, like the
    proposer's outer session after its first flush."""
    conn = sqlite3.connect(settings.get_db_path(chain_id), timeout=0.2, isolation_level=None)
    conn.execute("BEGIN IMMEDIATE")
    return conn


class TestNoChainDbWriter:
    def test_vc_floor_raise_succeeds_while_chain_db_write_lock_is_held(self):
        chain = "safety-2190-a"
        consensus = _make(chain)
        assert consensus.save_state() is True
        conn = _hold_write_lock(chain)
        try:
            assert consensus.pbft_vc_floor_raise(SEQ, 3) is True
            assert consensus.pbft_vc_floor(SEQ) == 3
        finally:
            conn.rollback()
            conn.close()

    def test_commit_lock_arm_succeeds_while_chain_db_write_lock_is_held(self):
        chain = "safety-2190-b"
        consensus = _make(chain)
        assert consensus.save_state() is True
        conn = _hold_write_lock(chain)
        try:
            assert consensus.pbft_commit_lock_arm(SEQ, HASH_A) is True
            assert consensus.pbft_commit_lock_get(SEQ) == HASH_A
        finally:
            conn.rollback()
            conn.close()

    def test_save_state_itself_still_needs_the_db(self):
        """Control: the held lock really blocks a chain.db writer, so the two
        tests above prove the store bypasses it rather than the lock being a no-op."""
        chain = "safety-2190-c"
        consensus = _make(chain)
        assert consensus.save_state() is True
        conn = _hold_write_lock(chain)
        try:
            from aitbc_chain.database import get_engine

            get_engine(chain).dispose()
            with sqlite3.connect(settings.get_db_path(chain), timeout=0.2) as other:
                with pytest.raises(sqlite3.OperationalError, match="locked"):
                    other.execute("UPDATE consensus_state SET current_view = current_view")
        finally:
            conn.rollback()
            conn.close()


class TestDurability:
    def test_records_survive_a_fresh_instance(self):
        chain = "safety-2190-d"
        consensus = _make(chain)
        assert consensus.save_state() is True
        assert consensus.pbft_vc_floor_raise(SEQ, 5) is True
        assert consensus.pbft_commit_lock_arm(SEQ, HASH_A) is True
        reborn = MultiValidatorPoA(chain)
        assert reborn.pbft_vc_floor(SEQ) == 5
        assert reborn.pbft_commit_lock_get(SEQ) == HASH_A

    def test_failed_replace_keeps_previous_file_and_rolls_back_memory(self, monkeypatch):
        chain = "safety-2190-e"
        consensus = _make(chain)
        assert consensus.save_state() is True
        assert consensus.pbft_vc_floor_raise(SEQ, 2) is True
        before = consensus._pbft_safety_store.path.read_text()

        def boom(*_a, **_k):
            raise OSError("disk full")

        monkeypatch.setattr(os, "replace", boom)
        assert consensus.pbft_vc_floor_raise(SEQ, 9) is False
        monkeypatch.undo()
        assert consensus.pbft_vc_floor(SEQ) == 2
        assert consensus._pbft_safety_store.path.read_text() == before
        assert not consensus._pbft_safety_store.path.with_name("pbft_safety.json.tmp").exists()

    def test_pruning_below_new_sequence(self):
        chain = "safety-2190-f"
        consensus = _make(chain)
        assert consensus.save_state() is True
        assert consensus.pbft_vc_floor_raise(SEQ, 1) is True
        assert consensus.pbft_vc_floor_raise(SEQ + 1, 1) is True
        reborn = MultiValidatorPoA(chain)
        assert reborn.pbft_vc_floor(SEQ + 1) == 1


class TestLoadPrecedence:
    def test_file_beats_stale_db_column(self):
        chain = "safety-2190-g"
        consensus = _make(chain)
        assert consensus.pbft_vc_floor_raise(SEQ, 1) is True
        assert consensus.save_state() is True  # mirror: DB column now floor=1
        assert consensus.pbft_vc_floor_raise(SEQ, 7) is True  # file only
        assert MultiValidatorPoA(chain).pbft_vc_floor(SEQ) == 7

    def test_no_file_falls_back_to_db_column(self):
        chain = "safety-2190-h"
        consensus = _make(chain)
        assert consensus.pbft_vc_floor_raise(SEQ, 4) is True
        assert consensus.save_state() is True
        consensus._pbft_safety_store.path.unlink()
        assert MultiValidatorPoA(chain).pbft_vc_floor(SEQ) == 4

    def test_graceful_save_state_mirrors_memory_into_db(self):
        chain = "safety-2190-i"
        consensus = _make(chain)
        assert consensus.pbft_commit_lock_arm(SEQ, HASH_B) is True
        assert consensus.save_state() is True
        from aitbc_chain.base_models import ConsensusState
        from aitbc_chain.database import session_scope

        with session_scope(chain) as session:
            row = session.query(ConsensusState).filter_by(chain_id=chain).first()
            assert row is not None
            assert json.loads(row.pbft_commit_locks_json) == {str(SEQ): HASH_B}

    def test_corrupt_file_fails_closed(self):
        chain = "safety-2190-j"
        consensus = _make(chain)
        assert consensus.save_state() is True
        assert consensus.pbft_vc_floor_raise(SEQ, 2) is True
        consensus._pbft_safety_store.path.write_text("{not json")
        reborn = MultiValidatorPoA(chain)
        assert reborn._pbft_vc_corrupt is True
        assert reborn.pbft_vc_floor_raise(SEQ, 9) is False
