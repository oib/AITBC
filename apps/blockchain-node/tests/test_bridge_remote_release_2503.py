"""#2503 — remote release evidence must be authoritative for sealed BRIDGE_RELEASE txs.

Live finding: a target chain can seal the ``BRIDGE_RELEASE`` credit without
ever holding a ``cross_chain_transfer`` row for a hub-originated transfer.
``GET /rpc/bridge/transfer/{id}`` answered 404 in that shape, so the
store-less reconciler/refund guard read the release as ``unreachable`` —
confirmed rows failed closed forever and pending rows could be refunded
after the release had already paid out.

The fix adds ``GET /rpc/bridge/release/{transfer_id}``, which always answers
200 with a definitive ``released`` flag drawn from the transfer row *and*
the sealed ``BRIDGE_RELEASE`` index. These tests drive the real route with
a ``TestClient`` against an island app holding only the sealed tx, then dial
it from the hub-side reconciler through ``httpx``'s ASGI transport — no
stubbed fetchers.
"""

from __future__ import annotations

import socket
import sys
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

_SRC = Path(__file__).resolve().parents[2] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402
from sqlmodel import Session, create_engine  # noqa: E402

from aitbc_chain.base_models import Transaction  # noqa: E402
from aitbc_chain.base_models_aux import CrossChainTransfer  # noqa: E402
from aitbc_chain.config import settings  # noqa: E402
from aitbc_chain.cross_chain.bridge import CrossChainBridge  # noqa: E402
from aitbc_chain.cross_chain.bridge_transfer_confirm import BridgeTransferConfirmMixin  # noqa: E402
from aitbc_chain.cross_chain.bridge_transfer_reconcile import BridgeTransferReconcileMixin  # noqa: E402
from aitbc_chain.metadata import chain_metadata  # noqa: E402
from aitbc_chain.rpc.routers import bridge as bridge_router_mod  # noqa: E402

HUB, ISLAND = "bc-2-hub", "bc-2-island"
NOW = datetime.now(UTC)
RELEASE_HASH = "0x" + "ab" * 32


class _HubRec(BridgeTransferConfirmMixin, BridgeTransferReconcileMixin):
    """Hub-side bridge mixin holding only the source-chain store."""

    def __init__(self, engine):
        self.engine = engine

    @contextmanager
    def _session_for(self, chain_id=""):
        with Session(self.engine) as s:
            yield s

    def _chain_db_ready(self, chain_id):
        return chain_id == HUB


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("AITBC_ENABLE_RATE_LIMITING", "false")
    monkeypatch.setattr(settings, "bridge_reconcile_enabled", True)
    monkeypatch.setattr(settings, "bridge_reconcile_dry_run", False)
    monkeypatch.setattr(settings, "supported_chains", f"{HUB},{ISLAND}")
    monkeypatch.setattr(settings, "bridge_reconcile_remote_evidence_enabled", True)


@pytest.fixture
def island_engine():
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    chain_metadata.create_all(eng)
    yield eng
    chain_metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture
def island_bridge(island_engine):
    return CrossChainBridge(lambda: Session(island_engine))


@pytest.fixture
def island_app(island_bridge):
    """The island's real bridge router — release route included."""
    app = FastAPI()
    app.include_router(bridge_router_mod.router, prefix="/rpc")
    return app


@pytest.fixture
def island_client(island_app, island_bridge):
    with (
        patch("aitbc_chain.cross_chain.bridge.get_cross_chain_bridge", return_value=island_bridge),
        patch.object(bridge_router_mod, "validate_chain_id", lambda chain_id: True),
    ):
        yield TestClient(island_app)


@contextmanager
def _serve(app) -> Iterator[str]:
    """Serve a FastAPI app over real HTTP on an ephemeral port."""
    import uvicorn

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(200):
        if server.started:
            break
        time.sleep(0.05)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=5)


@pytest.fixture
def island_server(island_client, island_app):
    """The island app on a real socket — the hub dials it with plain httpx.

    Depends on ``island_client`` so the bridge/chain-id patches stay active
    for the whole test (they are process-global, so the server thread sees
    them too).
    """
    with _serve(island_app) as base:
        yield base


