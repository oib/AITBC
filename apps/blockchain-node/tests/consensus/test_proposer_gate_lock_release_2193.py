"""#2193 F2 — the proposer must not hold chain.db's write lock across the PBFT/attestation wait.

The proposal's single session applies the txs (flush = write lock) and then waits up to
``pbft_view_change_timeout`` + attestation collection for the mesh. SQLite WAL has one writer,
so every other chain.db writer (the block-import path) stalls ``busy_timeout`` and dies with
``database is locked``. Behind ``proposer_release_write_lock_during_gates`` (default OFF) the
proposer rolls back before the wait and, once the gates pass, re-applies the same txs on a fresh
transaction and requires a byte-identical block hash before committing. Local-only: the block
bytes are unchanged, so there is no consensus rule and no height gate.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from aitbc_chain.config import settings
from aitbc_chain.consensus.poa import PoAProposer
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.metrics import metrics_registry
from aitbc_chain.models import Block
from sqlalchemy import event
from sqlalchemy.pool import NullPool
from sqlmodel import create_engine

CHAIN = "bc-2"
NOW = datetime(2026, 11, 18, 12, 0, 0, tzinfo=UTC)


def _blk(height: int, h: str, parent: str) -> Block:
    return Block(
        chain_id=CHAIN,
        height=height,
        hash=h,
        parent_hash=parent,
        proposer="0xprop",
        timestamp=NOW.replace(tzinfo=None),
        tx_count=0,
        state_root="0x00",
        bridge_state_root="0x00",
        aux_state_root="",
        signature="sig",
    )


@pytest.fixture(autouse=True)
def _reset_metrics():
    metrics_registry.reset()


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "chain.db"


@pytest.fixture
def engine(db_path):
    eng = create_engine(f"sqlite:///{db_path}", poolclass=NullPool)

    @event.listens_for(eng, "connect")
    def _wal(dbapi_conn, _rec):  # noqa: ANN001
        dbapi_conn.execute("PRAGMA journal_mode=WAL")

    chain_metadata.create_all(eng)
    return eng


@pytest.fixture
def session(engine):
    from aitbc_chain.database import prod_parity_sessionmaker

    with prod_parity_sessionmaker(bind=engine)() as s:
        s.add(_blk(1, "0xparent", "0x0"))
        s.commit()
        yield s


@pytest.fixture
def proposer():
    p = object.__new__(PoAProposer)
    p._logger = logging.getLogger("test2193")
    p._config = SimpleNamespace(chain_id=CHAIN)
    return p


def _tx(h: str):
    return SimpleNamespace(tx_hash=h, content={"from": "a", "to": "b"})


class _Calls:
    """Records what the re-apply stage did and lets a test steer its outcome."""

    def __init__(self, proposer, monkeypatch, *, hash2="0xhash", ok=True, processed=("t1",), rejected=()):
        self.events: list[str] = []
        self.args: list[tuple] = []
        self.hash2 = hash2
        self.ok = ok
        self.processed = list(processed)
        self.rejected = list(rejected)

        def _process(session, pending, account_map, existing_map, height, ts, rejected_out=None):
            self.events.append("process")
            self.args.append((list(pending), dict(account_map), dict(existing_map), height, ts))
            if rejected_out is not None:
                rejected_out.extend((_tx(h), "bad") for h in self.rejected)
            return [_tx(h) for h in self.processed], set(), self.ok

        def _assemble(session, height, parent, ts, processed, proposer_id):
            self.events.append("assemble")
            return SimpleNamespace(hash=self.hash2), self.hash2

        def _persist(session, rejected, height, ts, commit=True):
            self.events.append(f"persist_rejected:{commit}:{len(rejected)}")

        monkeypatch.setattr(proposer, "_process_proposal_txs", _process)
        monkeypatch.setattr(proposer, "_assemble_proposal_block", _assemble)
        monkeypatch.setattr(proposer, "_persist_rejected_txs", _persist)


def _finish(proposer, session, plan, **over):
    kw = {
        "next_height": 2,
        "parent_hash": "0xparent",
        "timestamp": NOW,
        "proposer": "0xprop",
        "block_hash": "0xhash",
        "processed_txs": [_tx("t1")],
        "rejected_txs": [],
    }
    kw.update(over)
    return proposer._gate_release_finish(session, plan, **kw)


def test_flag_defaults_off():
    assert settings.proposer_release_write_lock_during_gates is False


def test_plan_is_none_when_flag_off(proposer, monkeypatch):
    monkeypatch.setattr(settings, "proposer_release_write_lock_during_gates", False)
    assert proposer._gate_release_plan([_tx("t1")], {}, {}) is None


def test_plan_snapshots_the_maps_the_apply_path_mutates(proposer, monkeypatch):
    """The apply path writes existing_tx_map/account_map; the re-apply must see the pre-apply copy."""
    monkeypatch.setattr(settings, "proposer_release_write_lock_during_gates", True)
    existing, accounts = {"t0": 5}, {"a": object()}
    plan = proposer._gate_release_plan([_tx("t1")], accounts, existing)
    existing["t1"] = 2  # what _seq_apply_and_record does
    accounts["b"] = object()
    assert plan.existing_tx_map == {"t0": 5}
    assert set(plan.account_map) == {"a"}


def test_begin_frees_the_write_lock_for_a_second_writer(proposer, session, db_path, monkeypatch):
    """Regression for #2190/#2193: a flushed proposal holds the WAL write lock until begin()."""
    monkeypatch.setattr(settings, "proposer_release_write_lock_during_gates", True)
    plan = proposer._gate_release_plan([], {}, {})
    session.add(_blk(2, "0xhash", "0xparent"))
    session.flush()  # write lock now held by the proposal session

    other = sqlite3.connect(str(db_path), timeout=0.05)
    with pytest.raises(sqlite3.OperationalError, match="locked"):
        other.execute("BEGIN IMMEDIATE")
    other.close()

    proposer._gate_release_begin(session, plan)

    other = sqlite3.connect(str(db_path), timeout=0.05)
    other.execute("BEGIN IMMEDIATE")  # no longer blocked
    other.rollback()
    other.close()
    assert metrics_registry._counters["proposer_gate_lock_released_total"] == 1


