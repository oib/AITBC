"""#2257 — node-local reconciler moves stale pending bridge rows to terminal states."""

from __future__ import annotations

import sys
import time
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import pytest  # noqa: E402
from aitbc_chain.base_models import Transaction  # noqa: E402
from aitbc_chain.base_models_aux import CrossChainTransfer  # noqa: E402
from aitbc_chain.config import settings  # noqa: E402
from aitbc_chain.cross_chain.bridge_transfer_reconcile import BridgeTransferReconcileMixin  # noqa: E402
from aitbc_chain.metadata import chain_metadata  # noqa: E402
from sqlmodel import Session, create_engine  # noqa: E402

SRC, DST = "bc-2-fixture", "island-fixture"
NOW = datetime.now(UTC)
OLD = NOW - timedelta(hours=5)


class _Rec(BridgeTransferReconcileMixin):
    def __init__(self, engines):
        self.engines = engines

    @contextmanager
    def _session_for(self, chain_id=""):
        with Session(self.engines[chain_id]) as s:
            yield s

    def _chain_db_ready(self, chain_id):
        return chain_id in self.engines


@pytest.fixture
def env(tmp_path, monkeypatch):
    engines = {}
    for c in (SRC, DST):
        e = create_engine(f"sqlite:///{tmp_path / (c + '.db')}")
        chain_metadata.create_all(e)
        engines[c] = e
    monkeypatch.setattr(settings, "bridge_reconcile_enabled", True)
    monkeypatch.setattr(settings, "bridge_reconcile_dry_run", False)
    yield _Rec(engines), engines
    for e in engines.values():
        e.dispose()


def _row(engines, tid, lock_time=OLD, source_tx=None):
    with Session(engines[SRC]) as s:
        s.add(
            CrossChainTransfer(
                transfer_id=tid,
                source_chain=SRC,
                target_chain=DST,
                sender="0xa",
                recipient="0xb",
                amount=1,
                status="pending",
                source_tx_hash=source_tx or tid,
                lock_time=lock_time,
            )
        )
        s.commit()


def _tx(engines, chain, tx_hash, tx_type, *, height=5, status="confirmed", payload=None):
    with Session(engines[chain]) as s:
        s.add(
            Transaction(
                chain_id=chain,
                tx_hash=tx_hash,
                sender="x",
                recipient="y",
                payload=payload or {},
                value=0,
                fee=0,
                nonce=0,
                timestamp=NOW,
                block_height=height,
                status=status,
                type=tx_type,
            )
        )
        s.commit()


def _status(engines, tid):
    with Session(engines[SRC]) as s:
        return s.get(CrossChainTransfer, tid).status


def test_sealed_release_completes(env):
    rec, eng = env
    _row(eng, "t1")
    _tx(eng, SRC, "t1", "BRIDGE_LOCK")
    _tx(eng, DST, "rel1", "BRIDGE_RELEASE", payload={"transfer_id": "t1"})
    assert rec._reconcile_stale_pending(SRC) == 1
    assert _status(eng, "t1") == "completed"
    with Session(eng[SRC]) as s:
        assert s.get(CrossChainTransfer, "t1").target_tx_hash == "rel1"


def test_sealed_refund_refunds(env):
    rec, eng = env
    _row(eng, "t2")
    _tx(eng, SRC, "t2", "BRIDGE_LOCK")
    _tx(eng, SRC, "ref2", "BRIDGE_REFUND", payload={"transfer_id": "t2"})
    rec._reconcile_stale_pending(SRC)
    assert _status(eng, "t2") == "refunded"


def test_sealed_lock_without_outcome_stays_pending(env):
    rec, eng = env
    _row(eng, "t3")
    _tx(eng, SRC, "t3", "BRIDGE_LOCK")
    assert rec._reconcile_stale_pending(SRC) == 0
    assert _status(eng, "t3") == "pending"


def test_rejected_lock_fails(env):
    rec, eng = env
    _row(eng, "t4")
    _tx(eng, SRC, "t4", "BRIDGE_LOCK", height=None, status="rejected")
    rec._reconcile_stale_pending(SRC)
    assert _status(eng, "t4") == "failed"


def test_unsealed_past_horizon_fails_but_young_does_not(env):
    rec, eng = env
    _row(eng, "old")  # no lock tx at all, 5h old (> 2h horizon)
    _row(eng, "mid", lock_time=NOW - timedelta(minutes=30))  # past grace, inside horizon
    rec._reconcile_stale_pending(SRC)
    assert _status(eng, "old") == "failed"
    assert _status(eng, "mid") == "pending"


def test_inside_grace_is_untouched(env):
    rec, eng = env
    _row(eng, "new", lock_time=NOW - timedelta(seconds=30))
    _tx(eng, DST, "rel", "BRIDGE_RELEASE", payload={"transfer_id": "new"})
    assert rec._reconcile_stale_pending(SRC) == 0
    assert _status(eng, "new") == "pending"


def test_terminal_rows_never_rewritten_and_idempotent(env):
    rec, eng = env
    _row(eng, "t5")
    _tx(eng, DST, "rel5", "BRIDGE_RELEASE", payload={"transfer_id": "t5"})
    with Session(eng[SRC]) as s:
        s.add(
            CrossChainTransfer(
                transfer_id="done",
                source_chain=SRC,
                target_chain=DST,
                sender="a",
                recipient="b",
                amount=1,
                status="refunded",
                lock_time=OLD,
            )
        )
        s.commit()
    assert rec._reconcile_stale_pending(SRC) == 1
    assert rec._reconcile_stale_pending(SRC) == 0
    assert _status(eng, "done") == "refunded"


def test_disabled_and_dry_run_change_nothing(env, monkeypatch):
    rec, eng = env
    _row(eng, "t6")
    _tx(eng, DST, "rel6", "BRIDGE_RELEASE", payload={"transfer_id": "t6"})
    monkeypatch.setattr(settings, "bridge_reconcile_enabled", False)
    assert rec._reconcile_stale_pending(SRC) == 0
    monkeypatch.setattr(settings, "bridge_reconcile_enabled", True)
    monkeypatch.setattr(settings, "bridge_reconcile_dry_run", True)
    assert rec._reconcile_stale_pending(SRC) == 0
    assert _status(eng, "t6") == "pending"


def test_expired_deadline_defers(env):
    rec, eng = env
    _row(eng, "t7")
    _tx(eng, DST, "rel7", "BRIDGE_RELEASE", payload={"transfer_id": "t7"})
    assert rec._reconcile_stale_pending(SRC, deadline=time.monotonic() - 1) == 0
    assert _status(eng, "t7") == "pending"


def test_target_store_unavailable_leaves_release_undetected(env):
    rec, eng = env
    _row(eng, "t8", lock_time=NOW - timedelta(minutes=30))
    rec.engines = {SRC: eng[SRC]}  # target not hosted here
    assert rec._reconcile_stale_pending(SRC) == 0
    assert _status(eng, "t8") == "pending"