@pytest.fixture
def hub(island_server, monkeypatch):
    """Hub engine + reconciler; CHAIN_SYNC_SOURCES points at the live island."""
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    chain_metadata.create_all(eng)
    monkeypatch.setattr(settings, "chain_sync_sources", f"{ISLAND}:{island_server}")
    rec = _HubRec(eng)
    yield rec, eng
    eng.dispose()


def _seal_release(engine, tid: str, tx_hash: str = RELEASE_HASH) -> None:
    """Seal a BRIDGE_RELEASE for ``tid`` on the island — no transfer row."""
    with Session(engine) as s:
        s.add(
            Transaction(
                chain_id=ISLAND,
                tx_hash=tx_hash,
                type="BRIDGE_RELEASE",
                status="sealed",
                sender="bridge_release",
                recipient="0xrecipient",
                value=100,
                fee=0,
                nonce=0,
                payload={"transfer_id": tid, "target_chain": ISLAND},
                envelope={},
                block_height=9,
                timestamp=NOW,
            )
        )
        s.commit()


def _hub_pending_row(engine, tid: str, *, status: str = "pending", age: timedelta = timedelta(hours=5)) -> None:
    with Session(engine) as s:
        s.add(
            CrossChainTransfer(
                transfer_id=tid,
                source_chain=HUB,
                target_chain=ISLAND,
                sender="0xsender",
                recipient="0xrecipient",
                amount=100,
                status=status,
                source_tx_hash=tid,
                lock_time=datetime.now(UTC) - age,
            )
        )
        s.commit()


def _hub_record(engine, tid: str) -> CrossChainTransfer:
    with Session(engine) as s:
        record = s.get(CrossChainTransfer, tid)
        assert record is not None
        return record


# --------------------------------------------------------------------------
# Serving side: GET /rpc/bridge/release/{transfer_id}
# --------------------------------------------------------------------------