def test_begin_is_a_noop_without_a_plan(proposer, session, db_path):
    session.add(_blk(2, "0xhash", "0xparent"))
    session.flush()
    proposer._gate_release_begin(session, None)
    other = sqlite3.connect(str(db_path), timeout=0.05)
    with pytest.raises(sqlite3.OperationalError, match="locked"):
        other.execute("BEGIN IMMEDIATE")
    other.close()


def test_finish_without_a_plan_is_ok_and_touches_nothing(proposer, session, monkeypatch):
    calls = _Calls(proposer, monkeypatch)
    assert _finish(proposer, session, None) == "ok"
    assert calls.events == []


def test_finish_reapplies_and_accepts_an_identical_hash(proposer, session, monkeypatch):
    monkeypatch.setattr(settings, "proposer_release_write_lock_during_gates", True)
    plan = proposer._gate_release_plan([_tx("t1")], {"a": 1}, {"t0": 5})
    calls = _Calls(proposer, monkeypatch)
    assert _finish(proposer, session, plan) == "ok"
    assert calls.events == ["process", "persist_rejected:False:0", "assemble"]
    pending, accounts, existing, height, ts = calls.args[0]
    assert [t.tx_hash for t in pending] == ["t1"] and accounts == {"a": 1} and existing == {"t0": 5}
    assert (height, ts) == (2, NOW)  # same inputs as the first apply
    assert "proposer_gate_reapply_mismatch_total" not in metrics_registry._counters


