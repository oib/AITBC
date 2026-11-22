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


def test_completed_row_gets_confirm_time_from_release_tx(env):
    """#2458: reconcile-completed rows must carry confirm_time — the sealed
    BRIDGE_RELEASE's timestamp — so the status timeline is readable."""
    rec, eng = env
    _row(eng, "t9")
    _tx(eng, SRC, "t9", "BRIDGE_LOCK")
    sealed_at = datetime(2026, 11, 21, 20, 57, 0, tzinfo=UTC)
    _tx(eng, DST, "rel9", "BRIDGE_RELEASE", payload={"transfer_id": "t9"})
    # _tx uses default_factory for created_at; pin it explicitly instead.
    with Session(eng[DST]) as s:
        from sqlmodel import select as _sel

        tx = s.exec(_sel(Transaction).where(Transaction.tx_hash == "rel9")).one()
        tx.created_at = sealed_at.replace(tzinfo=None)
        s.add(tx)
        s.commit()
    assert rec._reconcile_stale_pending(SRC) == 1
    with Session(eng[SRC]) as s:
        record = s.get(CrossChainTransfer, "t9")
        assert record.status == "completed"
        assert record.target_tx_hash == "rel9"
        assert record.confirm_time is not None
        assert record.confirm_time.replace(tzinfo=None) == sealed_at.replace(tzinfo=None)


def test_reconcile_mirrors_terminal_state_to_memory(env):
    """#2458: a cached in-memory entry must not keep answering 'locked'
    after the DB row went terminal."""
    from aitbc_chain.cross_chain.bridge_types import BridgeStatus, BridgeTransfer

    rec, eng = env
    rec._pending_transfers = {}
    _row(eng, "t10")
    _tx(eng, SRC, "t10", "BRIDGE_LOCK")
    _tx(eng, DST, "rel10", "BRIDGE_RELEASE", payload={"transfer_id": "t10"})
    rec._pending_transfers["t10"] = BridgeTransfer(
        transfer_id="t10",
        source_chain=SRC,
        target_chain=DST,
        sender="0xa",
        recipient="0xb",
        amount=1,
        asset="native",
        status=BridgeStatus.locked,
        source_tx_hash="t10",
        target_tx_hash=None,
        lock_time=OLD,
        confirm_time=None,
        proof=None,
    )
    assert rec._reconcile_stale_pending(SRC) == 1
    mirrored = rec._pending_transfers["t10"]
    assert mirrored.status == BridgeStatus.completed
    assert mirrored.target_tx_hash == "rel10"
    assert mirrored.confirm_time is not None


def test_completed_null_confirm_time_backfilled(env):
    """#2458: rows completed before the confirm_time fix keep NULL forever —
    the backfill pass fills it from the sealed release evidence."""
    rec, eng = env
    # A row already completed (as the pre-fix reconcile left them) with no
    # confirm_time; the release tx is sealed on the target chain.
    with Session(eng[SRC]) as s:
        s.add(
            CrossChainTransfer(
                transfer_id="t11",
                source_chain=SRC,
                target_chain=DST,
                sender="0xa",
                recipient="0xb",
                amount=1,
                status="completed",
                source_tx_hash="t11",
                target_tx_hash="rel11",
                lock_time=OLD,
                confirm_time=None,
            )
        )
        s.commit()
    sealed_at = datetime(2026, 11, 21, 21, 0, 0)
    _tx(eng, DST, "rel11", "BRIDGE_RELEASE", payload={"transfer_id": "t11"})
    with Session(eng[DST]) as s:
        from sqlmodel import select as _sel

        tx = s.exec(_sel(Transaction).where(Transaction.tx_hash == "rel11")).one()
        tx.created_at = sealed_at
        s.add(tx)
        s.commit()
    assert rec._reconcile_stale_pending(SRC) == 1
    with Session(eng[SRC]) as s:
        record = s.get(CrossChainTransfer, "t11")
        assert record.status == "completed"  # never rewritten
        assert record.confirm_time is not None
        assert record.confirm_time.replace(tzinfo=None) == sealed_at


def _completed_null_row(engines, tid="t20", target=DST):
    with Session(engines[SRC]) as s:
        s.add(
            CrossChainTransfer(
                transfer_id=tid,
                source_chain=SRC,
                target_chain=target,
                sender="0xa",
                recipient="0xb",
                amount=1,
                status="completed",
                source_tx_hash=tid,
                lock_time=OLD,
                confirm_time=None,
            )
        )
        s.commit()


