"""Regression test for _process_txs_parallel session hygiene (register C-4).

The parallel write phase flushes deltas and queues Transaction rows mid-function.
Before the fix, an exception there escaped with the caller's session left dirty —
the same incident class as the sequential path's savepoint leak. The function must
roll back and report failure instead.
"""

import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

_SRC = Path(__file__).resolve().parents[2] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from aitbc_chain.consensus import poa as poa_module  # noqa: E402
from aitbc_chain.consensus.poa import PoAProposer  # noqa: E402
from aitbc_chain.state.pure_state_transition import StateDelta  # noqa: E402


class _FakeGraph:
    def add_transaction(self, *args, **kwargs):
        pass

    def conflict_rate(self):
        return 0.0

    def get_conflict_groups(self):
        return [["tx1"]]


class _FakeExecutor:
    def __init__(self, max_workers=1):
        pass

    def execute_groups(self, groups, fn):
        return [[fn(item) for item in group] for group in groups]

    def close(self):
        pass


def _make_proposer() -> PoAProposer:
    proposer = PoAProposer.__new__(PoAProposer)
    proposer._config = SimpleNamespace(chain_id="test-chain")
    proposer._logger = MagicMock()
    return proposer


def _make_tx() -> SimpleNamespace:
    return SimpleNamespace(
        tx_hash="tx1",
        content={
            "from": "0x" + "aa" * 20,
            "to": "0x" + "bb" * 20,
            "amount": 5,
            "fee": 1,
            "payload": {},
        },
    )


def _patch_pipeline(monkeypatch, apply_deltas):
    monkeypatch.setattr(poa_module, "DependencyGraph", _FakeGraph)
    monkeypatch.setattr(poa_module, "ParallelExecutor", _FakeExecutor)
    monkeypatch.setattr(
        poa_module, "extract_read_write_sets", lambda content: (frozenset(), frozenset())
    )
    monkeypatch.setattr(
        poa_module,
        "compute_state_delta",
        lambda account_map, tx_data, chain_id, tx_hash, processed: StateDelta(
            sender=tx_data["from"],
            recipient=tx_data["to"],
            sender_balance_change=-5,
            recipient_balance_change=5,
            sender_nonce_change=1,
            success=True,
            tx_type="TRANSFER",
            tx_hash=tx_hash,
        ),
    )
    monkeypatch.setattr(poa_module, "apply_delta_to_map", lambda *a, **k: None)
    monkeypatch.setattr(poa_module, "apply_deltas_to_db", apply_deltas)


def test_write_phase_failure_rolls_back_and_returns_failure(monkeypatch):
    def _boom(session, deltas, chain_id):
        raise RuntimeError("simulated mid-write failure")

    _patch_pipeline(monkeypatch, _boom)

    proposer = _make_proposer()
    session = MagicMock()
    result = proposer._process_txs_parallel(
        session, [_make_tx()], {}, {}, next_height=5, timestamp=datetime.now()
    )

    assert result == ([], set(), False)
    session.rollback.assert_called_once_with()


def test_write_phase_failure_after_transaction_adds_rolls_back(monkeypatch):
    """Failure even later in the write phase (during session.add) is also defended."""

    applied = {"called": False}

    def _apply_ok(session, deltas, chain_id):
        applied["called"] = True

    _patch_pipeline(monkeypatch, _apply_ok)

    proposer = _make_proposer()
    session = MagicMock()
    session.add.side_effect = RuntimeError("simulated add failure")

    result = proposer._process_txs_parallel(
        session, [_make_tx()], {}, {}, next_height=5, timestamp=datetime.now()
    )

    assert result == ([], set(), False)
    session.rollback.assert_called_once_with()


def test_happy_path_returns_processed_txs(monkeypatch):
    def _apply_ok(session, deltas, chain_id):
        pass

    _patch_pipeline(monkeypatch, _apply_ok)

    proposer = _make_proposer()
    session = MagicMock()
    tx = _make_tx()

    processed, changed, ok = proposer._process_txs_parallel(
        session, [tx], {}, {}, next_height=5, timestamp=datetime.now()
    )

    assert ok is True
    assert processed == [tx]
    assert changed
    session.rollback.assert_not_called()