def test_finish_resets_the_replay_cache_before_reapplying(proposer, session, monkeypatch):
    """The StateTransition singleton remembers applied tx hashes; without a reset the re-apply says 'replay attack'."""
    from aitbc_chain.consensus import poa as _poa

    monkeypatch.setattr(settings, "proposer_release_write_lock_during_gates", True)
    plan = proposer._gate_release_plan([_tx("t1")], {}, {})
    st = _poa.get_state_transition()
    st._processed_tx_hashes.add("t1")
    calls = _Calls(proposer, monkeypatch)
    seen = {}
    orig = proposer._process_proposal_txs

    def _spy(*a, **k):
        seen["cache"] = set(st._processed_tx_hashes)
        return orig(*a, **k)

    monkeypatch.setattr(proposer, "_process_proposal_txs", _spy)
    assert _finish(proposer, session, plan) == "ok"
    assert seen["cache"] == set()
    assert calls.events


def test_finish_aborts_on_hash_mismatch_and_never_commits_a_different_block(proposer, session, monkeypatch):
    monkeypatch.setattr(settings, "proposer_release_write_lock_during_gates", True)
    plan = proposer._gate_release_plan([_tx("t1")], {}, {})
    _Calls(proposer, monkeypatch, hash2="0xDIFFERENT")
    assert _finish(proposer, session, plan) == "abort"
    assert metrics_registry._counters["proposer_gate_reapply_mismatch_total"] == 1


def test_finish_aborts_when_the_processed_set_differs(proposer, session, monkeypatch):
    monkeypatch.setattr(settings, "proposer_release_write_lock_during_gates", True)
    plan = proposer._gate_release_plan([_tx("t1"), _tx("t2")], {}, {})
    _Calls(proposer, monkeypatch, processed=("t2",))  # same hash by construction, different txs
    assert _finish(proposer, session, plan) == "abort"
    assert metrics_registry._counters["proposer_gate_reapply_mismatch_total"] == 1


def test_finish_aborts_when_the_rejected_set_differs(proposer, session, monkeypatch):
    monkeypatch.setattr(settings, "proposer_release_write_lock_during_gates", True)
    plan = proposer._gate_release_plan([_tx("t1")], {}, {})
    _Calls(proposer, monkeypatch, rejected=("tx9",))
    assert _finish(proposer, session, plan, rejected_txs=[]) == "abort"


def test_finish_aborts_when_the_reapply_itself_fails(proposer, session, monkeypatch):
    monkeypatch.setattr(settings, "proposer_release_write_lock_during_gates", True)
    plan = proposer._gate_release_plan([_tx("t1")], {}, {})
    _Calls(proposer, monkeypatch, ok=False)
    assert _finish(proposer, session, plan) == "abort"
    assert metrics_registry._counters["proposer_gate_reapply_mismatch_total"] == 1


def test_finish_aborts_when_the_head_moved_to_a_rival(proposer, session, monkeypatch):
    """The import path sealed a *different* block at our height while we waited — never commit on top of it."""
    monkeypatch.setattr(settings, "proposer_release_write_lock_during_gates", True)
    plan = proposer._gate_release_plan([_tx("t1")], {}, {})
    session.add(_blk(2, "0xrival", "0xparent"))
    session.commit()
    calls = _Calls(proposer, monkeypatch)
    assert _finish(proposer, session, plan) == "abort"
    assert calls.events == []  # no re-apply on a moved head
    assert metrics_registry._counters["proposer_gate_head_moved_total"] == 1


def test_finish_aborts_when_the_parent_changed(proposer, session, monkeypatch):
    monkeypatch.setattr(settings, "proposer_release_write_lock_during_gates", True)
    plan = proposer._gate_release_plan([_tx("t1")], {}, {})
    calls = _Calls(proposer, monkeypatch)
    assert _finish(proposer, session, plan, parent_hash="0xnot-the-head") == "abort"
    assert calls.events == []