def test_remote_evidence_backfills_when_target_store_absent(env, monkeypatch):
    """#2469: hub holds only the source store — the backfill must fall back to
    the producing chain's rpc instead of leaving confirm_time NULL forever."""
    rec, eng = env
    eng.pop(DST)  # this node has no island store — the hub shape
    _completed_null_row(eng)
    monkeypatch.setattr(settings, "chain_sync_sources", f"{DST}:https://island.example")
    remote_at = datetime(2026, 11, 21, 22, 0, 0, tzinfo=UTC)
    rec._fetch_remote_release = lambda base, target, tid: {
        "released": True,
        "status": "completed",
        "target_tx_hash": "rel20",
        "confirm_time": remote_at.isoformat(),
    }
    assert rec._reconcile_stale_pending(SRC) == 1
    with Session(eng[SRC]) as s:
        record = s.get(CrossChainTransfer, "t20")
        assert record.status == "completed"
        assert record.confirm_time is not None
        assert record.confirm_time.replace(tzinfo=None) == remote_at.replace(tzinfo=None)
        assert record.target_tx_hash == "rel20"


def test_remote_evidence_ignored_when_disabled(env, monkeypatch):
    rec, eng = env
    eng.pop(DST)
    _completed_null_row(eng)
    monkeypatch.setattr(settings, "chain_sync_sources", f"{DST}:https://island.example")
    monkeypatch.setattr(settings, "bridge_reconcile_remote_evidence_enabled", False)
    calls = []
    rec._fetch_remote_release = lambda base, target, tid: calls.append(tid) or {}
    assert rec._reconcile_stale_pending(SRC) == 0
    assert calls == []
    with Session(eng[SRC]) as s:
        assert s.get(CrossChainTransfer, "t20").confirm_time is None


def test_remote_evidence_requires_confirmed_status_and_time(env, monkeypatch):
    """A remote row that is still pending — or lacks confirm_time — is not
    release evidence; the local row stays NULL."""
    rec, eng = env
    eng.pop(DST)
    _completed_null_row(eng, tid="t21")
    _completed_null_row(eng, tid="t22")
    monkeypatch.setattr(settings, "chain_sync_sources", f"{DST}:https://island.example")

    def fake_fetch(base, target, tid):
        if tid == "t21":
            return {"released": False, "status": "pending", "confirm_time": "2026-11-21T22:00:00+00:00"}
        return {"released": True, "status": "completed", "confirm_time": None}

    rec._fetch_remote_release = fake_fetch
    assert rec._reconcile_stale_pending(SRC) == 0
    with Session(eng[SRC]) as s:
        assert s.get(CrossChainTransfer, "t21").confirm_time is None
        assert s.get(CrossChainTransfer, "t22").confirm_time is None


def test_remote_evidence_unreachable_keeps_null(env, monkeypatch):
    rec, eng = env
    eng.pop(DST)
    _completed_null_row(eng)
    monkeypatch.setattr(settings, "chain_sync_sources", f"{DST}:https://island.example")
    rec._fetch_remote_release = lambda base, target, tid: None
    assert rec._reconcile_stale_pending(SRC) == 0
    with Session(eng[SRC]) as s:
        assert s.get(CrossChainTransfer, "t20").confirm_time is None


def test_remote_evidence_no_sync_source_configured(env):
    """Without a CHAIN_SYNC_SOURCES entry for the target chain there is no
    remote URL — the pass must not dial anything."""
    rec, eng = env
    eng.pop(DST)
    _completed_null_row(eng)
    calls = []
    rec._fetch_remote_release = lambda base, target, tid: calls.append(tid) or {}
    assert rec._reconcile_stale_pending(SRC) == 0
    assert calls == []


def test_fetch_remote_release_200_and_params(monkeypatch):
    """#2503: the fetch hits the release-evidence route with the target chain
    and returns the flat released/status payload."""
    import httpx

    class _Resp:
        def __init__(self, payload, status=200):
            self._payload = payload
            self.status_code = status

        def json(self):
            return self._payload

    class _Client:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url, params=None):
            self.url = url
            self.params = params
            return _Resp(
                {
                    "success": True,
                    "released": True,
                    "status": "completed",
                    "target_tx_hash": "0xrel",
                    "confirm_time": "2026-11-21T22:00:00+00:00",
                }
            )

    monkeypatch.setattr(httpx, "Client", _Client)
    row = BridgeTransferReconcileMixin._fetch_remote_release("https://island.example", "bc-2", "t1")
    assert row is not None
    assert row["released"] is True
    assert row["target_tx_hash"] == "0xrel"


def test_fetch_remote_release_non_200_and_errors(monkeypatch):
    """#2503: any non-200 — including the route-level 404 an unpatched peer
    returns — stays None (unreachable), never a definitive 'no release'."""
    import httpx

    class _Resp:
        status_code = 404

        def json(self):
            return {}

    class _Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url, params=None):
            return _Resp()

    monkeypatch.setattr(httpx, "Client", _Client)
    assert BridgeTransferReconcileMixin._fetch_remote_release("https://island.example", "bc-2", "t1") is None

    class _Boom:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            raise OSError("unreachable")

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(httpx, "Client", _Boom)
    assert BridgeTransferReconcileMixin._fetch_remote_release("https://island.example", "bc-2", "t1") is None