def test_release_route_reports_sealed_release_without_transfer_row(island_client, island_engine):
    """Auditor repro: sealed BRIDGE_RELEASE + no cross_chain_transfer row —
    the release route must answer released:true (the old /transfer route 404s)."""
    _seal_release(island_engine, "t-release")

    resp = island_client.get(f"/rpc/bridge/release/t-release?chain_id={ISLAND}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["released"] is True
    assert body["status"] == "completed"
    assert body["target_tx_hash"] == RELEASE_HASH
    assert body["confirm_time"] is not None

    # The row-only endpoint still cannot see it — documenting the 404 the
    # dedicated route exists to fix.
    assert island_client.get("/rpc/bridge/transfer/t-release").status_code == 404


def test_release_route_authoritative_negative_for_unknown_id(island_client):
    """A patched peer answers released:false for an id with no evidence —
    a definitive 'no release', not a transport failure."""
    resp = island_client.get(f"/rpc/bridge/release/nope?chain_id={ISLAND}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["released"] is False
    assert body["status"] is None


def test_release_route_reads_confirmed_row(island_client, island_engine):
    """A confirmed/completed transfer row is release evidence even before the
    release tx index sees it."""
    with Session(island_engine) as s:
        s.add(
            CrossChainTransfer(
                transfer_id="t-row",
                source_chain=HUB,
                target_chain=ISLAND,
                sender="0xsender",
                recipient="0xrecipient",
                amount=5,
                status="confirmed",
                target_tx_hash="0xrowhash",
                confirm_time=NOW,
            )
        )
        s.commit()

    resp = island_client.get(f"/rpc/bridge/release/t-row?chain_id={ISLAND}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["released"] is True
    assert body["status"] == "confirmed"
    assert body["target_tx_hash"] == "0xrowhash"


def test_release_route_pending_row_is_not_released(island_client, island_engine):
    with Session(island_engine) as s:
        s.add(
            CrossChainTransfer(
                transfer_id="t-pending",
                source_chain=HUB,
                target_chain=ISLAND,
                sender="0xsender",
                recipient="0xrecipient",
                amount=5,
                status="pending",
            )
        )
        s.commit()

    resp = island_client.get(f"/rpc/bridge/release/t-pending?chain_id={ISLAND}")
    assert resp.status_code == 200
    assert resp.json()["released"] is False
    assert resp.json()["status"] == "pending"


# --------------------------------------------------------------------------
# Consumer side: hub reconciler + refund verdict dial the real route
# --------------------------------------------------------------------------


def test_reconcile_completes_via_real_release_route(hub, island_engine):
    """Auditor repro end-to-end: store-less hub + sealed release on the
    island → the stale pending row reconciles to completed with the remote
    tx hash and confirm time."""
    rec, eng = hub
    _seal_release(island_engine, "t-e2e")
    _hub_pending_row(eng, "t-e2e")

    assert rec._reconcile_stale_pending(HUB) == 1
    record = _hub_record(eng, "t-e2e")
    assert record.status == "completed"
    assert record.target_tx_hash == RELEASE_HASH
    assert record.confirm_time is not None


def test_remote_verdict_reads_real_route(hub, island_engine):
    rec, _ = hub
    _seal_release(island_engine, "t-verdict")

    verdict, row = rec._remote_release_verdict(ISLAND, "t-verdict")
    assert verdict == "released"
    assert row is not None and row["target_tx_hash"] == RELEASE_HASH

    verdict, _ = rec._remote_release_verdict(ISLAND, "t-absent")
    assert verdict == "clear"


def _island_row(engine, tid: str, *, status: str = "locked") -> None:
    """A copy row on the island whose status lags a sealed release (#2509)."""
    with Session(engine) as s:
        s.add(
            CrossChainTransfer(
                transfer_id=tid,
                source_chain=HUB,
                target_chain=ISLAND,
                sender="0xsender",
                recipient="0xrecipient",
                amount=5,
                status=status,
            )
        )
        s.commit()


def test_release_route_stale_row_still_reads_sealed_release(island_client, island_engine):
    """#2509: a locked/pending copy row must not hide a sealed BRIDGE_RELEASE —
    the row's status is reported for information but released stays True."""
    _island_row(island_engine, "t-stale", status="locked")
    _seal_release(island_engine, "t-stale")

    resp = island_client.get(f"/rpc/bridge/release/t-stale?chain_id={ISLAND}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["released"] is True
    assert body["status"] == "locked"
    assert body["target_tx_hash"] == RELEASE_HASH


def test_remote_verdict_stale_row_is_released(hub, island_engine):
    """Auditor repro flipped: island holds a locked row plus the sealed
    release; the hub's confirmed row must verdict 'released' and the refund
    guard must refuse — not read the stale row as 'clear'."""
    rec, eng = hub
    _island_row(island_engine, "t-stale-row")
    _seal_release(island_engine, "t-stale-row")
    _hub_pending_row(eng, "t-stale-row", status="confirmed", age=timedelta(hours=3))

    verdict, row = rec._remote_release_verdict(ISLAND, "t-stale-row")
    assert verdict == "released"
    assert row is not None and row["target_tx_hash"] == RELEASE_HASH

    released, tx_hash, _ = rec._refund_release_evidence(None, _hub_record(eng, "t-stale-row"), "t-stale-row")
    assert released is True
    assert tx_hash == RELEASE_HASH


def test_unpatched_peer_404_stays_unreachable_not_clear(hub, island_client, monkeypatch):
    """A peer without the release route answers the route-level 404 — the
    consumer must keep the fail-closed ``unreachable`` verdict, never read
    it as 'no release'."""
    rec, eng = hub
    _hub_pending_row(eng, "t-old-peer", status="confirmed", age=timedelta(hours=3))

    bare = FastAPI()  # no bridge router — every path 404s
    with _serve(bare) as base:
        monkeypatch.setattr(settings, "chain_sync_sources", f"{ISLAND}:{base}")

        verdict, _ = rec._remote_release_verdict(ISLAND, "t-old-peer")
        assert verdict == "unreachable"

        # And the refund guard fails closed for the confirmed row.
        with pytest.raises(ValueError, match="unreachable"):
            rec._refund_release_evidence(None, _hub_record(eng, "t-old-peer"), "t-old-peer")