def test_finish_reports_sealed_when_the_import_path_already_sealed_our_block(proposer, session, monkeypatch):
    """The PBFT cert fixes the hash, so a peer's copy can be imported while we wait — benign (#2166 shape)."""
    monkeypatch.setattr(settings, "proposer_release_write_lock_during_gates", True)
    plan = proposer._gate_release_plan([_tx("t1")], {}, {})
    session.add(_blk(2, "0xhash", "0xparent"))
    session.commit()
    calls = _Calls(proposer, monkeypatch)
    assert _finish(proposer, session, plan) == "sealed"
    assert calls.events == []
    assert metrics_registry._counters["proposer_gate_already_sealed_total"] == 1


# --- wiring through _propose_block -------------------------------------------------------

from .test_proposer_watchdog import _patch_pipeline  # noqa: E402
from .test_proposer_watchdog import proposer as watchdog_proposer  # noqa: E402,F401


async def _run(proposer, monkeypatch, *, flag, finish_verdict="ok"):
    log: list[str] = []
    _patch_pipeline(proposer, monkeypatch)  # session factory yields None, as in the watchdog tests
    monkeypatch.setattr(settings, "proposer_release_write_lock_during_gates", flag)

    async def _gates(*_a, **_k):
        log.append("gates")
        return True

    monkeypatch.setattr(proposer, "_run_journaled_gates", _gates)
    monkeypatch.setattr(proposer, "_commit_and_record_block", lambda *_: log.append("commit"))

    async def _broadcast(*_a, **_k):
        log.append("broadcast")
        return True

    monkeypatch.setattr(proposer, "_broadcast_block", _broadcast)

    def _finish_stub(_s, plan, **_k):
        if plan is None:
            return "ok"
        log.append("finish")
        return finish_verdict

    monkeypatch.setattr(proposer, "_gate_release_begin", lambda _s, plan: log.append("begin") if plan is not None else None)
    monkeypatch.setattr(proposer, "_gate_release_finish", _finish_stub)
    result = await proposer._propose_block_with_watchdog(watchdog_after=5.0)
    return result, log


@pytest.mark.asyncio
async def test_flag_off_leaves_the_proposal_flow_untouched(watchdog_proposer, monkeypatch):  # noqa: F811
    result, log = await _run(watchdog_proposer, monkeypatch, flag=False)
    assert result is True
    assert "begin" not in log and "finish" not in log
    assert log.index("gates") < log.index("commit")


@pytest.mark.asyncio
async def test_flag_on_rolls_back_before_gates_and_reapplies_before_commit(watchdog_proposer, monkeypatch):  # noqa: F811
    result, log = await _run(watchdog_proposer, monkeypatch, flag=True)
    assert result is True
    assert log == ["begin", "gates", "finish", "commit", "broadcast"]


@pytest.mark.asyncio
async def test_flag_on_abort_skips_commit_and_broadcast(watchdog_proposer, monkeypatch):  # noqa: F811
    result, log = await _run(watchdog_proposer, monkeypatch, flag=True, finish_verdict="abort")
    assert result is False
    assert "commit" not in log and "broadcast" not in log


@pytest.mark.asyncio
async def test_flag_on_sealed_skips_commit_and_broadcast_but_succeeds(watchdog_proposer, monkeypatch):  # noqa: F811
    result, log = await _run(watchdog_proposer, monkeypatch, flag=True, finish_verdict="sealed")
    assert result is True
    assert "commit" not in log and "broadcast" not in log


# --- real apply: the byte-identical claim, with the real state transition -----------------

import hashlib  # noqa: E402
from typing import Any  # noqa: E402

from aitbc.crypto.crypto import derive_ethereum_address  # noqa: E402
from aitbc_chain.base_models import Account  # noqa: E402
from aitbc_chain.rpc.utils import sign_transaction_data  # noqa: E402

KEY_S = "0x" + "11" * 32
ADDR_S = derive_ethereum_address(KEY_S)
ADDR_R = derive_ethereum_address("0x" + "33" * 32)