def test_stale_pending_reconciles_via_remote_evidence(env, monkeypatch):
    """#2486: a stale pending row on a store-less host must still reach
    completed when the target chain's bridge API reports the release —
    the same remote evidence the #2469 backfill uses, now in _evidence_for."""
    rec, eng = env
    eng.pop(DST)  # hub shape: source store only
    _row(eng, "t-remote")
    monkeypatch.setattr(settings, "chain_sync_sources", f"{DST}:https://island.example")
    remote_at = datetime(2026, 11, 22, 1, 2, 3, tzinfo=UTC)
    rec._fetch_remote_release = lambda base, target, tid: (
        {
            "released": True,
            "status": "completed",
            "target_tx_hash": "rel-remote",
            "confirm_time": remote_at.isoformat(),
        }
        if tid == "t-remote"
        else None
    )
    assert rec._reconcile_stale_pending(SRC) == 1
    assert _status(eng, "t-remote") == "completed"
    with Session(eng[SRC]) as s:
        record = s.get(CrossChainTransfer, "t-remote")
        assert record.target_tx_hash == "rel-remote"
        assert record.confirm_time is not None


def test_stale_pending_remote_clear_status_stays_pending(env, monkeypatch):
    """Remote says the transfer is not released — the row honestly stays pending."""
    rec, eng = env
    eng.pop(DST)
    # Stale (>10min grace) but inside the 2h unsealed horizon, with no lock
    # tx — only the remote "not released" answer keeps it pending.
    _row(eng, "t-clear", lock_time=datetime.now(UTC) - timedelta(hours=1))
    monkeypatch.setattr(settings, "chain_sync_sources", f"{DST}:https://island.example")
    rec._fetch_remote_release = lambda base, target, tid: {"released": False, "status": "pending"}
    assert rec._reconcile_stale_pending(SRC) == 0
    assert _status(eng, "t-clear") == "pending"


def _completed_null_row_in(engines, store, tid, source, target):
    """A completed row with NULL confirm_time living in ``store``'s db."""
    with Session(engines[store]) as s:
        s.add(
            CrossChainTransfer(
                transfer_id=tid,
                source_chain=source,
                target_chain=target,
                sender="0xa",
                recipient="0xb",
                amount=1,
                status="completed",
                source_tx_hash=tid,
                lock_time=OLD,
                confirm_time=None,
            )
        )
        s.commit()


def test_reverse_direction_completed_row_backfilled(env):
    """#2492: hub's bc-2 store holds island->bc-2 rows (local chain is the
    TARGET). The backfill must scan them — the release evidence is the
    local sealed index — even though source_chain != the pass chain."""
    rec, eng = env
    _completed_null_row_in(eng, SRC, "t30", source=DST, target=SRC)
    sealed_at = datetime(2026, 11, 22, 1, 0, 0)
    _tx(eng, SRC, "rel30", "BRIDGE_RELEASE", payload={"transfer_id": "t30"})
    with Session(eng[SRC]) as s:
        from sqlmodel import select as _sel

        tx = s.exec(_sel(Transaction).where(Transaction.tx_hash == "rel30")).one()
        tx.created_at = sealed_at
        s.add(tx)
        s.commit()
    assert rec._reconcile_stale_pending(SRC) == 1
    with Session(eng[SRC]) as s:
        record = s.get(CrossChainTransfer, "t30")
        assert record.status == "completed"
        assert record.confirm_time is not None
        assert record.confirm_time.replace(tzinfo=None) == sealed_at


def test_reverse_direction_without_local_release_stays_null(env):
    """A reverse-direction row whose release is not sealed locally must keep
    its honest NULL — involvement widens the scan, not the evidence bar."""
    rec, eng = env
    _completed_null_row_in(eng, SRC, "t31", source=DST, target=SRC)
    assert rec._reconcile_stale_pending(SRC) == 0
    with Session(eng[SRC]) as s:
        assert s.get(CrossChainTransfer, "t31").confirm_time is None


def test_unrelated_chain_row_not_scanned(env):
    """A row between two chains neither of which is the pass chain stays
    untouched even when it sits in the local store."""
    rec, eng = env
    _completed_null_row_in(eng, SRC, "t32", source="chain-x", target="chain-y")
    _tx(eng, SRC, "rel32", "BRIDGE_RELEASE", payload={"transfer_id": "t32"})
    assert rec._reconcile_stale_pending(SRC) == 0
    with Session(eng[SRC]) as s:
        assert s.get(CrossChainTransfer, "t32").confirm_time is None