def _signed(nonce: int, amount: int, label: str) -> SimpleNamespace:
    tx: dict[str, Any] = {
        "from": ADDR_S,
        "to": ADDR_R,
        "amount": amount,
        "fee": 1,
        "nonce": nonce,
        "payload": {},
        "type": "TRANSFER",
        "chain_id": CHAIN,
        "tx_hash": "0x" + hashlib.sha256(label.encode()).hexdigest(),
    }
    tx["signature"] = sign_transaction_data(tx, KEY_S)
    return SimpleNamespace(tx_hash=tx["tx_hash"], content=tx, received_at=0.0, fee=1, size_bytes=1)


@pytest.fixture
def real_proposer():
    p = object.__new__(PoAProposer)
    p._logger = logging.getLogger("test2193-real")
    p._config = SimpleNamespace(chain_id=CHAIN)
    return p


def _first_apply(real_proposer, session, txs):
    """Exactly what _propose_block does up to signing; returns (plan, block, processed, rejected)."""
    from aitbc_chain.consensus import poa as _poa

    _poa.get_state_transition().reset_processed_cache()
    session.add(Account(chain_id=CHAIN, address=ADDR_S, balance=10**9, nonce=5))
    session.commit()
    acc = session.get(Account, (CHAIN, ADDR_S))
    accounts, existing = {ADDR_S: acc}, {}
    plan = real_proposer._gate_release_plan(txs, accounts, existing)
    rejected: list[tuple[Any, str]] = []
    processed, _c, ok = real_proposer._process_proposal_txs(session, txs, accounts, existing, 2, NOW, rejected)
    assert ok and processed
    real_proposer._persist_rejected_txs(session, rejected, 2, NOW, commit=False)
    block, block_hash = real_proposer._assemble_proposal_block(session, 2, "0xparent", NOW, processed, "0xprop")
    return plan, block, block_hash, processed, rejected


def test_real_apply_reapplies_to_the_identical_block_hash(real_proposer, session, monkeypatch):
    monkeypatch.setattr(settings, "proposer_release_write_lock_during_gates", True)
    txs = [_signed(5, 100, "a"), _signed(6, 10**12, "too-rich")]
    plan, _block, block_hash, processed, rejected = _first_apply(real_proposer, session, txs)
    assert len(processed) == 1 and len(rejected) == 1  # the over-balance tx is rejected, not sealed
    real_proposer._gate_release_begin(session, plan)
    verdict = _finish(
        real_proposer,
        session,
        plan,
        block_hash=block_hash,
        processed_txs=processed,
        rejected_txs=rejected,
    )
    assert verdict == "ok"
    assert "proposer_gate_reapply_mismatch_total" not in metrics_registry._counters
    # the fresh transaction carries the re-applied state, ready for the commit
    row = session.connection().exec_driver_sql("SELECT balance FROM account WHERE address = ?", (ADDR_S,)).fetchone()
    assert row[0] == 10**9 - 101  # applied exactly once, in this transaction


def test_real_apply_aborts_when_state_changed_under_the_released_lock(real_proposer, session, db_path, monkeypatch):
    """The whole point of releasing the lock is that others may write; a write that changes the
    apply inputs must produce a different hash and abort — never commit a block the mesh did not vote on."""
    monkeypatch.setattr(settings, "proposer_release_write_lock_during_gates", True)
    txs = [_signed(5, 100, "a")]
    plan, _block, block_hash, processed, rejected = _first_apply(real_proposer, session, txs)
    real_proposer._gate_release_begin(session, plan)

    other = sqlite3.connect(str(db_path), timeout=1.0)  # a writer that is no longer blocked
    other.execute("UPDATE account SET balance = balance + 7 WHERE address = ?", (ADDR_S,))
    other.commit()
    other.close()

    verdict = _finish(
        real_proposer,
        session,
        plan,
        block_hash=block_hash,
        processed_txs=processed,
        rejected_txs=rejected,
    )
    assert verdict == "abort"
    assert metrics_registry._counters["proposer_gate_reapply_mismatch_total"] == 1
    # the aborted attempt left nothing behind in the session's transaction
    session.rollback()
    assert session.get(Account, (CHAIN, ADDR_S)).balance == 10**9 + 7
